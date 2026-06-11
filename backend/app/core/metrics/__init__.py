"""Metrics module — Prometheus instrumentation for LLM calls and agent loops."""

from app.core.metrics.llm_metrics import (
    # Decorator
    track_llm_call,
    # Metrics generators
    get_metrics,
    get_llm_stats,
    # Verdict & guard metric helpers
    record_verdict,
    update_guard_metrics,
)

__all__ = [
    "track_llm_call",
    "get_metrics",
    "get_llm_stats",
    "record_verdict",
    "update_guard_metrics",
]
