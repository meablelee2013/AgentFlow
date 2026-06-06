# Tool System 技术详解

> AgentFlow 工具系统基于 LangGraph + OpenAI Function Calling 标准，支持 Agent 自主调用外部工具。

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────┐
│                      Agent API                          │
│                  POST /api/v1/agent                      │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│                AgentGraphEngine                          │
│                                                         │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐       │
│   │Supervisor│────▶│   LLM    │────▶│Tool Node │       │
│   │  Node    │◀────│  (chat)  │◀────│(execute) │       │
│   └──────────┘     └──────────┘     └──────────┘       │
│        │                 │                               │
│        │         tool_calls?                             │
│        │    ┌─────────┴─────────┐                       │
│        │    │ yes → tools_node  │                       │
│        │    │ no  → END         │                       │
│        │    └───────────────────┘                       │
└────────┼────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                   ToolRegistry                           │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │Calculator │ │ DateTime │ │WebSearch │ │HTTP Req  │  │
│  │  Tool    │ │  Tool    │ │  Tool    │ │  Tool    │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 二、BaseTool — 工具接口设计

### 2.1 类层次

```python
class BaseTool(ABC):
    name: str = ""              # 工具名称，LLM 通过此名调用
    description: str = ""       # 告诉 LLM 这工具做什么
    parameters: dict = {...}    # JSON Schema，定义输入参数
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult: ...
    
    def to_openai_schema(self) -> dict: ...  # 转为 OpenAI function calling 格式
```

### 2.2 为什么用 JSON Schema 定义参数？

LLM 需要**结构化描述**才能正确调用工具。假设我们定义 Calculator：

```python
class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate a mathematical expression."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression, e.g. '2 + 3 * 4'"
            }
        },
        "required": ["expression"]
    }
```

这个 schema 会转成 OpenAI Function Calling 格式发给 LLM：

```json
{
    "type": "function",
    "function": {
        "name": "calculator",
        "description": "Evaluate a mathematical expression.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression..."}
            },
            "required": ["expression"]
        }
    }
}
```

LLM 收到这个 schema 后就知道：**"有一个叫 calculator 的工具，需要一个 expression 参数，类型是 string"**。当用户问 "2+2 等于几"，LLM 会返回：

```json
{
    "tool_calls": [{
        "name": "calculator",
        "arguments": {"expression": "2+2"}
    }]
}
```

### 2.3 ToolResult — 统一返回格式

```python
@dataclass
class ToolResult:
    success: bool           # 工具是否执行成功
    output: str             # 执行结果（给 LLM 看）
    error: str | None       # 错误信息
    metadata: dict          # 附加数据（日志、统计等）

    def to_llm_message(self) -> str:
        """格式化为 LLM 能理解的消息"""
        if self.success:
            return self.output
        return f"Error: {self.error}"
```

设计要点：**成功和失败都返回字符串**。LLM 看不懂异常堆栈，只能理解自然语言。所以失败时返回 `"Error: division by zero"` 而不是直接抛异常。

---

## 三、ToolRegistry — 工具注册中心

### 3.1 Registry Pattern

```python
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}   # name → tool instance
    
    def register(self, tool: BaseTool):         # 注册工具
        self._tools[tool.name] = tool
    
    def get_openai_schemas(self) -> list[dict]:  # 生成 LLM 可用的 schema 列表
        return [t.to_openai_schema() for t in self._tools.values()]
    
    async def execute(self, name: str, **kwargs) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(False, "", f"Tool '{name}' not found")
        return await tool.execute(**kwargs)
```

### 3.2 添加一个新工具的步骤

```python
# Step 1: 定义工具类
class WeatherTool(BaseTool):
    name = "get_weather"
    description = "Get current weather for a city"
    parameters = {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name"}
        },
        "required": ["city"]
    }
    
    async def execute(self, city: str = "", **kwargs) -> ToolResult:
        # 这里接真实天气 API
        return ToolResult(success=True, output=f"The weather in {city} is sunny, 25°C")

# Step 2: 注册
registry = ToolRegistry()
registry.register(WeatherTool())

# Step 3: LLM 自动发现并使用
# 用户："北京天气怎么样？"
# LLM → tool_call: get_weather(city="北京")
# Tool → "The weather in 北京 is sunny, 25°C"
# LLM → "北京今天晴天，25度"
```

