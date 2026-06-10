"""
Test cases for the Decompose → Fan-out → Aggregate pipeline.

Run: cd backend && PYTHONPATH=. .venv/bin/python scripts/test_decompose_cases.py

Each test case defines:
  - goal: the input prompt
  - expected: what the decomposition should look like
  - The script runs the actual pipeline and validates the output
"""

import asyncio
import json
import sys
import time
from typing import Any

sys.path.insert(0, ".")

# ── Test Cases ──────────────────────────────────────────────────────

TEST_CASES = [
    {
        "name": "双对象对比调研",
        "goal": "对比分析特斯拉和比亚迪在2025年Q1的财务表现，包括营收、利润率、交付量，并给出投资建议",
        "description": """
用户想要两个公司的对比分析。应该被拆成：
  - 2个搜索子任务（各自搜一家公司的数据，可并行）
  - 1个 chat/agent 子任务（拿到两边数据后做对比分析）
        """,
        "expected_min_subtasks": 2,
        "expected_max_subtasks": 4,
        "expected_executors": ["web_search", "chat"],  # 至少包含这些
        "expected_status": "completed",
    },
    {
        "name": "简单问答（不应过度拆解）",
        "goal": "What is the capital of France?",
        "description": """
一个非常简单的知识问答。不应被过度拆解——1个 chat 子任务就够了。
这是测试 LLM 是否遵循"最小拆解原则"。
        """,
        "expected_min_subtasks": 1,
        "expected_max_subtasks": 2,
        "expected_executors": ["chat"],
        "expected_status": "completed",
    },
    {
        "name": "技术调研 + 报告生成",
        "goal": "Research the latest advancements in quantum computing in 2025, identify the top 3 companies leading the field, and write a summary report with their key breakthroughs.",
        "description": """
技术调研类任务。应该拆成：
  - 1-2个搜索子任务（搜量子计算进展、搜领先公司）
  - 1个 chat 子任务（汇总生成报告）
搜索任务可并行。
        """,
        "expected_min_subtasks": 2,
        "expected_max_subtasks": 4,
        "expected_executors": ["web_search", "chat"],
        "expected_status": "completed",
    },
    {
        "name": "单步搜索",
        "goal": "搜索一下苹果公司今天的最新股价",
        "description": """
单步搜索任务。1个 web_search 就够了。
不应拆成多个子任务。
        """,
        "expected_min_subtasks": 1,
        "expected_max_subtasks": 2,
        "expected_executors": ["web_search"],
        "expected_status": "completed",
    },
    {
        "name": "数据分析 + 写作",
        "goal": "Analyze the pros and cons of remote work vs office work based on recent studies, and write a balanced 500-word article suitable for a corporate blog.",
        "description": """
需要先搜研究数据，再写文章。应拆成：
  - 1个搜索（搜远程办公研究）
  - 1个 chat（基于搜索结果写文章）
        """,
        "expected_min_subtasks": 2,
        "expected_max_subtasks": 3,
        "expected_executors": ["web_search", "chat"],
        "expected_status": "completed",
    },
    {
        "name": "多维度竞品分析",
        "goal": "帮我做一份完整的竞品分析：竞品A和竞品B。需要包括他们的产品功能对比、定价策略、用户评价、市场份额。最后给出我方的竞争策略建议。",
        "description": """
复杂的竞品分析任务。应该拆成多个并行搜索 + 汇总：
  - 多个搜索（各自搜不同维度：功能/定价/评价/份额）
  - 1个 chat（汇总生成策略建议）
        """,
        "expected_min_subtasks": 3,
        "expected_max_subtasks": 6,
        "expected_executors": ["web_search", "chat"],
        "expected_status": "completed",
    },
]

# ── Runner ──────────────────────────────────────────────────────────

