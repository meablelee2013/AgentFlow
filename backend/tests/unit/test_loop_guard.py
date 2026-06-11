"""Tests for LoopGuard — multi-layer agent loop safety component.

Covers:
    - Layer 2: Max iteration threshold
    - Layer 3: Token ratio circuit breaker (WARN at 60%, STOP at 80%)
    - Layer 4: User cancel mechanism
    - Layer 5a: Dedup watchdog (consecutive identical results)
    - Layer 5b: Confidence scoring (low confidence streak)
    - Token ratio computation edge cases
"""

import pytest
from app.core.engine.loop_guard import LoopGuard, LoopConfig, LoopVerdict


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def default_config():
    """Config with small values for fast testing."""
    return LoopConfig(
        max_iterations=5,
        context_window=10000,
        max_output_tokens=2000,
        token_warn_ratio=0.6,
        token_stop_ratio=0.8,
        dedup_window=3,
        dedup_enabled=True,
        confidence_threshold=0.3,
        low_confidence_streak=2,
    )


@pytest.fixture
def guard(default_config):
    """Create a guard and clean up cancel state after test."""
    tid = "test-thread"
    # Ensure clean state before test
    LoopGuard.clear_cancel(tid)
    g = LoopGuard(config=default_config, thread_id=tid)
    yield g
    # Clean up after test
    LoopGuard.clear_cancel(tid)


# ── Layer 2: Max Iterations ──────────────────────────────────────

class TestMaxIterations:
    def test_continue_within_limit(self, guard):
        for _ in range(5):
            verdict = guard.check()
            assert verdict == LoopVerdict.CONTINUE

    def test_stop_when_exceeds_limit(self, guard):
        for _ in range(5):
            guard.check()
        verdict = guard.check()
        assert verdict == LoopVerdict.STOP_MAX_ITERATIONS

    def test_custom_max_iterations(self):
        config = LoopConfig(max_iterations=2)
        g = LoopGuard(config=config)
        g.check()
        g.check()
        assert g.check() == LoopVerdict.STOP_MAX_ITERATIONS

    def test_large_max_iterations(self):
        config = LoopConfig(max_iterations=100)
        g = LoopGuard(config=config)
        for _ in range(100):
            assert g.check() == LoopVerdict.CONTINUE
        assert g.check() == LoopVerdict.STOP_MAX_ITERATIONS


# ── Layer 3: Token Ratio Circuit Breaker ─────────────────────────

class TestTokenRatio:
    def test_continue_below_warn(self, guard):
        # context=10000, output=2000 → available=8000
        # 1000/8000 = 0.125 < 0.6
        verdict = guard.check(input_tokens=1000)
        assert verdict == LoopVerdict.CONTINUE

    def test_warn_at_warn_ratio(self, guard):
        # 4800/8000 = 0.6 → exactly at warn threshold
        verdict = guard.check(input_tokens=4800)
        assert verdict == LoopVerdict.WARN

    def test_stop_at_stop_ratio(self, guard):
        # 6400/8000 = 0.8 → exactly at stop threshold
        verdict = guard.check(input_tokens=6400)
        assert verdict == LoopVerdict.STOP_TOKEN_BUDGET

    def test_accumulates_input_tokens(self, guard):
        guard.check(input_tokens=3000)
        guard.check(input_tokens=2000)
        # Cumulative: 5000/8000 = 0.625 → WARN
        verdict = guard.check(input_tokens=0)
        assert verdict == LoopVerdict.WARN

    def test_zero_available_context(self):
        config = LoopConfig(context_window=2000, max_output_tokens=2000)
        g = LoopGuard(config=config)
        # available = 0 → ratio returns 0.0
        verdict = g.check(input_tokens=1000)
        assert verdict == LoopVerdict.CONTINUE

    def test_cumulative_exceeds_stop(self, guard):
        guard.check(input_tokens=3000)
        guard.check(input_tokens=3000)
        # 6000/8000 = 0.75 → WARN
        verdict = guard.check(input_tokens=3000)
        # 9000/8000 = 1.125 → STOP
        assert verdict == LoopVerdict.STOP_TOKEN_BUDGET