**核心价值**：新增工具不需要改任何 Agent 引擎代码。LLM 自动从 schema 发现新工具。

---

## 四、ReAct Tool Loop — Agent 如何循环调用工具

### 4.1 ReAct 模式

**ReAct** = **Re**asoning + **Act**ing。Agent 在"思考"和"行动"之间循环：

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│  User: "sqrt(144) + 5 等于多少？"                     │
│                                                      │
│  Step 1: LLM 推理 → 决定调用工具                       │
│  tool_call: calculator("sqrt(144)")                   │
│                                                      │
│  Step 2: Tool 执行 → 返回结果                          │
│  result: "12.0"                                       │
│                                                      │
│  Step 3: LLM 推理 → 还需要再算                          │
│  tool_call: calculator("12 + 5")                      │
│                                                      │
│  Step 4: Tool 执行 → 返回结果                          │
│  result: "17.0"                                       │
│                                                      │
│  Step 5: LLM 推理 → 有答案了，不需要工具了               │
│  final: "sqrt(144) + 5 = 17"                          │
│                                                      │
└──────────────────────────────────────────────────────┘
```

### 4.2 LangGraph 实现

```python
class AgentGraphEngine:
    MAX_TOOL_ITERATIONS = 5  # 防止无限循环
    
    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        workflow.add_node("agent", self._agent_node)      # LLM 推理节点
        workflow.add_node("tools", self._tools_node)      # 工具执行节点
        
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges(
            "agent",              # 从 agent 节点出发
            self._should_continue, # 路由函数
            {
                "tools": "tools",  # 有 tool_calls → 执行工具
                "end": END         # 没 tool_calls → 结束
            }
        )
        workflow.add_edge("tools", "agent")  # 工具执行完 → 回到 LLM 继续推理
```

### 4.3 路由函数 — `_should_continue`

```python
def _should_continue(self, state: AgentState) -> str:
    last_msg = state["messages"][-1]
    
    # 检查最后一条消息是否有 tool_calls
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        # 检查是否超过最大迭代次数
        tool_count = sum(1 for m in state["messages"] if isinstance(m, ToolMessage))
        if tool_count >= self.MAX_TOOL_ITERATIONS:
            return "end"     # 防止死循环
        return "tools"       # 继续执行工具
    
    return "end"             # LLM 给出了最终答案，结束
```

### 4.4 工具执行节点

```python
async def _tools_node(self, state: AgentState) -> dict:
    last_msg = state["messages"][-1]
    tool_messages = []
    
    for tc in last_msg.tool_calls:
        name = tc["name"]       # 工具名
        args = tc["args"]       # 参数（LLM 已填好）
        
        result = await self.tool_registry.execute(name, **args)
        
        tool_messages.append(ToolMessage(
            content=result.to_llm_message(),  # "12.0" 或 "Error: ..."
            tool_call_id=tc["id"],
            name=name,
        ))
    
    return {"messages": tool_messages}
```

**关键点**：ToolMessage 会拼接到 AgentState.messages 后面。下次 LLM 调用时，它会看到"我调用了 calculator，结果是 12.0"，从而决定下一步行动。

---

## 五、内置工具详解

### 5.1 CalculatorTool — 安全数学计算

```python
class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate a mathematical expression."
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Math expression, e.g. '2 + 3 * 4' or 'sqrt(144)'"
            }
        },
        "required": ["expression"]
    }
    
    _SAFE_NAMES = {               # 白名单：只允许这些函数
        "abs": abs, "sqrt": math.sqrt, "sin": math.sin,
        "cos": math.cos, "log": math.log, "pi": math.pi, ...
    }
    
    async def execute(self, expression: str = "", **kwargs) -> ToolResult:
        try:
            result = eval(expression, {"__builtins__": {}}, self._SAFE_NAMES)
            return ToolResult(success=True, output=str(result))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
```

**安全设计**：`eval` 在白名单命名空间执行，`__builtins__` 设为空，杜绝 `__import__('os').system('rm -rf /')` 这类注入攻击。

### 5.2 HTTPRequestTool — 调用外部 API

```python
class HTTPRequestTool(BaseTool):
    name = "http_request"
    description = "Make an HTTP request to an external API."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to request"},
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]}
        },
        "required": ["url"]
    }
