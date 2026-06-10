# Task Decomposition & Assignment — Design Spec

> 📅 2026-06-10 | 状态：✅ 已确认 | 依赖：Workflow Builder (feat/workflow-builder)

---

## 一、目标

让 Workflow Builder 具备**智能任务拆解与分发**能力。用户给出一个复杂需求，系统自动：

1. 用 LLM 分析需求并拆解为 N 个独立的子任务
2. 将每个子任务分配给最合适的 executor（简单节点 / Agent）
3. 并行执行所有子任务（无依赖）
4. 收集结果、追踪状态、生成汇总报告

## 二、架构决策

| # | 决策点 | 选择 | 理由 |
|---|--------|------|------|
| 1 | 画布形态 | Decompose + Aggregate 两个独立节点 | 灵活性最高，Aggregate 可单独使用 |
| 2 | 调度模型 | 能力池注册 + 动态 Fan-out | 运行时 LLM 决定拆几个、分配给谁 |
| 3 | 能力池范围 | Built-in Nodes + Agent Nodes，全可扩展 | 长远来看两种都需要，架构留好扩展口 |
| 4 | 能力发现 | 全局注册表，Decompose 勾选即可 | 统一管理，避免每次手动声明 YAML |
| 5 | 汇总策略 | LLM 智能汇总 + 完整追踪 + 部分成功 | 默认容错，失败子任务不影响整体报告 |
| 6 | 阶段策略 | Phase 1 先实现框架 + builtin nodes，Agent 节点框架预留 | 快速验证链路，Agent 能力后续补充 |

## 三、新增节点类型

### 3.1 Decompose 节点

| 属性 | 说明 |
|------|------|
| type | `"decompose"` |
| 输入 | 用户原始需求（来自 start 或其他上游节点） |
| 核心逻辑 | LLM 分析 → 输出结构化 `SubTask[]` |
| 输出 | `subtasks` 数组 → 驱动并行 Fan-out |
| 配置 | 勾选可用能力、自定义分解 prompt、max_subtasks |

**内部执行流程：**

```
1. 加载可用能力清单（从全局注册表 + 节点勾选）
2. 构建 LLM prompt：用户需求 + 能力清单 + 输出格式要求
3. LLM 返回结构化 JSON：{reasoning, subtasks: [{id, description, executor, input}]}
4. 校验：executor 必须在可用清单中
5. 写入 state.decomposed_tasks → 触发 Fan-out
```

**LLM 输出 Schema（Structured Output）：**

```json
{
  "reasoning": "string — 拆解逻辑说明",
  "subtasks": [
    {
      "id": "subtask_1",
      "description": "string — 这个子任务做什么",
      "executor": "string — capability_id，如 web_search | http_api | agent:analyst",
      "input": "object — 传给 executor 的参数",
      "expected_output": "string — 期望产出（帮助 Aggregate 判断）"
    }
  ]
}
```

### 3.2 Aggregate 节点

| 属性 | 说明 |
|------|------|
| type | `"aggregate"` |
| 输入 | 所有子任务的执行结果（自动等待上游全部完成） |
| 核心逻辑 | 收集所有 SubTask 结果 → LLM 汇总 → 生成报告 |
| 输出 | `aggregated_output` + `execution_trace` |
| 配置 | 自定义汇总 prompt、失败策略（partial/strict） |

**容错策略：**

| 策略 | 行为 |
|------|------|
| `partial`（默认） | 收集成功的，标记失败的，LLM 基于已有结果尽力汇总 |
| `strict` | 任一子任务失败 → Aggregate 整体标记失败 |

## 四、全局能力注册表

### 4.1 设计原则

- 系统启动时自动扫描所有可用 Executor
- Executor 分为两类：Builtin Node + Agent
- 每个 Executor 有：id、type、description、input_schema
- Decompose 配置面板从注册表拉取并勾选

### 4.2 Executor 接口

```python
class ExecutorCapability:
    id: str              # "web_search" | "http_api" | "agent:analyst"
    type: str            # "builtin_node" | "agent"
    label: str           # "Web Search"
    description: str     # "搜索互联网信息，适合调研、查资料"
    input_schema: dict   # {"query": {"type": "string", "required": true}}
    # agent only:
    system_prompt: str | None
    tools: list[str] | None
```

### 4.3 注册表 API