# ── Layer 4: User Cancel ─────────────────────────────────────────

class TestCancel:
    def test_cancel_stops_guard(self, guard):
        LoopGuard.request_cancel("test-thread")
        verdict = guard.check()
        assert verdict == LoopVerdict.STOP_CANCELLED

    def test_clear_cancel_restores(self, guard):
        LoopGuard.request_cancel("test-thread")
        LoopGuard.clear_cancel("test-thread")
        assert guard.check() == LoopVerdict.CONTINUE

    def test_different_threads_isolated(self, guard):
        g2 = LoopGuard(config=guard.config, thread_id="other-thread")
        LoopGuard.request_cancel("test-thread")
        assert guard.check() == LoopVerdict.STOP_CANCELLED
        assert g2.check() == LoopVerdict.CONTINUE

    def test_request_cancel_returns_bool(self):
        assert LoopGuard.request_cancel("new-thread") is True   # first time
        assert LoopGuard.request_cancel("new-thread") is False  # already marked
        LoopGuard.clear_cancel("new-thread")


# ── Layer 5a: Dedup Watchdog ─────────────────────────────────────

class TestDedup:
    def test_no_dedup_with_few_results(self, guard):
        results = ["a", "b"]
        verdict = guard.check(tool_results=results)
        assert verdict == LoopVerdict.CONTINUE

    def test_dedup_at_window_threshold(self, guard):
        results = ["same", "same", "same"]
        verdict = guard.check(tool_results=results)
        assert verdict == LoopVerdict.STOP_DEDUP

    def test_dedup_not_triggered_by_different(self, guard):
        results = ["apple", "banana", "cherry"]
        verdict = guard.check(tool_results=results)
        assert verdict != LoopVerdict.STOP_DEDUP

    def test_dedup_respects_window_size(self):
        config = LoopConfig(dedup_window=4)
        g = LoopGuard(config=config)
        # 3 same → not enough
        assert g.check(tool_results=["x", "x", "x"]) == LoopVerdict.CONTINUE
        # 4 same → triggers
        assert g.check(tool_results=["x", "x", "x", "x"]) == LoopVerdict.STOP_DEDUP

    def test_empty_results_skipped(self, guard):
        results = ["", "", ""]
        verdict = guard.check(tool_results=results)
        # Empty strings are falsy → dedup check passes
        assert verdict == LoopVerdict.CONTINUE

    def test_dedup_only_last_n(self, guard):
        # All different except last 3
        results = ["a", "b", "c", "x", "x", "x"]
        verdict = guard.check(tool_results=results)
        assert verdict == LoopVerdict.STOP_DEDUP

    def test_dedup_disabled(self):
        config = LoopConfig(dedup_enabled=False, dedup_window=3)
        g = LoopGuard(config=config)
        results = ["same", "same", "same"]
        assert g.check(tool_results=results) == LoopVerdict.CONTINUE


# ── Layer 5b: Confidence Scoring ─────────────────────────────────