```

**安全设计**：只允许 http/https 协议，10 秒超时，结果截断到 2000 字符。

---

## 六、Function Calling 原理

### 6.1 LLM 是怎么知道调用哪个工具的？

```python
# Step 1: 注册所有工具的 schema
schemas = registry.get_openai_schemas()
# → [
#   {"type": "function", "function": {"name": "calculator", ...}},
#   {"type": "function", "function": {"name": "datetime", ...}},
# ]

# Step 2: 把 schema 绑定到 LLM
llm = ChatOpenAI(model="deepseek-chat")
llm_with_tools = llm.bind_tools(schemas)

# Step 3: 调用 LLM
response = await llm_with_tools.ainvoke([
    SystemMessage("You have access to tools."),
    HumanMessage("What is 2+2?")
])

# Step 4: LLM 返回 tool_call 而不是普通文本
# response.tool_calls = [{"name": "calculator", "args": {"expression": "2+2"}}]
```

### 6.2 LLM 内部如何决定？

LLM 训练时学习了 Function Calling 格式。当它看到：
1. `tools` 参数里有 `calculator` 的定义
2. 用户问了一个数学问题
3. 它知道 "数学问题 → 应该调用 calculator 工具"

这个过程不是规则匹配，而是 LLM 的推理能力——类似于它知道 "这个问题我算不出来，需要用计算器"。

---

## 七、生产级安全考虑

### 7.1 防止无限循环

```python
MAX_TOOL_ITERATIONS = 5  # 最多 5 次工具调用

# 如果 LLM 反复调同一个工具没结果 → 强制停止
tool_count = sum(1 for m in state["messages"] if isinstance(m, ToolMessage))
if tool_count >= MAX_TOOL_ITERATIONS:
    return "end"
```

### 7.2 防止注入攻击

```python
# Calculator: 白名单 eval
eval(expression, {"__builtins__": {}}, SAFE_NAMES)

# HTTP: 限制协议
if not url.startswith(("http://", "https://")):
    return ToolResult(False, "", "URL must be http/https")

# HTTP: 超时 + 截断
httpx.AsyncClient(timeout=10)
resp.text[:2000]
```

### 7.3 错误处理

```python
try:
    return await tool.execute(**kwargs)
except Exception as e:
    return ToolResult(success=False, output="", error=str(e))
    # LLM 看到 "Error: division by zero" 后会尝试其他方法或告知用户
```

---

## 八、面试题汇总

> 点击展开查看答案。

### Q1: Function Calling 是什么？Agent 是怎么知道自己该调用哪个工具的？

<details>
<summary>展开答案</summary>

Function Calling 是 LLM 的一项能力：**不直接回答，而是返回一个结构化的工具调用请求**。

原理：
1. 你把可用工具的定义（name, description, parameters JSON Schema）发给 LLM
2. LLM 根据用户问题推理：该不该用工具？用哪个？参数填什么？
3. LLM 返回 `tool_call` 对象（不是普通文本）
4. 你的代码执行这个 tool_call，把结果返回给 LLM
5. LLM 基于结果继续推理或给出最终答案

```python
# 对话示例
User:     "2 + 2 等于几？"
LLM:      tool_call: calculator("2+2")     ← 不直接回答，调用工具
System:   result: "4"                       ← 执行工具
LLM:      "2 + 2 等于 4"                   ← 基于结果回答
```

关键：**LLM 不是查询数据库选择工具，而是通过推理选择。** 这就像人看到数学题会去找计算器，看到"今天天气"会去查天气 App 一样。
</details>

---

### Q2: ToolRegistry 用了什么设计模式？为什么好？

<details>
<summary>展开答案</summary>

**Registry Pattern（注册表模式）**。

```python
# 新增工具只需一行，不改任何引擎代码
registry.register(MyNewTool())
```

好处：
- **开闭原则**：对扩展开放（加新工具），对修改关闭（不改 Agent 引擎）
- **解耦**：工具和 Agent 互不知道对方的实现
- **可插拔**：不同环境注册不同工具（开发用计算器，生产加 API 工具）
- **可发现**：LLM 通过 schema 自动发现所有可用工具

对比不用 Registry：
```python
# ❌ 硬编码 if-else
if tool_name == "calculator":
    result = calculate(args)
elif tool_name == "datetime":
    result = get_datetime(args)
elif tool_name == "weather":  # 每加一个工具都要改这里
    ...