```
GET /api/v1/capabilities
→ {
    builtin_nodes: [{id, type, label, description, input_schema}, ...],
    agents: [{id, type, label, description, input_schema, tools}, ...]
  }
```

## 五、运行时数据流

```
START → user_query
  ↓
DECOMPOSE → LLM 输出 {subtasks: [...]}
  ↓
Fan-out Executor（编译器自动处理）
  ├── subtask_1 → dispatch("web_search", {query: "..."})    ┐
  ├── subtask_2 → dispatch("http_api", {url: "...", ...})   ├── 并行
  └── subtask_3 → dispatch("agent:analyst", {task: "..."})  ┘
  ↓
所有结果写入 state.subtask_results[]
  ↓
AGGREGATE → LLM 读取所有结果 → 生成汇总报告
  ↓
END → 返回 {output, execution_trace}
```

## 六、核心数据模型

### 6.1 新增 Pydantic Models

```python
class DecomposeNodeData(BaseModel):
    """Decompose 节点配置"""
    enabled_capabilities: list[str] = []  # ["web_search", "agent:analyst"]
    system_prompt: str = ""               # 自定义拆解 prompt（为空则用默认）
    max_subtasks: int = 10

class AggregateNodeData(BaseModel):
    """Aggregate 节点配置"""
    summary_prompt: str = ""              # 自定义汇总 prompt
    failure_mode: Literal["partial", "strict"] = "partial"

class SubTask(BaseModel):
    """单个子任务"""
    id: str
    description: str
    executor: str                         # capability_id
    input: dict[str, Any] = {}
    expected_output: str = ""
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    result: Any = None
    error: str | None = None
    duration_ms: int = 0

class ExecutionTrace(BaseModel):
    """执行追踪"""
    execution_id: str
    total: int
    completed: int
    failed: int
    subtasks: list[SubTask]
    aggregated_output: str = ""
```

### 6.2 WorkflowNode type 扩展

```python
type: Literal[
    "start", "chat", "rag", "search", "tool",
    "condition", "loop", "hitl", "end",
    "http_api", "database", "code",
    "decompose", "aggregate",    # ← 新增
]
```

### 6.3 ChatState 扩展

```python
class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]
    node_outputs: dict[str, Any]
    # 新增 — 任务拆解专用
    decomposed_tasks: list[SubTask]          # Decompose 产出的子任务列表
    subtask_results: dict[str, SubTask]      # key=subtask.id → 执行结果
    execution_trace: ExecutionTrace | None   # 完整追踪记录
```

## 七、编译器改动

### 7.1 Decompose → Aggregate 的特殊边

当前 Compiler 按静态 edges 创建 node functions。Decompose→Aggregate 之间需要**动态 Fan-out**：

```python
# compiler.py 新增逻辑
def _is_decompose_fanout(edges, nodes) -> bool:
    """检测 Decompose → Aggregate 模式"""
    # 如果存在 decompose → aggregate 的边
    # 且 decompose 产出的 subtasks 是动态的
    # 则这段不创建静态 node functions，改用动态 fan-out

async def _make_fanout_executor(decompose_result, capability_registry):
    """根据 subtasks 动态创建并行执行器"""
    tasks = []
    for subtask in decompose_result.subtasks:
        executor = capability_registry.get(subtask.executor)
        tasks.append(executor.execute(subtask))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

### 7.2 编译策略

```
如果两个节点类型是 decompose → aggregate：
  1. decompose 作为普通 node 函数执行（返回 {subtasks: [...]})
  2. 不创建 aggregate 的普通 node 函数
  3. 在 decompose 执行后插入 fan-out 逻辑
  4. fan-out 完成后 aggregate 执行汇总

如果不是这种模式：
  按现有逻辑正常编译
