# AgentFlow 任务拆解与分配 — 端到端全链路走查

> 从用户输入一句话，到系统理解、拆解、分配、执行、汇总展示的完整技术链路。每一步附带核心代码和设计缘由。

---

## 目录

1. [总览：一条任务的完整生命周期](#一总览一条任务的完整生命周期)
2. [第一步：用户输入 → 前端捕获](#二第一步用户输入--前端捕获)
3. [第二步：SSE 流式请求 → 后端接收](#三第二步sse-流式请求--后端接收)
4. [第三步：Decompose — LLM 理解并拆解任务](#四第三步decompose--llm-理解并拆解任务)
5. [第四步：Fan-out — 动态并行分配与执行](#五第四步fan-out--动态并行分配与执行)
6. [第五步：Aggregate — 收集结果并流式汇总](#六第五步aggregate--收集结果并流式汇总)
7. [第六步：前端实时渲染](#七第六步前端实时渲染)
8. [完整数据流图](#八完整数据流图)
9. [关键代码索引](#九关键代码索引)

---

## 一、总览：一条任务的完整生命周期

用户输入：
> "对比分析特斯拉和比亚迪在2025年Q1的财务表现，包括营收、利润率、交付量，并给出投资建议"

系统在 **3-5 秒内**完成以下全链路：

```
┌──────────────────────────────────────────────────────────────────────────┐
│   用户浏览器                          后端服务器                  外部服务  │
│                                                                          │
│   输入 Goal ───────────────────────▶ POST /test-decompose/stream         │
│                                            │                             │
│                                    ┌───────▼──────────┐                  │
│                                    │ ① DECOMPOSE      │──▶ DeepSeek API  │
│                                    │   LLM 理解并拆解  │◀── 结构化JSON    │
│                                    └───────┬──────────┘                  │
│   ◀── SSE: phase=decomposing              │                             │
│   ◀── SSE: decomposed (3 个子任务)        │                             │
│                                            │                             │
│                                    ┌───────▼──────────┐                  │
│                                    │ ② FAN-OUT        │                  │
│                                    │   并行调度         │                  │
│                                    │   ┌────────────┐  │──▶ DDG 搜索 API │
│                                    │   │ web_search │  │──▶ HTTP API     │
│                                    │   │ agent      │  │──▶ DeepSeek+工具│
│                                    │   └────────────┘  │                  │
│   ◀── SSE: subtask_start/done             │                             │
│                                            │                             │
│                                    ┌───────▼──────────┐                  │
│                                    │ ③ AGGREGATE      │──▶ DeepSeek API  │
│                                    │   LLM 流式汇总    │◀── 逐字输出      │
│                                    └───────┬──────────┘                  │
│   ◀── SSE: token...token...token          │                             │
│   ◀── SSE: aggregated + trace             │                             │
│   ◀── SSE: phase=done                     │                             │
└──────────────────────────────────────────────────────────────────────────┘
```

**六个阶段的数捗变化：**

| 阶段 | 后端产出的关键数据 | 前端用户看到什么 |
|------|-------------------|----------------|
| ① 输入 | `goal = "对比分析特斯拉..."` | 输入框 → 点击发送 |
| ② 拆解中 | LLM 调用中... | 🧠 黄色横幅 "正在分析任务..." |
| ③ 拆解完成 | `subtasks = [t1, t2, t3]` | 3 张子任务卡片瞬间出现 |
| ④ 执行中 | 逐个 `subtask_result` 到位 | 每张卡片逐个变绿 + 显示耗时 |
| ⑤ 汇总中 | LLM 逐字输出 token | ✍️ 报告逐字打在屏幕上 |
| ⑥ 完成 | `execution_trace` | 📊 追踪条：✅3 ❌0 3980ms |

---

## 二、第一步：用户输入 → 前端捕获

### 2.1 页面结构

文件：`frontend/src/pages/DecomposeTestChat.tsx`

```tsx
// 底部输入区：一个 textarea + 一个发送按钮
<textarea
  value={goal}
  onChange={e => setGoal(e.target.value)}
  onKeyDown={handleKeyDown}          // Enter 发送，Shift+Enter 换行
  placeholder="Enter a complex goal to decompose..."
  rows={2}
  disabled={isRunning}               // 运行时禁用，防止重复提交
/>

<button
  onClick={handleSubmit}
  disabled={isRunning || !goal.trim()}  // 空内容或运行中不可点
>
  {isRunning ? <Loader2 className="animate-spin" /> : <Send />}
</button>
```

### 2.2 发送逻辑：建立 SSE 连接

```tsx
const handleSubmit = async () => {
  const trimmed = goal.trim();

  // ① 保存用户输入（用于后续在页面上展示"用户说了什么"）
  setLastGoal(trimmed);
  setGoal("");                // 清空输入框，让用户可以输入下一个问题

  // ② 重置所有状态，进入"拆解中"
  reset();
  setPhase("decomposing");

  // ③ 发起 POST 请求，用 ReadableStream 读取 SSE（Server-Sent Events）
  const abortController = new AbortController();
  const resp = await fetch("/api/v1/workflows/test-decompose/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal: trimmed }),
    signal: abortController.signal,   // 支持用户中途取消
  });

  // ④ 逐行读取 SSE 事件流
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;                  // 流结束了

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";       // 最后一行可能不完整，保留到下次

    let currentEvent = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();   // 提取事件名
      } else if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6)); // 解析 JSON 数据
        handleSSE(currentEvent, data);          // 更新 UI
      }
    }
  }
};
```

**为什么要用 `fetch` + `ReadableStream` 而不是 `EventSource`？**

因为 `EventSource` 只支持 GET 请求，而我们需要 POST 把用户的 goal 发送给后端。`fetch` + `ReadableStream` 可以自己解析 SSE 协议。

**为什么要维护 `buffer`？**

TCP 是流式协议，一个 SSE 帧可能被拆成多个网络包。比如 `data: {"text":"hello"}\n\n` 可能第一个包只收到 `da`，第二个包收到 `ta: {"tex` 等等。buffer 确保我们按完整行处理。

### 2.3 SSE 事件 → UI 更新

```tsx
const handleSSE = (event: string, data: Record<string, unknown>) => {
  switch (event) {
    case "phase":        // 阶段切换
      setPhase(data.phase);     // decomposing → executing → aggregating → done
      break;

    case "decomposed":   // LLM 拆解完成
      setSubtasks(data.subtasks);  // 子任务卡片瞬间全部出现
      break;

    case "subtask_start":  // 某个子任务开始执行
      // 对应卡片显示蓝色脉冲动画
      break;

    case "subtask_done":   // 某个子任务执行完成
      // 卡片变绿 + 显示耗时 + 展开可查看结果
      break;

    case "subtask_failed": // 某个子任务执行失败
      // 卡片变红 + 显示错误信息
      break;

    case "token":          // LLM 汇总的每个 token
      setStreamingText(prev => prev + data.text);  // 逐字追加
      break;

    case "aggregated":     // 最终汇总完成
      setAggregated(data);  // 完整报告 + 执行追踪
      break;
  }
};
```

---

## 三、第二步：SSE 流式请求 → 后端接收

### 3.1 API 端点

文件：`backend/app/api/v1/workflow.py`

```python
@router.post("/test-decompose/stream")
async def test_decompose_stream(req: TestDecomposeRequest):
    """SSE 流式端点：拆解 → 并行执行 → 汇总，全程推送进度"""

    async def event_stream():
        # ── 阶段1：拆解 ──
        yield _sse("phase", {"phase": "decomposing", "message": "正在分析任务..."})

        decomposer = DecomposeExecutor()
        subtasks = await decomposer.decompose(goal=req.goal, ...)

        yield _sse("decomposed", {
            "subtasks": [{"id": s.id, "description": s.description, "executor": s.executor}
                          for s in subtasks],
            "count": len(subtasks),
        })

        # ── 阶段2：并行执行 ──
        yield _sse("phase", {"phase": "executing", "message": f"并行执行 {len(subtasks)} 个子任务..."})

        async for event_type, event_data in execute_fanout_sse(subtasks, ...):
            yield _sse(event_type, event_data)   # subtask_start / subtask_done / subtask_failed

        # ── 阶段3：流式汇总 ──
        yield _sse("phase", {"phase": "aggregating", "message": "正在生成汇总报告..."})

        async for token in aggregator.aggregate_stream(goal, subtask_results):
            if isinstance(token, tuple) and token[0] == "__TRACE__":
                trace_info = token[1]        # 哨兵：执行追踪数据
            elif isinstance(token, tuple) and token[0] == "__ANSWER__":
                final_answer = token[1]      # 哨兵：最终答案
            else:
                yield _sse("token", {"text": token})  # 普通文本 token

        yield _sse("aggregated", {"aggregated_output": final_answer, "execution_trace": trace_info})
        yield _sse("phase", {"phase": "done", "message": "完成"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # 禁止 Nginx 缓冲，否则前端收不到逐条事件
        },
    )
```

### 3.2 SSE 协议格式

每个事件的格式：
```
event: <事件类型>
data: <JSON 数据>

```

实际例子：
```
event: phase
data: {"phase":"decomposing","message":"正在分析任务..."}

event: decomposed
data: {"subtasks":[{"id":"task_1","description":"搜索特斯拉Q1财报","executor":"web_search"}],"count":3}

event: subtask_start
data: {"id":"task_1","description":"搜索特斯拉Q1财报","executor":"web_search"}

event: subtask_done
data: {"id":"task_1","status":"completed","result":{...},"duration_ms":1200}
```

**为什么用 SSE 而不是 WebSocket？**

- SSE 是标准 HTTP，不需要额外依赖
- 我们只需要后端→前端的单向推送（前端不需要给后端发消息）
- SSE 浏览器原生支持自动重连
- 比 WebSocket 更简单、更轻量

---

## 四、第三步：Decompose — LLM 理解并拆解任务

### 4.1 核心执行器

文件：`backend/app/core/workflow/nodes/decompose.py`

```python
class DecomposeExecutor:
    def __init__(self, registry=None, model_name=None):
        self.registry = registry or get_capability_registry()
        self.llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model="deepseek-chat",
            temperature=0.2,    # 低温度 = 更确定的输出，减少 JSON 格式错误
        )

    async def decompose(self, goal, enabled_capabilities, max_subtasks=10):
        """核心方法：把 goal 拆成 Subtask 列表"""

        # ── 第一步：构建能力清单 ──
        # 从注册表获取每种能力是什么、能做什么、需要什么参数
        capabilities_desc = self.registry.describe_for_prompt(enabled_capabilities)
        # 输出示例：
        # - `web_search` (builtin_node): 搜索互联网信息，适合调研、查资料
        #   Input: query (string)
        # - `chat` (builtin_node): LLM 推理、分析、写作
        #   Input: prompt (string)

        # ── 第二步：构建 Prompt ──
        system_prompt = DECOMPOSE_SYSTEM_PROMPT
        user_prompt = f"""## 可用能力清单
{capabilities_desc}

## 用户需求
{goal}

请将以上需求拆解为独立的子任务。最多 {max_subtasks} 个。"""

        # ── 第三步：调用 LLM ──
        response = await self.llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        # ── 第四步：解析 LLM 输出的 JSON ──
        plan = self._parse_response(response.content)
        # 处理可能出现的 markdown 代码块包裹（```json ... ```）

        # ── 第五步：校验 ──
        subtasks = self._validate_subtasks(plan["subtasks"], enabled_capabilities, max_subtasks)
        # 确保每个子任务的 executor 在可用列表中（防止 LLM 幻觉）

        return subtasks
```

### 4.2 Decompose 的 System Prompt（完整中文版）

```python
DECOMPOSE_SYSTEM_PROMPT = """你是一个任务拆解专家。你的工作是把用户的复杂需求拆分为可以并行执行的独立子任务。

## 核心原则

1. 每个子任务使用**恰好一种**可用能力
2. 所有子任务必须**完全独立** — 不依赖其他子任务的输出
3. 子任务可以**全部并行**执行（无数据依赖）
4. 每个子任务的输入必须**具体、可执行**

## 如何选择能力

- web_search：搜索互联网信息，适合调研、查资料、找新闻
- http_api：调用外部 HTTP API 获取结构化数据
- chat：LLM 推理、分析、总结、写作、问答
- rag：搜索知识库中的文档和资料
- database：查询结构化数据库
- code：执行 Python 代码进行数据处理或计算
- agent:*：需要多步推理 + 工具使用的复杂任务

## 重要规则

1. **按需拆解** — 简单问题只拆 1 个就够了，不要过度拆解
2. **无依赖** — 如果任务 B 需要任务 A 的结果，就合并为一个任务
3. **最小化数量** — 复杂目标通常 3-5 个即可
4. **输入具体** — 每个子任务的 input 要包含详细、可执行的参数

## 输出格式（严格 JSON）

{
  "reasoning": "拆解策略说明",
  "subtasks": [
    {
      "id": "task_1",
      "description": "这个子任务做什么",
      "executor": "可用清单中的能力ID",  ← 必须从上面选
      "input": {"参数名": "参数值"},
      "expected_output": "期望产出的描述"
    }
  ]
}
"""
```

### 4.3 Prompt 设计的四个核心考量

| 原则 | 在 Prompt 里的体现 | 为什么这样设计 |
|------|-------------------|--------------|
| **能力驱动拆解** | 把可用能力清单注入 prompt | 不是让 LLM 凭空想象"该拆成什么"，而是从已有能力里匹配最佳方案 |
| **最小粒度** | "刚好能被一个 executor 完成" | 避免过度拆解，一个 API 调用不该拆成 5 步 |
| **独立无依赖** | "如果 B 需要 A 的结果，就合并" | 当前版本不做 DAG 依赖图，并行是核心优势 |
| **失败隔离** | 每个子任务独立 try/catch | 一个子任务失败不影响其他 |

### 4.4 LLM 实际输入输出示例

**输入：**
```
## 可用能力清单
- `web_search` (builtin_node): 搜索互联网信息，适合调研、查资料...
  Input: query (string)*
- `chat` (builtin_node): LLM 推理、分析、写作...
  Input: prompt (string)*

## 用户需求
对比分析特斯拉和比亚迪在2025年Q1的财务表现，包括营收、利润率、交付量，并给出投资建议
```

**LLM 输出：**
```json
{
  "reasoning": "需要两公司的Q1财务数据。搜索可并行（无数据依赖），对比分析需综合两个搜索结果。将它们合并为一个 chat 任务以避免依赖。",
  "subtasks": [
    {
      "id": "task_1",
      "description": "搜索特斯拉2025 Q1财报：营收、利润率、交付量",
      "executor": "web_search",
      "input": {
        "query": "Tesla Q1 2025 earnings revenue profit margin vehicle deliveries"
      },
      "expected_output": "特斯拉Q1关键财务数据：营收、利润、交付量"
    },
    {
      "id": "task_2",
      "description": "搜索比亚迪2025 Q1财报：营收、利润率、交付量",
      "executor": "web_search",
      "input": {
        "query": "BYD Q1 2025 financial results revenue deliveries"
      },
      "expected_output": "比亚迪Q1关键财务数据：营收、利润、交付量"
    },
    {
      "id": "task_3",
      "description": "对比两公司Q1财报，给出投资建议",
      "executor": "chat",
      "input": {
        "prompt": "请对比分析特斯拉和比亚迪2025年Q1的财务表现，维度包括营收、利润率、交付量。基于数据对比，给出投资建议。"
      },
      "expected_output": "包含营收对比、利润率对比、交付量对比、投资建议的完整报告"
    }
  ]
}
```

### 4.5 关键的校验逻辑

```python
def _validate_subtasks(self, raw_subtasks, enabled_capabilities, max_subtasks):
    validated = []
    for raw in raw_subtasks[:max_subtasks]:
        executor = raw.get("executor", "")

        # 校验1：executor 必须在可用列表中（防止 LLM 幻觉）
        if executor not in enabled_capabilities:
            continue   # 跳过编造出来的能力

        # 校验2：必须有 id 和 input
        if not raw.get("id"):
            continue

        subtask = SubTask(
            id=raw["id"],
            description=raw.get("description", ""),
            executor=executor,
            input=raw.get("input", {}),
            status="pending",
        )
        validated.append(subtask)

    if not validated:
        raise ValueError(f"所有子任务校验失败。LLM输出: {raw_subtasks}")

    return validated
```

**为什么要做这层校验？** LLM 偶尔会"幻觉"出一个不存在的 executor（比如凭空编一个 `google_search`）。校验层确保只有合法的子任务进入执行阶段。如果所有子任务都被过滤掉了，直接报错让用户知道。

---

## 五、第四步：Fan-out — 动态并行分配与执行

### 5.1 调度器的设计

文件：`backend/app/core/workflow/fanout.py`

核心思路：拿到 N 个子任务 → 每个匹配一个 executor → **全部并行跑**（`asyncio.gather`）→ 每个完成时推送 SSE 事件。

```python
async def execute_fanout_sse(subtasks, state, registry=None):
    """
    输入: [SubTask("搜索特斯拉", executor="web_search"), SubTask("搜索比亚迪", executor="web_search"), ...]
    输出: SSE 事件流 (subtask_start → subtask_done/failed)
    """

    async def run_one(st: SubTask):
        """执行单个子任务，返回 SSE 事件流"""

        # ① 先告诉前端：这个任务开始了
        yield ("subtask_start", {
            "id": st.id,
            "description": st.description,
            "executor": st.executor,
        })

        start = time.monotonic()

        # ② 查找 executor
        capability = registry.get(st.executor)
        if not capability:
            yield ("subtask_failed", {
                "id": st.id,
                "error": f"未知的 executor: {st.executor}",
                "duration_ms": ...,
            })
            return

        # ③ 执行
        try:
            if capability.type == "builtin_node":
                result = await _execute_builtin(st.executor, st.input, state)
            elif capability.type == "agent":
                result = await _execute_agent(st.executor, st.input, state, capability)

            yield ("subtask_done", {
                "id": st.id,
                "status": "completed",
                "result": result,
                "duration_ms": int((time.monotonic() - start) * 1000),
            })
        except Exception as e:
            yield ("subtask_failed", {
                "id": st.id,
                "status": "failed",
                "error": str(e),
                "duration_ms": ...,
            })

    # 所有子任务同时启动
    # asyncio.gather 天然支持并行 —— 三个协程同时跑
    tasks = [run_one(st) for st in subtasks]
    # ...收集所有 generator 的事件
```

### 5.2 为什么用 asyncio.gather？

| 方案 | 适合场景 | 我们为什么选/不选 |
|------|---------|-----------------|
| `asyncio.gather` ✅ | 运行时动态数量 | 子任务数量是 LLM 运行时决定的，编译时不知道有几个分支 |
| LangGraph `Send()` | 所有目标在编译时已知 | 需要预定义所有可能的 target node，不支持动态数量 |
| `for` 循环顺序执行 | 简单，但有依赖 | 丧失了并行优势，3 个任务需要累加时间而非取最大值 |

### 5.3 Builtin Node 的执行逻辑

```python
async def _execute_builtin(executor_id, input_data, state):
    """根据 executor_id 调度到具体实现"""

    if executor_id == "web_search":
        # 调用 DuckDuckGo（默认，免费无限制）
        from app.core.tool.builtins.search_backends import get_search_backend
        backend = get_search_backend()    # 默认 DuckDuckGo
        results = await backend.search(input_data["query"], max_results=5)
        return {
            "items": [{"title": r.title, "url": r.url, "snippet": r.snippet}
                       for r in results],
            "count": len(results),
        }

    elif executor_id == "chat":
        llm = ChatOpenAI(model="deepseek-chat", temperature=0.7)
        response = await llm.ainvoke([
            HumanMessage(content=input_data["prompt"]),
        ])
        return {"content": response.content}

    elif executor_id == "http_api":
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method=input_data.get("method", "GET"),
                url=input_data["url"],
            )
        return {"status": resp.status_code, "body": resp.json()}

    # 其他 builtin: rag, database, code（均有 placeholder 实现）
```

### 5.4 Agent Node 的执行逻辑

与 Builtin 不同，Agent 不是"一次调用就完成"，而是 **Think → Act → Observe** 循环。

文件：`backend/app/core/workflow/agent_executor.py`

```python
class AgentExecutor:
    async def execute(self, task: str, state: dict) -> dict:
        messages = [
            SystemMessage(content=self.system_prompt),     # Agent 的"人设"
            HumanMessage(content=f"Task: {task}"),         # 要完成的任务
        ]

        tool_call_log = []

        # ReAct 循环：最多 N 轮
        for iteration in range(self.max_iterations):
            response = await self.llm.ainvoke(messages)
            messages.append(response)

            if response.tool_calls:
                # 有工具调用 → 执行工具 → 把结果喂回 LLM
                for tc in response.tool_calls:
                    tool_result = await self._execute_tool(tc)
                    messages.append(ToolMessage(content=str(tool_result)))
                    tool_call_log.append({"tool": tc["name"], "result": tool_result})
            else:
                # 没有工具调用 → 这是最终回答
                return {
                    "output": response.content,
                    "iterations": iteration + 1,
                    "tool_calls": tool_call_log,
                }

        # 达到最大迭代次数 → 返回部分结果
        return {"output": "达到最大迭代次数", "partial": True}
```

**Agent vs Builtin 的本质区别：**

| 维度 | Builtin Node | Agent Node |
|------|-------------|-----------|
| 执行模式 | 一次调用，一步完成 | Think → Act → Observe 循环 |
| 输入 | 结构化参数 `{url, method}` | 自然语言任务描述 |
| 输出 | 固定 schema 的 dict | 自由文本 + 工具调用日志 |
| 耗时 | 秒级（1-3s） | 分钟级（10-60s+） |
| 适用场景 | 搜索、API 调用、简单问答 | 多步推理、数据分析、复杂调研 |

### 5.5 并行执行的时序

```
时间轴 →

task_1 (web_search):  ████████████░░░░░░░░░░░░░░░░  1200ms ✅ 完成
task_2 (web_search):  ██████████░░░░░░░░░░░░░░░░░░  980ms  ✅ 完成
task_3 (chat):        ██████████████████░░░░░░░░░░░  1800ms ✅ 完成

总耗时 = max(1200, 980, 1800) = 1800ms
而非 1200 + 980 + 1800 = 3980ms

节省时间 = 3980 - 1800 = 2180ms = 节省 55%
```

---

## 六、第五步：Aggregate — 收集结果并流式汇总

### 6.1 流式汇总执行器

文件：`backend/app/core/workflow/nodes/aggregate.py`

```python
class AggregateExecutor:
    async def aggregate_stream(self, goal, subtask_results):
        """
        流式生成汇总报告。
        每个 LLM 输出的 token 通过 async generator 产出，发送给前端。
        """

        # ① 分类：哪些成功、哪些失败
        completed = [st for st in subtask_results.values() if st.status == "completed"]
        failed = [st for st in subtask_results.values() if st.status == "failed"]

        # ② 把子任务结果格式化为文本
        results_text = self._format_results(subtask_results)
        # 示例输出：
        # ### task_1: 搜索特斯拉Q1财报
        # Executor: web_search | Duration: 1200ms
        # {"items": [{"title": "Tesla Q1 2025...", "url": "...", "snippet": "..."}]}

        # ③ 构建 Prompt（注意：用纯 Markdown 输出，不用 JSON 包裹）
        user_prompt = f"""## 原始需求
{goal}

## 已完成的子任务结果
{results_text}

{f"## 失败的子任务\n{self._format_failed(failed)}" if failed else ""}

请综合以上所有结果，生成一份完整的汇总报告。直接使用 Markdown 格式输出。"""

        # ④ 流式调用 LLM
        llm = ChatOpenAI(
            model="deepseek-chat",
            temperature=0.3,
            streaming=True,        # ← 开启流式模式
        )
        full_text = ""
        async for chunk in llm.astream([
            SystemMessage(content=AGGREGATE_STREAM_PROMPT),
            HumanMessage(content=user_prompt),
        ]):
            if chunk.content:
                full_text += chunk.content
                yield chunk.content          # ← 每个 token 立即传给调用方

        # ⑤ 构建执行追踪
        trace = ExecutionTrace(
            total=len(subtask_results),
            completed=len(completed),
            failed=len(failed),
            subtasks=list(subtask_results.values()),
            aggregated_output=full_text,
        )
        yield ("__TRACE__", trace.model_dump())     # 哨兵：执行追踪
        yield ("__ANSWER__", full_text)              # 哨兵：最终答案
```

### 6.2 为什么要两套 Prompt？

| 场景 | Prompt 类型 | 输出格式 | 为什么 |
|------|-----------|---------|--------|
| **流式汇总** | Markdown 直出 | `## 对比分析报告\n\n### 营收对比...` | 前端逐字展示，用户看到 LLM "打字"的过程 |
| **非流式汇总** | JSON 包裹 | `{"answer":"## 对比分析...", "completeness_reason":"..."}` | 需要结构化的质量评估 |

```python
# 流式 Prompt 的核心指令：
AGGREGATE_STREAM_PROMPT = """
- 直接输出 Markdown，不要 JSON 包裹
- 不要"Here is the report"这类开场白，直接从内容开始
- 如果某些子任务失败了，标注局限性但不编造数据
"""
```

### 6.3 Partial Success 容错机制

```
假设 3 个子任务中 1 个失败：

  ✅ task_1 (web_search)  → 成功，返回 5 条搜索结果
  ✅ task_2 (web_search)  → 成功，返回 3 条搜索结果
  ❌ task_3 (chat)        → 失败："API rate limit exceeded"

Aggregate 的处理逻辑：

1. 只把 task_1 和 task_2 的结果传给 LLM
2. 在 prompt 中明确告知：
   "⚠️ task_3 因 API 限流失败，无法生成 chat 分析。
    请基于已有的 2 个搜索结果生成报告，标注数据局限性。"

3. LLM 生成的报告开头：
   "## 免责声明
   以下分析基于 2/3 子任务的完成结果。chat 分析因 API 限流未完成。"

4. ExecutionTrace 准确记录：
   {total: 3, completed: 2, failed: 1}
```

**为什么默认 partial 模式？** 因为 3 个任务中 1 个失败就丢弃 2 个成功结果，用户体验极差。Partial success 让用户至少能拿到"部分可用的"报告。

---

## 七、第六步：前端实时渲染

### 7.1 阶段横幅：一眼看到当前进度

```tsx
function PhaseBanner({ phase, subtaskCount }) {
  // phase 的可能值：decomposing | executing | aggregating | done | error

  const configs = {
    decomposing:  { icon: Brain,  label: "正在分析任务，拆解子任务...",      color: "text-amber-600", bg: "bg-amber-50" },
    executing:    { icon: Zap,    label: `并行执行 ${n} 个子任务中...`,      color: "text-blue-600",  bg: "bg-blue-50" },
    aggregating:  { icon: FileText, label: "正在汇总生成报告...",            color: "text-emerald-600", bg: "bg-emerald-50" },
    done:         { icon: CheckCircle2, label: "完成",                      color: "text-emerald-600", bg: "bg-emerald-50" },
    error:        { icon: XCircle, label: "发生错误",                       color: "text-red-600", bg: "bg-red-50" },
  };

  const cfg = configs[phase];
  const spinning = ["decomposing", "executing", "aggregating"].includes(phase);

  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${cfg.bg}`}>
      {spinning ? <Loader2 className="animate-spin" /> : <cfg.icon />}
      <span>{cfg.label}</span>
    </div>
  );
}
```

**视觉效果：**
- 🟡 拆解中 → 黄色横幅 + 持续转圈
- 🔵 执行中 → 蓝色横幅 + 持续转圈
- 🟢 汇总中 → 绿色横幅 + 持续转圈
- ✅ 完成 → 绿色横幅 + 对勾

### 7.2 子任务卡片：三态动画

```tsx
function SubtaskCard({ st, phase }) {
  // 每个子任务卡片有三种状态，对应不同颜色和动画：

  // pending (等待中)         → 灰色边框，时钟图标
  // running (执行中)         → 蓝色边框 + animate-pulse 脉冲动画，旋转图标
  // completed (已完成)       → 绿色边框，对勾图标，显示耗时
  // failed (失败)            → 红色边框，叉号图标，显示错误

  const statusStyle = {
    pending:   "border-gray-200 bg-white",
    running:   "border-blue-200 bg-blue-50/20 animate-pulse",
    completed: "border-emerald-200 bg-emerald-50/20",
    failed:    "border-red-200 bg-red-50/20",
  }[st.status];

  return (
    <div className={`border rounded-xl ${statusStyle}`}>
      {/* 点击展开查看 Input / Result / Error */}
      <button onClick={() => setExpanded(!expanded)}>
        <StatusIcon />
        <span>{st.description}</span>
        <span className="font-mono text-[10px]">{st.executor}</span>
        {st.duration_ms > 0 && <span>{st.duration_ms}ms</span>}
      </button>

      {expanded && st.result != null && (
        <pre>{safeStringify(st.result)}</pre>     // JSON 格式化展示
      )}
      {expanded && st.error && (
        <p className="text-red-500">{st.error}</p>  // 错误信息
      )}
    </div>
  );
}
```

### 7.3 流式文字：逐字打字展示

```tsx
{/* 汇总阶段：实时展示 LLM 正在生成的报告 */}
{streamingText && (
  <div>
    <div className="flex items-center gap-2">
      <BarChart3 className="text-emerald-500" />
      <span className="text-xs font-semibold">实时报告</span>
      {phase === "aggregating" && <Loader2 className="animate-spin text-emerald-400" />}
    </div>
    <div className="bg-white border border-emerald-200 rounded-xl p-5">
      <div className="text-sm whitespace-pre-wrap text-ink/80">
        {streamingText}
        {/* 初次加载时显示闪烁光标效果 */}
        {phase === "aggregating" && !streamingText && (
          <span className="italic text-gray-300">正在生成报告...</span>
        )}
      </div>
    </div>
  </div>
)}
```

### 7.4 执行追踪条

```tsx
{/* 底部：一目了然的执行统计 */}
{trace && (
  <div className="bg-gray-50 border rounded-xl p-4 flex items-center gap-4 text-xs">
    <CheckCircle2 size={12} className="text-emerald-500" />
    <span className="font-mono text-emerald-600">{trace.completed} 完成</span>

    <XCircle size={12} className="text-red-400" />
    <span className="font-mono text-red-500">{trace.failed} 失败</span>

    <span className="text-gray-300">|</span>
    <span className="text-gray-400">{trace.total} 个子任务</span>

    <Clock size={12} className="text-gray-400 ml-auto" />
    <span className="font-mono text-gray-500">{trace.total_duration_ms}ms 总耗时</span>
  </div>
)}
```

### 7.5 用户输入气泡

```tsx
{/* 顶部：右对齐的深色气泡显示用户输入了什么 */}
{lastGoal && phase !== "idle" && (
  <div className="flex justify-end">
    <div className="max-w-[80%] bg-ink text-white px-4 py-3 rounded-2xl rounded-br-md">
      <p className="text-xs font-medium opacity-60 mb-0.5">Goal</p>
      <p className="text-sm">{lastGoal}</p>
    </div>
  </div>
)}
```

---

## 八、完整数据流图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     一条任务从输入到展示的完整数据流                         │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  前端状态变化                            后端 State 变化                   │
│  ────────────                            ──────────────                   │
│                                                                          │
│  ① goal = "对比分析..."               ┌─────────────────┐                │
│     用户点击发送                        │ POST /stream    │                │
│     setLastGoal(goal)                  │ Body: {goal}    │                │
│     setPhase("decomposing")           └────────┬────────┘                │
│                                                │                         │
│  ② 黄色横幅 + 转圈                  ┌───────────▼───────────┐            │
│     用户气泡显示 goal                 │ DecomposeExecutor     │            │
│                                      │ .decompose(goal)     │            │
│  ③ subtasks = [                     │   → LLM structured    │            │
│       {id:"t1", executor:            │     output            │            │
│        "web_search",                 │   → validate()       │            │
│        status:"pending"},            │                       │            │
│       {id:"t2", ...},               │ subtasks = [          │            │
│       {id:"t3", ...}                │   SubTask(id="t1"),   │            │
│     ]                                │   SubTask(id="t2"),   │            │
│     3 张灰色卡片出现                  │   SubTask(id="t3"),   │            │
│                                      │ ]                     │            │
│  ④ phase = "executing"              └───────────┬───────────┘            │
│     蓝色横幅                                       │                      │
│                                               │                          │
│  ⑤ t1: pending → running           ┌───────────▼───────────┐            │
│     (蓝色脉冲动画)                    │ execute_fanout_sse()  │            │
│                                      │                       │            │
│  ⑥ t1: running → completed         │  run_one(t1) ─────────▶ DDG API   │
│     (绿色 + 1200ms)                  │  run_one(t2) ─────────▶ DDG API   │
│     t2: running → completed         │  run_one(t3) ─────────▶ DeepSeek  │
│     (绿色 + 980ms)                   │                       │            │
│     t3: running → completed         │  全部并行！             │            │
│     (绿色 + 1800ms)                  └───────────┬───────────┘            │
│                                                │                         │
│  ⑦ phase = "aggregating"           ┌───────────▼───────────┐            │
│     绿色横幅 + 实吿报告框             │  AggregateExecutor    │            │
│                                      │  .aggregate_stream() │            │
│  ⑧ "## 对比分析报告\n\n            │   → LLM astream()     │            │
│      ### 营收对比\n                  │   → yield token       │            │
│      特斯拉: $X亿\n                  │   → yield token       │            │
│      比亚迪: $X亿\n                  │   → ...               │            │
│      ### 投资建议\n                  └───────────┬───────────┘            │
│      ..."                                         │                      │
│     逐字出现在打字框中                              │                      │
│                                                │                         │
│  ⑨ 完整报告 + 追踪条                 ┌───────────▼───────────┐            │
│     ✅ 3 完成  ❌ 0 失败             │  ExecutionTrace       │            │
│     3980ms 总耗时                    │   {total:3,           │            │
│                                      │    completed:3,       │            │
│  ⑩ phase = "done"                   │    failed:0,          │            │
│     绿色 Complete 横幅               │    total_duration_ms} │            │
│                                      └───────────────────────┘            │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 九、关键代码索引

| 步骤 | 文件路径 | 核心类/函数 | 大致行数 |
|------|---------|------------|---------|
| ① 用户输入捕获 | `frontend/src/pages/DecomposeTestChat.tsx` | `handleSubmit()` | ~50 行 |
| ② SSE 事件解析 | `frontend/src/pages/DecomposeTestChat.tsx` | `handleSSE()` | ~60 行 |
| ③ 后端 SSE 端点 | `backend/app/api/v1/workflow.py` | `test_decompose_stream()` | ~100 行 |
| ④ 任务拆解 | `backend/app/core/workflow/nodes/decompose.py` | `DecomposeExecutor.decompose()` | ~80 行 |
| ⑤ LLM 拆解 Prompt | `backend/app/core/workflow/nodes/decompose.py` | `DECOMPOSE_SYSTEM_PROMPT` | ~50 行 |
| ⑥ 输出校验 | `backend/app/core/workflow/nodes/decompose.py` | `_validate_subtasks()` | ~30 行 |
| ⑦ 能力注册表 | `backend/app/core/workflow/capability_registry.py` | `CapabilityRegistry` | ~100 行 |
| ⑧ 并行调度器 | `backend/app/core/workflow/fanout.py` | `execute_fanout_sse()` | ~80 行 |
| ⑨ Builtin 执行 | `backend/app/core/workflow/fanout.py` | `_execute_builtin()` | ~90 行 |
| ⑩ Agent 执行 | `backend/app/core/workflow/agent_executor.py` | `AgentExecutor.execute()` | ~60 行 |
| ⑪ 流式汇总 | `backend/app/core/workflow/nodes/aggregate.py` | `AggregateExecutor.aggregate_stream()` | ~70 行 |
| ⑫ 容错处理 | `backend/app/core/workflow/nodes/aggregate.py` | Partial Success 逻辑 | ~30 行 |
| ⑬ 前端阶段横幅 | `frontend/src/pages/DecomposeTestChat.tsx` | `PhaseBanner()` | ~25 行 |
| ⑭ 前端子任务卡片 | `frontend/src/pages/DecomposeTestChat.tsx` | `SubtaskCard()` | ~50 行 |
| ⑮ 前端流式展示 | `frontend/src/pages/DecomposeTestChat.tsx` | 流式文字 box | ~15 行 |

### 核心数据模型

| 模型 | 所在文件 | 用途 |
|------|---------|------|
| `SubTask` | `backend/.../schema.py` | 单个子任务：id, executor, input, status, result, error, duration_ms |
| `ExecutionTrace` | `backend/.../schema.py` | 完整追踪：total, completed, failed, subtasks[], aggregated_output |
| `DecomposeNodeData` | `backend/.../schema.py` | Decompose 节点配置：enabled_capabilities, system_prompt, max_subtasks |
| `AggregateNodeData` | `backend/.../schema.py` | Aggregate 节点配置：summary_prompt, failure_mode |
| `ExecutorCapability` | `backend/.../capability_registry.py` | 能力描述：id, type, label, description, input_schema, tools |