```
</details>

---

### Q3: ReAct 模式是什么？和普通 LLM 调用有什么区别？

<details>
<summary>展开答案</summary>

**ReAct** = **Re**asoning + **Act**ing，Agent 在思考和行动之间循环。

对比：
```
普通 LLM:
  User → LLM → Answer（一步到位，但没有工具能力）

ReAct Agent:
  User → LLM(思考) → Tool(行动) → LLM(思考) → Tool(行动) → ... → Answer
```

LangGraph 实现 ReAct 的优势：
- **状态管理**：每次循环的结果自动保存在 Checkpointer 中
- **条件路由**：`_should_continue()` 根据最后一条消息决定是继续循环还是结束
- **迭代上限**：防止 LLM 反复调工具死循环
- **可中断**：结合 HITL 可以在工具执行前暂停等审批
</details>

---

### Q4: `bind_tools` 是什么？底层发生了什么？

<details>
<summary>展开答案</summary>

`bind_tools` 是 LangChain 提供的方法，把工具 Schema 注入到 LLM 的请求参数中。

```python
# 表面
llm_with_tools = llm.bind_tools(tool_schemas)

# 底层：实际发给 DeepSeek/OpenAI 的 HTTP 请求变成了
POST /v1/chat/completions
{
    "model": "deepseek-chat",
    "messages": [...],
    "tools": [                          ← bind_tools 加上去的
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "...",
                "parameters": {...}
            }
        }
    ]
}
```

OpenAI/DeepSeek 的 API 原生支持 `tools` 参数。`bind_tools` 只是一个便捷包装，把 Python dict 转成正确的 HTTP 请求格式。
</details>

---

### Q5: 如何保证 Calculator 的 eval 安全？

<details>
<summary>展开答案</summary>

Python 的 `eval()` 极其危险。默认情况下可以执行任意代码：

```python
eval("__import__('os').system('rm -rf /')")  # 💀 灾难
```

我们的三层防护：

```python
# 1. 清空 builtins — 不能 import, 不能 open 文件
eval(expr, {"__builtins__": {}}, SAFE_NAMES)

# 2. 白名单函数 — 只允许数学函数
SAFE_NAMES = {"abs": abs, "sqrt": math.sqrt, "sin": math.sin, ...}
# __import__, exec, open 等统统不在白名单里

# 3. try/except — 任何异常都捕获，不泄露到 LLM
try:
    result = eval(...)
except Exception as e:
    return ToolResult(success=False, error="Invalid expression")
```

更安全的替代方案（生产级）：
- 用 `numexpr` 库（纯数学表达式引擎，无代码执行能力）
- 用沙箱容器执行（Docker + nsjail）
- 用 WebAssembly 沙箱
</details>

---

### Q6: Tool Loop 和 Supervisor Multi-Agent 有什么区别？什么时候用哪个？

<details>
<summary>展开答案</summary>

| | Tool Loop | Supervisor |
|------|-----------|------------|
| 结构 | 单个 Agent + 多个工具 | 多个专业 Agent + 调度者 |
| LLM 调用 | 1 个 LLM 反复调工具 | 多个 LLM 各有分工 |
| 适用场景 | 计算、查时间、调 API | 研究+编码+审查 pipeline |
| 复杂度 | 低 | 高 |
| 示例 | "今天天气？" → 调天气 API | "写个排序算法并审查" → Coder + Reviewer |

选择标准：
- **只有一个任务类型** → Tool Loop
- **需要多个不同专业能力协作** → Supervisor

两者可以组合：Supervisor 的每个子 Agent 也可以有自己的 Tool Loop。
</details>

---

### Q7: 如何防止 Agent 无限循环调用工具？

<details>
<summary>展开答案</summary>

```python
# 方案 1: 硬限制（我们的实现）
MAX_TOOL_ITERATIONS = 5
tool_count = sum(1 for m in messages if isinstance(m, ToolMessage))
if tool_count >= MAX_TOOL_ITERATIONS:
    return "end"

# 方案 2: 重复检测
last_calls = []
if tool_call in last_calls[-3:]:
    return "end"  # 同样参数连调 3 次 → 停止

# 方案 3: Token 预算
total_tokens = sum(len(m.content) for m in messages)
if total_tokens > 10000:
    return "end"

# 方案 4: 时间限制
if time.time() - start_time > 30:
    return "end"
```

生产环境建议组合使用：硬限制 + 重复检测 + 时间限制。
</details>