```

## 八、Agent Executor

Agent 类型的 executor 与 Builtin Node 的本质区别：

| 维度 | Builtin Node | Agent |
|------|-------------|-------|
| 执行模式 | 单次调用、一步完成 | Think → Act → Observe 循环 |
| 输入 | 结构化参数 {url, method} | 自然语言任务 + tools 列表 |
| 输出 | 固定 schema | 自由文本 + 可选结构化结果 |
| 配置 | 无需额外配置 | 需 system_prompt + tools 绑定 |
| 超时 | 秒级 | 分钟级 |

Agent Executor 在 Phase 1 提供框架接口，具体 Agent 类型（analyst、coder 等）在后续 Phase 实现。

## 九、前端改动

### 9.1 新增节点类型

- Decompose 节点：图标 🔀，黄色 (#f59e0b)
- Aggregate 节点：图标 📊，绿色 (#22c55e)

### 9.2 ConfigDrawer 扩展

**Decompose 配置面板：**
- 能力池勾选（从 GET /api/v1/capabilities 拉取）
- 自定义分解 Prompt（textarea）
- 最大子任务数

**Aggregate 配置面板：**
- 自定义汇总 Prompt（textarea）
- 失败策略选择（partial / strict）

### 9.3 NODE_PALETTE 扩展

```typescript
{ type: "decompose", label: "Decompose", icon: GitBranch, color: "#f59e0b" },
{ type: "aggregate", label: "Aggregate", icon: BarChart3, color: "#22c55e" },
```

## 十、API 扩展

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/v1/capabilities` | 获取全局能力注册表 |
| GET | `/api/v1/workflows/{id}/trace` | 获取最近一次执行的 ExecutionTrace |
| POST | `/api/v1/workflows/{id}/execute` | 已有，响应增加 `execution_trace` 字段 |

## 十一、文件变更清单

### 新建文件 (6)

| 文件 | 说明 |
|------|------|
| `backend/app/core/workflow/capability_registry.py` | 全局能力注册表 |
| `backend/app/core/workflow/nodes/decompose.py` | Decompose 执行器 |
| `backend/app/core/workflow/nodes/aggregate.py` | Aggregate 执行器 |
| `backend/app/core/workflow/fanout.py` | 动态并行 Fan-out 调度 |
| `backend/app/core/workflow/agent_executor.py` | Agent 类型 executor 框架 |
| `backend/app/api/v1/capabilities.py` | 能力注册表 API |

### 修改文件 (4)

| 文件 | 改动 |
|------|------|
| `backend/app/core/workflow/schema.py` | 新增 DecomposeNodeData、AggregateNodeData、SubTask、ExecutionTrace；扩展 WorkflowNode.type |
| `backend/app/core/workflow/compiler.py` | 新增 decompose/aggregate handler + 动态 fan-out 逻辑 |
| `backend/app/core/engine/chat_engine.py` | ChatState 新增 decomposed_tasks、subtask_results、execution_trace |
| `frontend/src/components/workflow/ConfigDrawer.tsx` | 新增 Decompose/Aggregate 配置面板 |

### 前端新增/修改 (2)

| 文件 | 改动 |
|------|------|
| `frontend/src/pages/WorkflowEditor.tsx` | NODE_PALETTE 新增 decompose/aggregate；nodeTypes 注册 |
| `frontend/src/api/client.ts` | 新增 getCapabilities() |

## 十二、实施顺序（无依赖可并行）

```
Phase 1: 数据模型 + Schema
  └─ schema.py 新增所有模型 + ChatState 扩展

Phase 2: 能力注册表 + API
  └─ capability_registry.py + capabilities.py

Phase 3: Decompose 执行器
  └─ decompose.py: LLM prompt + structured output + 校验

Phase 4: Fan-out 调度器
  └─ fanout.py: 并行 dispatch + 结果收集

Phase 5: Aggregate 执行器
  └─ aggregate.py: 结果收集 + LLM 汇总 + 容错

Phase 6: Agent Executor 框架
  └─ agent_executor.py: executor interface + 默认实现

Phase 7: Compiler 集成
  └─ compiler.py: 注册新 handler + decompose→aggregate 动态 fan-out

Phase 8: 前端节点 + 配置面板
  └─ WorkflowEditor.tsx + ConfigDrawer.tsx + client.ts
```

Phase 1-2 可并行（无依赖）；Phase 3-5 可部分并行（Decompose 和 Aggregate 独立，Fan-out 依赖两者的 Schema）；Phase 6 独立；Phase 7 依赖 1-6；Phase 8 依赖 Phase 1-2 的 API。

## 十三、测试策略

| 测试层 | 内容 |
|--------|------|
| 单元测试 | SubTask/ExecutionTrace 模型序列化/反序列化 |
| 单元测试 | Decompose prompt 构建 + structured output 解析 |
| 单元测试 | Aggregate 汇总逻辑（正常 + 部分失败 + 全部失败） |
| 单元测试 | Fan-out 并行调度 + asyncio.gather 异常处理 |
| 集成测试 | 完整链路: start → decompose → fan-out → aggregate → end |
| 集成测试 | 部分子任务失败时的容错行为 |