async def run_test_case(case: dict) -> dict[str, Any]:
    """Run a single test case through the decompose pipeline."""
    from app.core.workflow.capability_registry import get_capability_registry
    from app.core.workflow.nodes.decompose import DecomposeExecutor
    from app.core.workflow.fanout import execute_fanout
    from app.core.workflow.nodes.aggregate import AggregateExecutor

    registry = get_capability_registry()
    enabled_caps = [c.id for c in registry.list_builtin()]

    goal = case["goal"]
    start_time = time.monotonic()

    # Step 1: Decompose
    decomposer = DecomposeExecutor()
    try:
        subtasks = await decomposer.decompose(
            goal=goal,
            enabled_capabilities=enabled_caps,
            max_subtasks=10,
        )
    except Exception as e:
        return {
            "case": case["name"],
            "goal": goal,
            "status": "error",
            "error": f"Decomposition failed: {e}",
            "subtasks": [],
            "executors_used": [],
            "aggregated_output": "",
            "duration_ms": int((time.monotonic() - start_time) * 1000),
        }

    # Step 2: Fan-out
    state: dict = {"messages": [], "node_outputs": {}}
    results = await execute_fanout(subtasks, state, registry=registry)

    # Step 3: Aggregate
    aggregator = AggregateExecutor()
    aggregate_result = await aggregator.aggregate(
        goal=goal,
        subtask_results=results,
        node_data={"failure_mode": "partial"},
    )

    total_ms = int((time.monotonic() - start_time) * 1000)
    executors_used = [st.executor for st in subtasks]
    trace = aggregate_result.get("execution_trace", {})

    return {
        "case": case["name"],
        "goal": goal,
        "status": "completed",
        "subtask_count": len(subtasks),
        "executors_used": executors_used,
        "subtask_details": [
            {
                "id": st.id,
                "description": st.description,
                "executor": st.executor,
                "status": (results.get(st.id).status if results.get(st.id) else "unknown"),
                "duration_ms": (results.get(st.id).duration_ms if results.get(st.id) else 0),
            }
            for st in subtasks
        ],
        "aggregated_output": aggregate_result.get("aggregated_output", "")[:500],
        "trace_summary": {
            "total": trace.get("total", 0) if isinstance(trace, dict) else 0,
            "completed": trace.get("completed", 0) if isinstance(trace, dict) else 0,
            "failed": trace.get("failed", 0) if isinstance(trace, dict) else 0,
        },
        "duration_ms": total_ms,
    }


def validate_result(result: dict, case: dict) -> list[str]:
    """Validate a test result against expectations. Returns list of issues."""
    issues = []

    if result["status"] == "error":
        issues.append(f"Pipeline failed: {result.get('error')}")
        return issues

    # Check subtask count
    count = result["subtask_count"]
    min_expected = case.get("expected_min_subtasks", 1)
    max_expected = case.get("expected_max_subtasks", 10)
    if count < min_expected:
        issues.append(
            f"Subtask count {count} < expected min {min_expected}. "
            f"Decomposition was too shallow."
        )
    if count > max_expected:
        issues.append(
            f"Subtask count {count} > expected max {max_expected}. "
            f"Over-decomposed."
        )

    # Check executors
    expected_execs = case.get("expected_executors", [])
    used_execs = result["executors_used"]
    for expected in expected_execs:
        if expected not in used_execs:
            issues.append(
                f"Expected executor '{expected}' not used. Used: {used_execs}"
            )

    # Check all subtasks have a status
    for st in result.get("subtask_details", []):
        if st["status"] not in ("completed", "failed", "running", "pending"):
            issues.append(f"Subtask {st['id']} has invalid status: {st['status']}")

    return issues


async def main():
    print("=" * 80)
    print("  AgentFlow — Task Decomposition Test Suite")
    print("=" * 80)
    print()

    results = []
    passed = 0
    failed = 0

    for i, case in enumerate(TEST_CASES):
        print(f"[{i + 1}/{len(TEST_CASES)}] {case['name']}")
        print(f"  Goal: {case['goal'][:100]}...")
        print(f"  Expected: {case['description'].strip()[:150]}...")

        result = await run_test_case(case)
        issues = validate_result(result, case)

        results.append((case, result, issues))

        if not issues:
            print(f"  ✅ PASSED — {result['subtask_count']} subtasks, "
                  f"executors: {result['executors_used']}, "
                  f"{result['duration_ms']}ms")
            passed += 1
        else:
            print(f"  ⚠️  ISSUES: {', '.join(issues)}")
            failed += 1

        # Print subtask details
        for st in result.get("subtask_details", []):
            status_icon = {"completed": "✅", "failed": "❌", "running": "⏳"}.get(st["status"], "❓")
            print(f"    {status_icon} [{st['executor']:15s}] {st['description'][:80]} ({st['duration_ms']}ms)")

        # Print aggregated output preview
        agg = result.get("aggregated_output", "")
        if agg:
            print(f"  📊 Aggregate preview: {agg[:150]}...")

        print()

    # ── Summary ──
    print("=" * 80)
    print(f"  RESULTS: {passed} passed, {failed} issues, {len(TEST_CASES)} total")
    print("=" * 80)

    if failed > 0:
        print("\n⚠️  Issues found:")
        for case, result, issues in results:
            if issues:
                print(f"  [{case['name']}]")
                for issue in issues:
                    print(f"    - {issue}")


if __name__ == "__main__":
    asyncio.run(main())
