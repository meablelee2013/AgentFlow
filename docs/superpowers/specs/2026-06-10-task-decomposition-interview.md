# AgentFlow 任务拆解与分配系统 — 面试深度文档

> 📅 2026-06-10 | 面试用完整技术讲解：动机 → 设计决策 → 架构 → 每一层为什么这么做

---

## 目录

1. [问题定义：我们要解决什么](#一问题定义我们要解决什么)
2. [核心设计决策与备选方案对比](#二核心设计决策与备选方案对比)
3. [系统架构全景](#三系统架构全景)
4. [Decompose 节点内部机制](#四decompose-节点内部机制)
5. [能力注册表与调度模型](#五能力注册表与调度模型)
6. [Fan-out 动态并行引擎](#六fan-out-动态并行引擎)
7. [Aggregate 节点：容错与汇总](#七aggregate-节点容错与汇总)
8. [Agent vs Builtin Node：两类执行器](#八agent-vs-builtin-node两类执行器)
9. [Execution Trace：可观测性](#九execution-trace可观测性)
10. [扩展性设计](#十扩展性设计)
11. [与业界方案对比](#十一与业界方案对比)
12. [一句话总结](#十二一句话总结)

---

## 一、问题定义：我们要解决什么

### 1.1 当前 Workflow Builder 的局限

AgentFlow 的 Workflow Builder 是一个可视化工作流编排器。用户可以拖拽节点（Chat、RAG、Search、HTTP API、Database、Code 等 12 种），连线组成 DAG（有向无环图），保存并执行。

**核心问题：执行模型是静态的。**

```
START → Chat → RAG → END
```

每个节点做什么、连到哪，必须在画布上**预先画好**。一个工作流只能处理**一类已知问题**。

### 1.2 真实场景的矛盾

用户输入：

> "帮我调研竞品 X 的最近动态，查一下他们的财务数据，然后写一份 SWOT 分析报告"

这个需求包含三个**不同性质**的子任务：
1. 🔍 搜索竞品新闻 → 需要 Web Search
2. 📡 查财务数据 → 需要调用外部 API
3. 🤖 综合分析生成报告 → 需要 Agent（多步推理）

换一个问题：

> "分析这个数据集，找出异常值，画个图表，给一段业务建议"

子任务又完全不同（代码执行、数据可视化、LLM 分析）。

**核心洞察：不同的问题拆解出完全不同的子任务集合，且子任务的类型在"设计工作流时"是无法预知的。**

### 1.3 我们要达成的四个目标

| 目标 | 说明 | 为什么现有系统做不到 |
|------|------|---------------------|
| **动态拆解** | 不同问题自动拆成不同的子任务（数量、类型、参数全动态） | 现有工作流节点固定 |
| **智能分配** | 每个子任务自动路由到最合适的执行器 | 不存在"路由决策"层 |
| **并行执行** | 无依赖的子任务全部并行跑，最小化总耗时 | 现有执行是顺序的 |
| **结果汇总** | 自动收集所有结果，标记完成/失败，生成整合报告 | 没有汇总层 |

---

## 二、核心设计决策与备选方案对比

### 决策 1：Decompose + Aggregate 两个独立节点 vs 单节点

| 方案 | 描述 | 优势 | 劣势 |
|------|------|------|------|
| A: 单节点 Fan-out Manager | 拆解+分发+汇总全塞一个节点 | 画布最简单 | 内部逻辑过于复杂，无法复用（想单独用汇总能力必须带拆解） |
| B: 只做 Decompose | 拆解后让现有 Chat 节点汇总 | 改动最小 | Chat 缺乏结构化收集能力，不区分成功/失败 |
| **C: Decompose + Aggregate 分离** ✅ | 两个独立节点，职责清晰 | 可独立测试、独立演进、可组合 | 多一个节点类型 |

**选择 C 的原因：**

```
┌─────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────┐
│  START  │────▶│  DECOMPOSE   │────▶│  AGGREGATE   │────▶│ END │
└─────────┘     └──────┬───────┘     └──────▲──────┘     └─────┘
                       │                    │
                       │  动态 Fan-out       │
                       ▼                    │
                 ┌──────────────────────────┐
                 │ search │ api │ agent │... │  ← N 个并行 Worker
                 └──────────────────────────┘
```

- **Decompose = Planner**：只负责"想"，输出结构化子任务列表
- **Aggregate = Reporter**：只负责"收"，不关心子任务怎么执行
- 两者解耦后各自可独立升级（比如 Aggregate 可以换成模板引擎，不影响 Decompose）
- Aggregate 可以接在任何产生多个结果的节点后面，不限于 Decompose

### 决策 2：全局注册表 + 动态 Fan-out vs 画布连线

| 模型 | 描述 | 代表系统 |
|------|------|---------|
| 画布连线固定 Pool | 手动把 N 个节点连到 Decompose，LLM 只在这 N 个里选 | Coze 扣子 |
| **全局注册表 + 动态 Fan-out** ✅ | 系统维护能力池，运行时动态选择 | 我们 |
| 完全自治 Supervisor | Decompose = Supervisor Agent，内部 tool-use 循环 | LangGraph Supervisor |

**为什么不用画布连线？**
1. 灵活性差：连了 3 个节点但任务需要 5 种能力 → 束手无策
2. 画布膨胀：10 个不同类型节点全连到 Decompose → 无法维护

**为什么不用完全自治 Supervisor？**
1. 可观测性差：看不到 Supervisor 内部做了什么决策
2. 调试困难：失败了不知道哪一步出问题
3. 不可复用：Supervisor 的能力无法被其他节点引用

**全局注册表的优势：**
- 能力注册是声明式的（定义一次，到处可用）
- Decompose 配置时只需勾选启用哪些能力
- 新增能力自动可见（加一个 Agent 或节点，注册表自动感知）

### 决策 3：单次拆解（不递归）

**选择：一次 LLM 调用产出所有子任务，不做递归拆解。**

| 方式 | 描述 | 问题 |
|------|------|------|
| 单次拆解 ✅ | 一次 LLM 调用产出完整的子任务列表 | 简单、可预测、易调试 |
| 递归拆解 | Decompose → 检查每个子任务是否还需要拆 → 递归 | "这还需要拆吗？"的判断不可靠；调试极难 |

**理由：**
- 递归拆解的"是否继续拆"判断依赖 LLM，而这个判断本身不稳定
- 单次拆解的失败模式更可控：如果拆解不够细，用户可以调整 prompt，而不是调递归参数
- 复杂的递归树更适合用程序逻辑（而非 LLM）来处理

---

## 三、系统架构全景

### 3.1 三层架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     Presentation Layer (Frontend)                  │
│  ┌─────────────────────┐  ┌────────────────────────────────────┐  │
│  │ NODE_PALETTE        │  │ ConfigDrawer                        │  │
│  │ + Decompose 🔀      │  │ + Decompose 配置：勾选能力、prompt  │  │
│  │ + Aggregate  📊     │  │ + Aggregate 配置：汇总 prompt、容错 │  │
│  └─────────────────────┘  └────────────────────────────────────┘  │
└──────────────────────────────────┬───────────────────────────────┘
                                   │ HTTP REST
┌──────────────────────────────────┼───────────────────────────────┐
│                      Application Layer (FastAPI)                   │
│  ┌──────────────────────────────┼──────────────────────────────┐  │
│  │ GET  /api/v1/capabilities    │  Capability Registry API      │  │
│  │ POST /api/v1/workflows       │  Save workflow (unchanged)    │  │
│  │ POST /api/v1/workflows/{id}/execute                           │  │
│  │   → response includes execution_trace (NEW)                   │  │
│  └──────────────────────────────┼──────────────────────────────┘  │
└──────────────────────────────────┼───────────────────────────────┘
                                   │
┌──────────────────────────────────┼───────────────────────────────┐
│                      Core Layer (LangGraph)                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    WorkflowCompiler                           │  │
│  │  DSL JSON → StateGraph                                       │  │
│  │  ┌───────────┐  ┌───────────┐  ┌──────────────────────────┐ │  │
│  │  │ Decompose │  │  Fanout   │  │ Aggregate                │ │  │
│  │  │ Handler   │─▶│ Executor  │─▶│ Handler                  │ │  │
│  │  │           │  │ (parallel)│  │ (LLM merge + trace)      │ │  │
│  │  └───────────┘  └───────────┘  └──────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐   │
│  │ CapabilityRegistry   │  │ AgentExecutor (ReAct)             │   │
│  │ - builtin_nodes      │  │ - system_prompt + tools           │   │
│  │ - agents             │  │ - Think → Act → Observe loop      │   │
│  └──────────────────────┘  └──────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 关键数据流

```
START → user_query = "调研竞品X并做SWOT分析"
  ↓
DECOMPOSE → LLM 输出: {
    subtasks: [
      {id: "t1", executor: "web_search", input: {query: "竞品X 最新动态"}},
      {id: "t2", executor: "http_api",   input: {url: "https://..."}},
      {id: "t3", executor: "agent:analyst", input: {task: "SWOT分析"}}
    ]
  }
  ↓
Fan-out Executor (asyncio.gather)
  ├── t1 → web_search(query="竞品X 最新动态")     ┐
  ├── t2 → http_api(url="https://...")             ├── 并行
  └── t3 → agent:analyst(task="SWOT分析")          ┘
  ↓
state.subtask_results = {t1: {...}, t2: {...}, t3: {...}}
  ↓
AGGREGATE → LLM 汇总 → {
    aggregated_output: "# SWOT 分析\n...",
    execution_trace: {total: 3, completed: 3, failed: 0}
  }
  ↓
END → 返回 {output, execution_trace}
```

---

## 四、Decompose 节点内部机制

### 4.1 执行流程

```
Step 1: 加载能力清单
  └─ 从 CapabilityRegistry 获取被勾选的 capabilities
  └─ 每个 capability 包含: id, type, label, description, input_schema

Step 2: 构建 LLM Prompt
  └─ System: 能力清单 + 拆解原则 + 输出 Schema
  └─ User: user_query
  └─ Output Format: JSON Schema (Structured Output)

Step 3: LLM 生成结构化输出
  └─ 使用 OpenAI Function Calling / Structured Output
  └─ 强制 LLM 按 JSON Schema 输出
  └─ 校验：每个 executor 必须在可用能力列表中

Step 4: 写入 State
  └─ state.decomposed_tasks = [subtask_1, subtask_2, subtask_3]
  └─ 触发 Fan-out 调度器
```

### 4.2 为什么必须用 Structured Output？

| 方式 | 风险 |
|------|------|
| 自由文本 + 正则解析 | LLM 可能输出不规范 JSON，解析失败 → 整个工作流崩溃 |
| **Structured Output (Function Calling)** ✅ | LLM 被强制按 Schema 输出，格式 100% 可靠 |

**这是一个从实践中得出的教训：任何依赖 LLM 输出的下游逻辑，必须用 Structured Output 约束。**

### 4.3 Prompt 设计哲学

Decompose 的 system prompt 遵循四个原则：

1. **能力驱动的拆解**：不是抽象地"分解任务"，而是"从可用能力出发，找到最匹配的执行器"。这确保每个子任务都有明确的执行路径
2. **最小粒度原则**：拆到每个子任务刚好能被一个 executor 完成。不拆太细（一个 API 调用拆成 5 步），也不拆太粗（搜索+分析+写报告挤在一起）
3. **独立无依赖**：每个子任务必须能独立执行。这是并行 Fan-out 的前提。如果任务 B 需要任务 A 的结果，会在后续版本支持 depends_on
4. **失败隔离**：一个子任务失败不应影响其他子任务

### 4.4 LLM 结构化输出格式

```json
{
  "reasoning": "分析：用户需要调研竞品、获取财务数据、生成报告。三个方向独立无依赖，可并行执行。",
  "subtasks": [
    {
      "id": "subtask_1",
      "description": "搜索竞品X的最新市场动态和新闻",
      "executor": "web_search",
      "input": {
        "query": "竞品X 2026 最新动态 市场份额 产品发布"
      },
      "expected_output": "搜索结果列表，包含标题、URL、摘要"
    },
    {
      "id": "subtask_2",
      "description": "获取竞品X的财务数据",
      "executor": "http_api",
      "input": {
        "url": "https://api.finance.example.com/company/X/financials",
        "method": "GET",
        "headers": {"Authorization": "Bearer {{credential}}"}
      },
      "expected_output": "JSON：收入、利润、增长率、利润率"
    },
    {
      "id": "subtask_3",
      "description": "基于搜索和财务结果，生成SWOT分析报告",
      "executor": "agent:analyst",
      "input": {
        "task": "基于竞品X的市场动态和财务数据，生成一份SWOT分析报告（优势、劣势、机会、威胁）",
        "format": "markdown"
      },
      "expected_output": "Markdown 格式的 SWOT 分析报告"
    }
  ]
}
```

---

## 五、能力注册表与调度模型

### 5.1 Executor 统一接口

```python
class ExecutorCapability:
    """一个可被执行的能力"""
    id: str              # "web_search" | "http_api" | "agent:analyst"
    type: str            # "builtin_node" | "agent"
    label: str           # "Web Search"
    description: str     # "搜索互联网信息，适合调研、查资料、找新闻"
    input_schema: dict   # {"query": {"type": "string", "required": true}, ...}

    # agent-only fields:
    system_prompt: str | None   # Agent 的 system prompt
    tools: list[str] | None     # 可绑定的 tool names
    max_iterations: int = 10    # ReAct 最大循环次数
```

### 5.2 注册表自动发现

系统启动时扫描两类能力：

```python
class CapabilityRegistry:
    def __init__(self):
        self._builtin_nodes: dict[str, BuiltinCapability] = {}
        self._agents: dict[str, AgentCapability] = {}

    def discover_builtin_nodes(self):
        """自动扫描 workflow nodes 目录"""
        # 从 compiler.py 的 handlers dict 获取所有 builtin 节点类型
        # 每个节点自带 input_schema 声明

    def discover_agents(self):
        """从 agent registry / database 获取 Agent 列表"""
        # 用户可以通过 API 注册自定义 Agent
        # 系统预置 agent:analyst, agent:coder, agent:writer 等

    def get(self, capability_id: str) -> ExecutorCapability | None:
        """统一获取接口"""
        return self._builtin_nodes.get(capability_id) or self._agents.get(capability_id)
```

### 5.3 注册表 API

```
GET /api/v1/capabilities
→ {
    "builtin_nodes": [
      {"id": "web_search", "type": "builtin_node", "label": "Web Search",
       "description": "...", "input_schema": {...}},
      {"id": "http_api", "type": "builtin_node", "label": "HTTP API",
       "description": "...", "input_schema": {...}},
      ...
    ],
    "agents": [
      {"id": "agent:analyst", "type": "agent", "label": "Analyst Agent",
       "description": "...", "input_schema": {...}, "tools": [...]},
      ...
    ]
  }
```

前端 Decompose 配置面板调用此 API，展示为 checkbox 列表。

### 5.4 为什么用字符串 ID 而非类引用？

- `capability_id = "web_search"` 而不是 `capability = WebSearchExecutor`
- 原因 1：LLM 只能理解字符串，给它类引用没有意义
- 原因 2：JSON 序列化友好，可以在前端、后端、LLM prompt 之间传递
- 原因 3：扩展新能力只需在注册表加一条记录，不影响现有代码

---

## 六、Fan-out 动态并行引擎

### 6.1 核心挑战

传统 LangGraph 图是**静态编译**的：

```python
graph.add_node("search", search_func)
graph.add_node("chat", chat_func)
graph.add_edge("search", "chat")  # 编译时就确定了
```

但我们的需求是：**运行时才知道有多少个分支、每个调哪个 executor。**

### 6.2 解决方案：asyncio.gather 并行调度

```python
async def execute_fanout(
    subtasks: list[SubTask],
    registry: CapabilityRegistry,
    state: ChatState,
) -> dict[str, SubTask]:
    """动态并行执行所有子任务。返回 {subtask_id: executed_subtask}"""

    async def run_one(st: SubTask) -> SubTask:
        executor = registry.get(st.executor)
        if not executor:
            st.status = "failed"
            st.error = f"Unknown executor: {st.executor}"
            return st

        try:
            start = time.monotonic()
            st.status = "running"
            st.result = await executor.execute(st.input, state)
            st.status = "completed"
        except Exception as e:
            st.status = "failed"
            st.error = str(e)
        finally:
            st.duration_ms = int((time.monotonic() - start) * 1000)
        return st

    # 所有子任务并行执行
    results = await asyncio.gather(
        *[run_one(st) for st in subtasks],
        return_exceptions=True  # ← 关键：一个失败不影响其他
    )

    return {r.id: r for r in results if isinstance(r, SubTask)}
```

### 6.3 为什么用 asyncio.gather 而不是 LangGraph 的 Send？

| 方式 | 优势 | 劣势 |
|------|------|------|
| `asyncio.gather` ✅ | 简单直接，Python 原生；天然支持 return_exceptions | 需要自己管理结果收集 |
| LangGraph `Send()` | LangGraph 原生并行 API | 需要预定义所有可能的 target node；动态数量分支需要 workaround |

**选择 asyncio.gather 的理由：**
- 子任务数量是运行时动态决定的，LangGraph Send 需要编译时知道所有目标节点
- asyncio 的 `return_exceptions=True` 完美满足了"一个失败不影响其他"的容错需求
- 不引入 LangGraph 的额外抽象层，降低维护成本

### 6.4 Compiler 中的处理

```python
# compiler.py — _make_node_func 中新增
async def decompose_func(state: ChatState) -> dict:
    """Decompose 节点：拆解任务 + 触发 Fan-out + 收集结果"""
    # Step 1: LLM 拆解
    subtasks = await decompose_llm_call(state, node_data, capabilities)

    # Step 2: 写入 state
    state["decomposed_tasks"] = subtasks

    # Step 3: 并行 Fan-out
    results = await execute_fanout(subtasks, registry, state)

    # Step 4: 写入结果
    state["subtask_results"] = results

    return {
        "decomposed_tasks": subtasks,
        "subtask_results": results,
        "messages": [AIMessage(content=f"Decomposed into {len(subtasks)} subtasks. "
                                       f"Completed: {sum(1 for r in results.values() if r.status == 'completed')}, "
                                       f"Failed: {sum(1 for r in results.values() if r.status == 'failed')}")],
    }
```

---

## 七、Aggregate 节点：容错与汇总

### 7.1 Partial Success 模式

并行执行的 N 个子任务，任何一个可能因网络、API 限流、超时等原因失败。如果因为 1/5 失败就丢弃 4/5，用户体验极差。

**Partial Success（默认策略）：**

```
3 个子任务:
  ✅ subtask_1 (web_search)   → 成功，5 条搜索结果
  ✅ subtask_2 (http_api)     → 成功，财务数据完整
  ❌ subtask_3 (agent:analyst) → 失败："API rate limit exceeded"

Aggregate 行为:
  → 收集 t1 + t2 的结果
  → LLM prompt 告知："subtask_3 因 API 限流失败。请基于已有的 2 个结果生成报告"
  → 输出报告中标注局限性："以下分析基于部分数据（财务分析因 API 限流未完成）"
  → execution_trace: total=3, completed=2, failed=1
```

### 7.2 容错策略对比

| 策略 | 行为 | 适用场景 |
|------|------|---------|
| `partial`（默认） | 成功的用上，失败的标记，尽力汇总 | 一般业务场景 |
| `strict` | 任一失败 → Aggregate 整体标记失败 | 关键业务流程（如交易） |
| `retry`（未来） | 失败的重试 N 次后再汇总 | 网络不稳定的场景 |

### 7.3 Aggregate 的执行流程

```
Step 1: 等待所有子任务完成（Fan-out 已保证）
Step 2: 读取 state.subtask_results
Step 3: 分类：completed_tasks, failed_tasks
Step 4: 构建 LLM Prompt:
  - System: "你是报告整合专家..."
  - User: 原始需求 + 成功任务的结果 + 失败任务的信息
Step 5: LLM 生成汇总报告
Step 6: 构建 ExecutionTrace
Step 7: 写入 state → 返回
```

### 7.4 LLM 汇总 Prompt 设计要点

```
1. 明确告知 LLM 哪些任务成功了、哪些失败了
2. 要求 LLM "不要编造失败子任务的数据"
3. 要求 LLM 在报告中说明数据局限性
4. 输出格式支持：Markdown（默认）、纯文本、JSON
```

---

## 八、Agent vs Builtin Node：两类执行器

### 8.1 为什么需要 Agent 执行器？

有些子任务不是"一个 API 调用"能解决的。例如"分析竞品优劣"：

```
Think → "需要先看财报，再看产品对标"
  Act → 调用财务 API
  Observe → 得到收入数据
Think → "收入只能说明规模，还需市场份额"
  Act → Web Search: "竞品X 市场份额"
  Observe → 获得 3 篇相关文章
Think → "信息够了，可以写分析"
  Output → 生成 SWOT 报告
```

这就是经典的 **ReAct（Reasoning + Acting）循环** vs Builtin Node 的单次调用。

### 8.2 统一接口、不同实现

```python
class AgentExecutor:
    """Agent 类型执行器"""

    def __init__(self, agent_def: AgentCapability):
        self.system_prompt = agent_def.system_prompt
        self.tools = agent_def.tools  # LangChain Tools
        self.max_iterations = agent_def.max_iterations
        self.llm = get_llm()

    async def execute(self, input: dict, state: ChatState) -> dict:
        """ReAct 循环"""
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=json.dumps(input)),
        ]
        tool_messages = []

        for iteration in range(self.max_iterations):
            response = await self.llm.ainvoke(messages)

            if response.tool_calls:
                # Act → Observe
                for tc in response.tool_calls:
                    result = await execute_tool(tc, self.tools)
                    messages.append(ToolMessage(content=str(result), tool_call_id=tc.id))
                    tool_messages.append({"tool": tc.name, "result": result})
            else:
                # Final answer
                return {
                    "output": response.content,
                    "iterations": iteration + 1,
                    "tool_calls": tool_messages,
                }

        # Max iterations reached → partial result
        return {
            "output": messages[-1].content if messages else "",
            "partial": True,
            "iterations": self.max_iterations,
        }
```

### 8.3 本质区别总结

| 维度 | Builtin Node | Agent |
|------|-------------|-------|
| 执行模式 | 单次调用、一步完成 | Think → Act → Observe 循环 |
| 输入 | 结构化参数 `{url, method}` | 自然语言任务 + tools |
| 输出 | 固定 schema dict | 自由文本 + 结构化结果 |
| 超时 | 秒级 | 分钟级 |
| 配置 | 无需额外配置 | system_prompt + tools 绑定 |
| 适用 | 确定性操作（搜索、API） | 需要多步推理的复杂任务 |

**设计洞察：不要用 Agent 做简单的事，也不要用 Simple Node 做复杂的事。Decompose 的 LLM 需要具备这种判断力。**

---

## 九、Execution Trace：可观测性

### 9.1 设计动机

当工作流执行完后，用户不仅要看到最终报告，还需要知道：
- 拆了几个子任务？
- 每个谁执行的？
- 哪些成功、哪些失败、为什么失败？
- 各耗时多少？

没有 Execution Trace，失败时你不知道该修什么。

### 9.2 数据结构

```json
{
  "execution_id": "exec-abc123",
  "started_at": "2026-06-10T14:30:00Z",
  "total": 3,
  "completed": 2,
  "failed": 1,
  "total_duration_ms": 17120,
  "subtasks": [
    {
      "id": "subtask_1",
      "description": "搜索竞品X最新动态",
      "executor": "web_search",
      "status": "completed",
      "duration_ms": 1230,
      "result": {"items": [{"title": "...", "url": "..."}]},
      "error": null
    },
    {
      "id": "subtask_2",
      "description": "获取财务数据",
      "executor": "http_api",
      "status": "completed",
      "duration_ms": 890,
      "result": {"revenue": 1200000000, "profit": 150000000},
      "error": null
    },
    {
      "id": "subtask_3",
      "description": "生成SWOT分析",
      "executor": "agent:analyst",
      "status": "failed",
      "duration_ms": 15000,
      "result": null,
      "error": "API rate limit exceeded after 3 retries"
    }
  ],
  "aggregated_output": "# 竞品X SWOT分析报告\n\n## 免责声明\n以下分析基于 2/3 子任务的完成结果..."
}
```

### 9.3 前端展示

执行完成后，不仅展示最终报告，还在下方展示一个可折叠的执行追踪卡片：

```
┌─────────────────────────────────────────┐
│ 📊 执行追踪 (3 tasks, 2/3 completed)    │
├─────────────────────────────────────────┤
│ ✅ subtask_1  web_search    1.2s        │
│ ✅ subtask_2  http_api      0.9s        │
│ ❌ subtask_3  agent:analyst 15.0s       │
│    Error: API rate limit exceeded       │
└─────────────────────────────────────────┘
```

---

## 十、扩展性设计

### 10.1 如何加一个新的能力？

加一个 `email_sender` 节点只需要：

1. 在 capability_registry 中注册一条记录
2. 实现 executor（~20 行代码）
3. Decompose 自动感知，下次拆解时 LLM 就能使用

**不需要改 Decompose、Aggregate、Compiler。**

### 10.2 如何加一个新的 Agent？

1. 定义一个 AgentCapability（id, system_prompt, tools）
2. 注册到 agent_registry
3. Decompose 配置面板自动显示

### 10.3 未来扩展路线

| 阶段 | 内容 |
|------|------|
| **当前 Phase 1** | 数据模型 + 注册表 + Decompose + Fan-out + Aggregate + 前端 |
| Phase 2 | Agent 执行器完整实现（ReAct + tool binding） |
| Phase 3 | 子任务间数据依赖（depends_on），拓扑排序执行 |
| Phase 4 | 多层递归拆解（Decompose → Sub-Decompose） |
| Phase 5 | 自定义 Agent 构建器（用户定义 system_prompt + tools） |
| Phase 6 | 子工作流引用（复用已有工作流作为子任务） |

---

## 十一、与业界方案对比

| 维度 | **AgentFlow** | LangGraph Supervisor | Coze 扣子 | Dify | CrewAI |
|------|--------------|---------------------|-----------|------|--------|
| 任务拆解 | ✅ 显式 Decompose 节点，LLM 结构化输出 | 隐式（Supervisor 自然语言路由） | ❌ 不支持动态拆解 | ❌ 手动编排 | ✅ 自然语言定义 Task |
| 能力发现 | ✅ 全局注册表，自动感知 | 依赖 tool binding | 手动连线选择 | 手动连线 | 隐式（Agent role） |
| 并行执行 | ✅ 自动 Fan-out（asyncio.gather） | 手动构图 Send() | 手动连多个分支 | 手动 | ✅ 自动（无依赖即并行） |
| 容错 | ✅ Partial Success（默认） | 需手动实现 | 节点级重试 | ❌ 无 | 需手动实现 |
| 汇总 | ✅ 专用 Aggregate + LLM 智能汇总 | 需手动实现 | Chat 节点 | Chat 节点 | ✅ 内置 |
| 可观测 | ✅ Execution Trace（成功/失败/耗时） | LangSmith（外部） | 有限 | 有限 | 有限 |
| Agent 执行 | ✅ 独立 AgentExecutor（ReAct） | ✅ 原生 | ❌ 插件模式 | ❌ 不支持 | ✅ 原生 |
| 前端可视化 | ✅ ReactFlow 画布 | ❌ 无内置 UI | ✅ 有 | ✅ 有 | ❌ CLI only |

**核心差异化：**

> 把"拆解"和"汇总"提升为一等公民（first-class nodes），而不是隐式行为。
> 这意味着：你可以看见、配置、调试规划过程，而不是把它藏在 Agent 内部的黑盒里。

---

## 十二、一句话总结

**AgentFlow 的任务拆解系统，本质上是一个"自然语言需求 → 结构化计划 → 并行执行 → 汇总报告"的自动流水线。它的核心设计洞察是：将通常隐式存在于 Agent 内部的 Planning 能力，提升为工作流画布上的显式节点，让规划过程可见、可配置、可调试，同时保持执行层的完整可扩展性。**

---

## 附录：关键文件与代码量估算

| 文件 | 类型 | 预计行数 | 核心职责 |
|------|------|---------|---------|
| `capability_registry.py` | 新建 | ~80 | 能力注册/发现/查询 |
| `nodes/decompose.py` | 新建 | ~150 | LLM prompt + structured output + 校验 |
| `nodes/aggregate.py` | 新建 | ~120 | 结果收集 + LLM 汇总 + 容错 |
| `fanout.py` | 新建 | ~60 | asyncio.gather 并行调度 |
| `agent_executor.py` | 新建 | ~100 | ReAct 循环框架 |
| `api/v1/capabilities.py` | 新建 | ~30 | GET /api/v1/capabilities |
| `schema.py` | 修改 | +50 | 新增模型 + 扩展 type literal |
| `compiler.py` | 修改 | +60 | 新增 decompose/aggregate handler |
| `chat_engine.py` | 修改 | +10 | ChatState 扩展 |
| `ConfigDrawer.tsx` | 修改 | +80 | 新增两种配置面板 |
| `WorkflowEditor.tsx` | 修改 | +15 | 新增两种节点类型 |
| **总计** | | **~755** | |

---

> 面试时可以重点讲：为什么拆解和汇总要分开（**关注点分离**）、为什么用全局注册表而不是画布连线（**声明式 > 命令式**）、为什么用 Structured Output 而不是自由文本（**可靠性 > 灵活性**）。这三个决策体现了对 LLM 系统工程的深刻理解。