class TestConfidence:
    def test_high_confidence_continues(self, guard):
        guard.record_tool_result("The weather in Beijing is 35°C with sunshine")
        guard.record_tool_result("Population of Tokyo is approximately 14 million")
        assert guard._low_confidence_streak == 0
        # Normal results → should not trigger
        verdict = guard.check()
        assert verdict == LoopVerdict.CONTINUE

    def test_error_result_low_confidence(self, guard):
        guard.record_tool_result("Error: connection refused")
        guard.record_tool_result("Exception: timeout after 30 seconds")
        # Streak of 2 low confidence → STOP
        verdict = guard.check()
        assert verdict == LoopVerdict.STOP_LOW_CONFIDENCE

    def test_not_found_low_confidence(self, guard):
        guard.record_tool_result("No results found for this query")
        guard.record_tool_result("No data available")
        verdict = guard.check()
        assert verdict == LoopVerdict.STOP_LOW_CONFIDENCE

    def test_streak_resets_after_good_result(self, guard):
        guard.record_tool_result("Error: something went wrong")
        guard.record_tool_result("The answer is 42. This is a comprehensive response with multiple sentences providing context and detail.")
        # Streak should have reset to 0
        assert guard._low_confidence_streak == 0

    def test_empty_result_zero_confidence(self, guard):
        guard.record_tool_result("")
        guard.record_tool_result("")
        verdict = guard.check()
        assert verdict == LoopVerdict.STOP_LOW_CONFIDENCE

    def test_custom_confidence_threshold(self):
        config = LoopConfig(confidence_threshold=0.9, low_confidence_streak=1)
        g = LoopGuard(config=config)
        # Even a normal result (estimated 0.8) is below 0.9 threshold
        g.record_tool_result("Normal result with reasonable content length")
        assert g.check() == LoopVerdict.STOP_LOW_CONFIDENCE

    def test_explicit_confidence_override(self, guard):
        guard.record_tool_result("short", confidence=0.9)  # explicitly high
        guard.record_tool_result("also short", confidence=0.9)
        assert guard._low_confidence_streak == 0

    def test_explicit_low_confidence(self, guard):
        guard.record_tool_result("something", confidence=0.1)
        guard.record_tool_result("anything", confidence=0.1)
        verdict = guard.check()
        assert verdict == LoopVerdict.STOP_LOW_CONFIDENCE


# ── Verdict Priority ─────────────────────────────────────────────

class TestVerdictPriority:
    """Stop verdicts should take precedence over WARN."""

    def test_stop_before_warn(self, guard):
        """STOP_MAX_ITERATIONS should fire even if token ratio says WARN."""
        for _ in range(5):
            guard.check(input_tokens=5000)  # 5000/8000 = 0.625 → would be WARN
        # 6th call → STOP_MAX_ITERATIONS (not WARN)
        verdict = guard.check(input_tokens=5000)
        assert verdict == LoopVerdict.STOP_MAX_ITERATIONS

    def test_cancel_takes_priority(self, guard):
        LoopGuard.request_cancel("test-thread")
        # Even first call with no tokens → STOP_CANCELLED
        verdict = guard.check()
        assert verdict == LoopVerdict.STOP_CANCELLED
        LoopGuard.clear_cancel("test-thread")

    def test_stop_token_before_dedup(self, guard):
        ver = guard.check(input_tokens=7000)  # 7000/8000 = 0.875 > 0.8
        assert ver == LoopVerdict.STOP_TOKEN_BUDGET


# ── Summary and Properties ───────────────────────────────────────

class TestSummary:
    def test_summary_after_checks(self, guard):
        guard.check(input_tokens=3000)
        guard.record_tool_result("Test result with enough length for normal confidence")
        summary = guard.summary
        assert summary["iteration"] == 1
        assert summary["cumulative_input_tokens"] == 3000
        assert 0 < summary["token_ratio"] < 1
        assert summary["low_confidence_streak"] == 0
        assert summary["cancelled"] is False

    def test_token_ratio_property(self, guard):
        guard.check(input_tokens=4000)  # 4000/8000 = 0.5
        assert guard.token_ratio == 0.5

    def test_avg_confidence(self, guard):
        guard.record_tool_result("Error: failed", confidence=0.1)
        guard.record_tool_result("Good result with lots of detail and context", confidence=0.8)
        assert 0.4 < guard.avg_confidence < 0.5  # (0.1 + 0.8) / 2 = 0.45

    def test_avg_confidence_empty(self, guard):
        assert guard.avg_confidence == 1.0  # No results → default 1.0
