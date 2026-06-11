"""
LLM call metrics — Prometheus instrumentation for QPS, latency, and confidence.

Exposes:
    - llm_call_total:         Counter of LLM invocations (by model, provider)
    - llm_call_latency_seconds: Histogram of LLM call duration
    - llm_call_qps:            Gauge — calls per second (sliding window)
    - agent_loop_verdict_total: Counter of LoopGuard verdicts
    - agent_token_ratio:       Gauge — current token usage ratio
    - agent_confidence:        Gauge — average action confidence

Usage:
    from app.core.metrics.llm_metrics import track_llm_call, record_verdict

    @track_llm_call(model="deepseek-chat", provider="deepseek")
    async def my_llm_call():
        return await llm.ainvoke(messages)

    # After loop guard check:
    record_verdict(verdict, thread_id)
"""

from __future__ import annotations
import time
from collections import deque
from typing import Callable

from prometheus_client import Counter, Gauge, Histogram, generate_latest, REGISTRY

# ── Prometheus metric definitions ──────────────────────────────

LLM_CALL_TOTAL = Counter(
    "llm_call_total",
    "Total number of LLM invocations",
    ["model", "provider"],
)

LLM_CALL_LATENCY = Histogram(
    "llm_call_latency_seconds",
    "LLM call duration in seconds",
    ["model", "provider"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

LLM_CALL_ERRORS = Counter(
    "llm_call_errors_total",
    "Total number of LLM call errors",
    ["model", "provider", "error_type"],
)

AGENT_LOOP_VERDICT = Counter(
    "agent_loop_verdict_total",
    "LoopGuard verdict counts",
    ["verdict", "engine"],
)

AGENT_TOKEN_RATIO = Gauge(
    "agent_token_ratio",
    "Current token usage ratio (input_tokens / available_context)",
    ["thread_id"],
)

AGENT_CONFIDENCE = Gauge(
    "agent_confidence",
    "Average action confidence score",
    ["thread_id"],
)

AGENT_ITERATION = Gauge(
    "agent_loop_iterations",
    "Current loop iteration count",
    ["thread_id"],
)


# ── Sliding window for QPS ─────────────────────────────────────

class SlidingWindow:
    """Track event timestamps for QPS calculation over a sliding window."""

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self._timestamps: deque[float] = deque()

    def record(self):
        """Record an event at the current time."""
        now = time.monotonic()
        self._timestamps.append(now)
        self._prune(now)

    def _prune(self, now: float | None = None):
        """Remove timestamps outside the window."""
        cutoff = (now or time.monotonic()) - self.window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    @property
    def qps(self) -> float:
        """Current QPS (calls per second) over the window."""
        self._prune()
        if not self._timestamps:
            return 0.0
        elapsed = time.monotonic() - self._timestamps[0]
        if elapsed <= 0:
            return 0.0
        return len(self._timestamps) / min(elapsed, self.window_seconds)

    @property
    def p99(self) -> float | None:
        """P99 latency estimate (requires storing latencies separately)."""
        # P99 is tracked separately via Prometheus Histogram quantiles
        return None


# ── P99 latency tracker ────────────────────────────────────────

class P99Tracker:
    """Track P99 latency using a sorted list of recent latencies."""

    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self._latencies: deque[float] = deque()

    def record(self, latency_seconds: float):
        """Record a latency sample."""
        self._latencies.append(latency_seconds)
        if len(self._latencies) > self.max_samples:
            self._latencies.popleft()

    @property
    def p50(self) -> float:
        return self._percentile(0.50)

    @property
    def p90(self) -> float:
        return self._percentile(0.90)

    @property
    def p99(self) -> float:
        return self._percentile(0.99)

    def _percentile(self, p: float) -> float:
        if not self._latencies:
            return 0.0
        sorted_lat = sorted(self._latencies)
        idx = int(len(sorted_lat) * p)
        idx = min(idx, len(sorted_lat) - 1)
        return sorted_lat[idx]


# ── Global instances ───────────────────────────────────────────

_qps_window = SlidingWindow(window_seconds=60.0)
_p99_tracker = P99Tracker(max_samples=1000)

LLM_QPS = Gauge("llm_call_qps", "LLM calls per second (60s sliding window)")
LLM_P99_LATENCY = Gauge("llm_call_p99_latency_seconds", "LLM call P99 latency (seconds)")


# ── Public API ──────────────────────────────────────────────────

def track_llm_call(model: str = "deepseek-chat", provider: str = "deepseek"):
    """Decorator to track LLM call metrics.

    Usage:
        @track_llm_call(model="deepseek-chat", provider="deepseek")
        async def call_llm():
            return await llm.ainvoke(messages)
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            start = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.monotonic() - start

                LLM_CALL_TOTAL.labels(model=model, provider=provider).inc()
                LLM_CALL_LATENCY.labels(model=model, provider=provider).observe(elapsed)
                _qps_window.record()
                _p99_tracker.record(elapsed)

                # Update gauges
                LLM_QPS.set(round(_qps_window.qps, 2))
                LLM_P99_LATENCY.set(round(_p99_tracker.p99, 3))

                return result
            except Exception as e:
                elapsed = time.monotonic() - start
                error_type = type(e).__name__
                LLM_CALL_ERRORS.labels(model=model, provider=provider, error_type=error_type).inc()
                raise

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator


def record_verdict(verdict, thread_id: str = "", engine: str = "agent"):
    """Record a LoopGuard verdict to Prometheus."""
    AGENT_LOOP_VERDICT.labels(verdict=str(verdict), engine=engine).inc()


def update_guard_metrics(thread_id: str, token_ratio: float, confidence: float, iteration: int):
    """Update gauge metrics from LoopGuard state."""
    AGENT_TOKEN_RATIO.labels(thread_id=thread_id).set(token_ratio)
    AGENT_CONFIDENCE.labels(thread_id=thread_id).set(confidence)
    AGENT_ITERATION.labels(thread_id=thread_id).set(iteration)


def get_metrics() -> bytes:
    """Generate Prometheus metrics in text format."""
    return generate_latest(REGISTRY)


def get_llm_stats() -> dict:
    """Return current LLM call statistics for non-Prometheus consumers."""
    return {
        "qps": round(_qps_window.qps, 2),
        "window_seconds": _qps_window.window_seconds,
        "p50_ms": round(_p99_tracker.p50 * 1000, 1),
        "p90_ms": round(_p99_tracker.p90 * 1000, 1),
        "p99_ms": round(_p99_tracker.p99 * 1000, 1),
        "total_calls": _qps_window._timestamps and len(_qps_window._timestamps) or 0,
    }
