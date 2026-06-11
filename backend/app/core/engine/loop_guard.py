"""
Loop Safety Guard — multi-layer protection against infinite agent loops.

Combined strategy with five layers + Prometheus metrics:

    Layer 1 (Business):     Task completion detection via existing _should_continue logic
    Layer 2 (Safety):       Max iteration threshold → STOP_MAX_ITERATIONS
    Layer 3 (Performance):  Token ratio circuit breaker → WARN at 60%, STOP at 80%
                            ratio = input_tokens / (context_window - max_output_tokens)
    Layer 4 (Interaction):  User cancel interface → STOP_CANCELLED
    Layer 5 (Production):   Dedup watchdog + confidence scoring →
                            STOP_DEDUP (identical results) / STOP_LOW_CONFIDENCE

Usage:
    from app.core.engine.loop_guard import LoopGuard, LoopConfig, LoopVerdict

    config = LoopConfig()
    guard = LoopGuard(config, thread_id="abc123")

    # Before each tool execution:
    verdict = guard.check(input_tokens=1200, tool_results=["result1", "result2"])
    if verdict == LoopVerdict.CONTINUE:
        ...  # proceed
    elif verdict == LoopVerdict.WARN:
        ...  # approaching limit, should wrap up
    else:
        logger.warning("loop_guard_stop", verdict=verdict.value, **guard.summary)
        break
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


class LoopVerdict(Enum):
    """Result of a LoopGuard safety check."""
    CONTINUE = "continue"
    WARN = "warn"                       # Token ratio >= 60%, wrap up soon
    STOP_MAX_ITERATIONS = "stop_max_iterations"
    STOP_TOKEN_BUDGET = "stop_token_budget"     # Token ratio >= 80%
    STOP_DEDUP = "stop_duplicate_results"        # N consecutive identical tool results
    STOP_LOW_CONFIDENCE = "stop_low_confidence"  # Streak of low-confidence actions
    STOP_CANCELLED = "stop_cancelled"


@dataclass
class LoopConfig:
    """Configuration for LoopGuard.

    All values have sensible defaults. Override via app.config.Settings
    for production tuning.
    """
    # Layer 2: Safety threshold
    max_iterations: int = 5

    # Layer 3: Token ratio circuit breaker
    context_window: int = 65536        # DeepSeek-v3 default
    max_output_tokens: int = 2048
    token_warn_ratio: float = 0.6     # 60% → WARN
    token_stop_ratio: float = 0.8     # 80% → STOP

    # Layer 5a: Dedup watchdog
    dedup_window: int = 3
    dedup_enabled: bool = True

    # Layer 5b: Confidence scoring
    confidence_threshold: float = 0.3  # Below this is "low confidence"
    low_confidence_streak: int = 2     # Consecutive low-confidence actions to trigger stop

    @property
    def available_context(self) -> int:
        """Effective context budget = total window - reserved output space."""
        return self.context_window - self.max_output_tokens


class LoopGuard:
    """Multi-layer safety guard for agent execution loops.

    Tracks per-conversation state and checks all safety layers on each iteration.

    Cancel mechanism (Layer 4):
        Uses an in-memory set of cancelled thread_ids. Migrate to Redis
        when the Redis gap is closed for cross-process visibility.
    """

    # Class-level cancel registry
    _cancelled_threads: ClassVar[set[str]] = set()

    def __init__(self, config: LoopConfig | None = None, thread_id: str = ""):
        self.config = config or LoopConfig()
        self.thread_id = thread_id
        self.iteration = 0
        self._input_tokens: list[int] = []  # per-LLM-call input token counts
        self._tool_results: list[str] = []
        self._tool_confidences: list[float] = []  # per-tool-call confidence scores
        self._low_confidence_streak = 0

    # ── Public API ──────────────────────────────────────────────

    def check(
        self,
        input_tokens: int = 0,
        tool_results: list[str] | None = None,
    ) -> LoopVerdict:
        """Run all safety checks and return a verdict.

        Call this before each tool execution iteration.

        Args:
            input_tokens: Input token count from the most recent LLM call.
            tool_results: Accumulated tool result strings. If None, skips dedup check.
        """
        self.iteration += 1

        # Layer 2: Max iterations
        if self.iteration > self.config.max_iterations:
            return LoopVerdict.STOP_MAX_ITERATIONS

        # Layer 4: User cancel
        if self._is_cancelled():
            return LoopVerdict.STOP_CANCELLED

        # Layer 3: Token ratio circuit breaker
        if input_tokens > 0:
            self._input_tokens.append(input_tokens)
        cumulative_input = sum(self._input_tokens)
        ratio = self._compute_token_ratio(cumulative_input)

        if ratio >= self.config.token_stop_ratio:
            return LoopVerdict.STOP_TOKEN_BUDGET

        # Layer 5a: Dedup watchdog (only if enabled)
        if self.config.dedup_enabled and tool_results and len(tool_results) >= self.config.dedup_window:
            self._tool_results = list(tool_results)
            last_n = tool_results[-self.config.dedup_window:]
            if len(set(last_n)) == 1 and last_n[0]:
                return LoopVerdict.STOP_DEDUP

        # Layer 5b: Low confidence streak
        if self._low_confidence_streak >= self.config.low_confidence_streak:
            return LoopVerdict.STOP_LOW_CONFIDENCE

        # Token ratio warning (non-blocking)
        if ratio >= self.config.token_warn_ratio:
            return LoopVerdict.WARN

        return LoopVerdict.CONTINUE

    def record_tool_result(self, result: str, confidence: float | None = None):
        """Record a tool execution result with optional confidence score.

        Confidence is computed heuristically if not provided:
        - Empty/error results → low confidence (0.0–0.2)
        - Short results → moderate confidence (0.5)
        - Normal results → high confidence (0.8)
        """
        result_str = str(result).strip()
        self._tool_results.append(result_str)

        if confidence is not None:
            score = confidence
        else:
            score = self._estimate_confidence(result_str)

        self._tool_confidences.append(score)

        if score < self.config.confidence_threshold:
            self._low_confidence_streak += 1
        else:
            self._low_confidence_streak = 0

    def record_token_usage(self, usage: dict | None):
        """Record token usage from an LLM response.

        Args:
            usage: OpenAI-compatible usage dict, e.g.
                {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        """
        if usage:
            prompt_tokens = usage.get("prompt_tokens", 0)
            if prompt_tokens > 0:
                self._input_tokens.append(prompt_tokens)
            else:
                # Fallback: estimate from total_tokens
                total = usage.get("total_tokens", 0)
                if total > 0:
                    self._input_tokens.append(total)

    # ── Cancel mechanism (Layer 4) ──────────────────────────────

    @classmethod
    def request_cancel(cls, thread_id: str) -> bool:
        """Mark a thread for cancellation. Returns True if newly marked."""
        if thread_id in cls._cancelled_threads:
            return False
        cls._cancelled_threads.add(thread_id)
        return True

    @classmethod
    def clear_cancel(cls, thread_id: str):
        """Remove a thread's cancel flag."""
        cls._cancelled_threads.discard(thread_id)

    def _is_cancelled(self) -> bool:
        return bool(self.thread_id) and self.thread_id in self._cancelled_threads

    # ── Internal helpers ────────────────────────────────────────

    def _compute_token_ratio(self, cumulative_input: int) -> float:
        """Compute input_tokens / (context_window - max_output_tokens)."""
        available = self.config.available_context
        if available <= 0:
            return 0.0
        return cumulative_input / available

    @staticmethod
    def _estimate_confidence(result: str) -> float:
        """Heuristic confidence estimation from tool result quality.

        Returns a value between 0.0 (no confidence) and 1.0 (high confidence).
        """
        if not result:
            return 0.0

        lower = result.lower()

        # Explicit error indicators
        if any(kw in lower for kw in ("error:", "exception:", "traceback", "failed to")):
            return 0.1

        # Not-found / empty indicators
        if any(kw in lower for kw in ("not found", "no results", "no data", "unavailable")):
            return 0.2

        # Suspiciously short results (no real content)
        if len(result) < 20:
            return 0.4

        # Normal — assume reasonable confidence
        return 0.8

    # ── Properties ──────────────────────────────────────────────

    @property
    def token_ratio(self) -> float:
        """Current cumulative input token ratio (0.0–∞)."""
        return self._compute_token_ratio(sum(self._input_tokens))

    @property
    def avg_confidence(self) -> float:
        """Average confidence across all recorded tool calls."""
        if not self._tool_confidences:
            return 1.0
        return sum(self._tool_confidences) / len(self._tool_confidences)

    @property
    def summary(self) -> dict:
        """Return a summary of the guard's current state for logging/metrics."""
        return {
            "iteration": self.iteration,
            "max_iterations": self.config.max_iterations,
            "cumulative_input_tokens": sum(self._input_tokens),
            "token_ratio": round(self.token_ratio, 4),
            "token_warn_ratio": self.config.token_warn_ratio,
            "token_stop_ratio": self.config.token_stop_ratio,
            "tool_results_count": len(self._tool_results),
            "avg_confidence": round(self.avg_confidence, 2),
            "low_confidence_streak": self._low_confidence_streak,
            "cancelled": self._is_cancelled(),
        }
