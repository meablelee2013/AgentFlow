# MCP 接入指南

> 本文档说明在 AgentFlow 里 **如何安装/配置一个 MCP server、系统在启动和运行时如何感知它、Agent 如何调用它的 tools**。
>
> 适用代码版本:`feat/task-decomposition` 分支,涉及 `backend/app/core/mcp/`、`backend/app/main.py`、`backend/app/core/engine/chat_engine.py`、`backend/app/api/v1/chat.py`、项目根 `.mcp.json`。

---

## 0. 全景图

```
        ┌────────────────────────────┐
        │ 1) 你写 .mcp.json          │
        └──────────────┬─────────────┘
                       │  FastAPI lifespan 读
                       ▼
   ┌───────────────────────────────────────┐
   │ 2) startup: 连 MCP server (HTTP)      │
   │    - streamable_http_client(url)      │
   │    - ClientSession.initialize()       │
   │    - session.list_tools()  ← 协议发现 │
   │    缓存到 MCPClientManager._tools     │
   └──────────────┬────────────────────────┘
                  │
                  ▼
   ┌───────────────────────────────────────┐
   │ 3) 首个请求: 适配成 LangChain BaseTool │
   │    - 中文名 → ASCII (DeepSeek 要求)    │
   │    - JSON Schema → Pydantic args      │
   │    - 闭包包住 manager.call_tool        │
   └──────────────┬────────────────────────┘
                  │
                  ▼
   ┌───────────────────────────────────────┐
   │ 4) ChatGraphEngine(tools=...)         │
   │    LLM.bind_tools()  ← 模型这样感知   │
   │    StateGraph: chat ⇄ tools (ReAct)   │
   └───────────────────────────────────────┘
```

模型本身**不感知 MCP 协议**——它看到的只是 OpenAI Function Calling 协议里的一组 function。MCP → LangChain → OpenAI 的翻译全部发生在我们的适配层。

---

## 1. MCP 传输方式(stdio / SSE / Streamable HTTP)

MCP 协议本身定义的是 **JSON-RPC 消息格式**(`tools/list`、`tools/call`、`initialize` …),"消息怎么从客户端送到 server" 是另一层——**传输层 (transport)**。官方目前定义了 3 种,理解差异是选 `.mcp.json` 里 `type` 字段的前提。

| 传输方式 | 关键词 | 进程模型 | 网络 | 现状 |
|---|---|---|---|---|
| **stdio** | 子进程标准输入输出 | client 拉起 server 子进程 | 无 | 默认、最稳 |
| **SSE** (Server-Sent Events) | HTTP + 事件流 | 各自独立进程 | 跨网络 | **已废弃**(2024-11-05 后版本被 Streamable HTTP 取代) |
| **Streamable HTTP** | HTTP POST + 可选 SSE 流 | 各自独立进程 | 跨网络 | 当前 HTTP 类传输的官方推荐 |

### 1.1 stdio:本地子进程 + 管道通信

#### 工作方式

```
┌──────────────┐   spawn (fork+exec)   ┌─────────────────────┐
│  MCP Client  │ ────────────────────▶ │   MCP Server 进程   │
│ (我们的后端) │                       │ (npx/uvx/python ...) │
└──────┬───────┘                       └──────┬──────────────┘
       │         stdin  (JSON-RPC 请求)        │
       │  ───────────────────────────────────▶ │
       │         stdout (JSON-RPC 响应/通知)   │
       │  ◀─────────────────────────────────── │
       │         stderr (日志,不参与协议)     │
       │  ◀─────────────────────────────────── │
```

- Client **fork 出 server 子进程**,通过管道(`stdin/stdout`)读写换行分隔的 JSON-RPC 报文。
- `stderr` 留给 server 输出日志,不混进协议流。
- Server 进程的生命周期 = client 的生命周期,client 退出 → server 也死。

#### 在 `.mcp.json` 里长这样(标准 MCP 客户端 / Claude Code 通用格式)

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/me/docs"],
      "env": { "LOG_LEVEL": "info" }
    }
  }
}
```

#### 优点

- **零网络配置**——不要端口、不要 token、不要 TLS
- **天然隔离**——每个 client 一个 server 进程,没有多租户问题
- **延迟极低**——管道通信,微秒级
- **最简单的鉴权**——通过 `env` 传 API key,不会出现在网络层

#### 缺点

- 必须**本地可执行**(`npx`/`uvx`/`python` 都要在 PATH 里),云端部署难
- 一个 client 对应一个 server 实例,**没法共享**
- 远程访问做不到——比如手机/网页客户端连不上你本地的 stdio server
- 跨语言/跨容器调试麻烦(stderr 日志要单独捞)

#### 适用场景

本地工具(文件系统、Git、本地数据库)、个人开发环境、Claude Code 桌面端这种"客户端就在用户机器上"的场景。

> ⚠️ AgentFlow 目前**不支持 stdio**——`MCPConfig.from_project_root` 只解析 `type ∈ {"http", "streamableHttp"}`,其他类型会被日志 `mcp_skip_unsupported_transport` 跳过。要支持得在 `_startup_mcp` 里再走 `mcp.client.stdio.stdio_client` 这套 API,生命周期管理会更复杂(子进程清理、僵尸进程、stderr 转发)。

### 1.2 SSE:HTTP + 单向事件流(已废弃)

#### 工作方式

```
Client                           Server
  │                                │
  │  GET /sse  (Accept: text/event-stream)
  │ ──────────────────────────────▶│
  │                                │  保持连接,持续推 event
  │  ◀── event: message ───────────│  (server → client)
  │  ◀── event: message ───────────│
  │                                │
  │  POST /messages  (JSON-RPC)    │  (client → server,单独短连接)
  │ ──────────────────────────────▶│
  │  ◀── 200 OK ───────────────────│
```

关键特点:**双通道**——server → client 走长连 SSE 流,client → server 走独立的 HTTP POST。这种"两条腿走路"的设计是 SSE 最初被废弃的原因之一:对负载均衡器、防火墙、客户端实现都不友好(SSE 连接和 POST 端点的会话关联要靠 cookie 或 session id 自己拼)。

#### 现状

- MCP 规范 **2024-11-05 版** 引入 SSE
- MCP 规范 **2025-03-26 版** 起 SSE 被标记为 **deprecated**,推荐迁移到 Streamable HTTP
- 老的 server 实现仍能跑,但新写的不建议用

#### 为什么提它

历史上一段时间网上很多 MCP server 教程是 SSE 版的,你看到 `"type": "sse"` 的 `.mcp.json` 就知道这是老格式。**AgentFlow 也不支持 SSE**——同样会被跳过。

### 1.3 Streamable HTTP:当前 HTTP 类传输的推荐方案

这是 AgentFlow 目前唯一支持的远程传输方式(`type: "http"` 或 `"streamableHttp"`)。

#### 工作方式

```
Client                                  Server
  │                                       │
  │  POST /mcp  (JSON-RPC 请求)            │
  │  Accept: application/json,             │
  │          text/event-stream             │
  │ ─────────────────────────────────────▶ │
  │                                       │
  │  ◀── 响应 (两种之一):                  │
  │    (a) Content-Type: application/json  │  ← 单条结果,普通短连接
  │        { "jsonrpc":"2.0", ... }        │
  │                                       │
  │    或                                  │
  │    (b) Content-Type: text/event-stream │  ← 流式输出
  │        event: message                  │  (允许中途推 progress / chunk)
  │        data: { ... }                   │
  │        event: message                  │
  │        data: { ... }                   │
  │                                       │
  │  (可选) GET /mcp                        │  ← server 主动推消息时
  │        long-poll SSE 流                │  (反向通知,如 sampling 请求)
  │ ─────────────────────────────────────▶ │
  │  ◀── event: ... ───────────────────────│
```

#### 关键改进(相对 SSE)

1. **单端点 `/mcp`**——POST 发请求,server 自己决定回 `application/json` 还是 `text/event-stream`。负载均衡器看到的就是普通 HTTP POST,session 关联走标准 `Mcp-Session-Id` header。
2. **流是可选的**——不需要流的简单工具调用,直接走普通 POST/JSON,延迟和成本都更低;需要流(比如大模型 server 给的工具,要边算边返回)才升级到 SSE 流。
3. **可恢复(resumable)**——SSE 流断开后可以用 `Last-Event-ID` 续传,长任务更可靠。
4. **更容易部署**——无状态 server 可以横向扩展,session id 配合外部存储就能跨实例。

#### 在 `.mcp.json` 里长这样(AgentFlow 当前支持的格式)

```json
{
  "mcpServers": {
    "cmapi00074002": {
      "type": "http",
      "url": "http://mcpservergateway.market.alicloudapi.com/mcpnacos/.../<token>"
    }
  }
}
```

URL 里通常已经把鉴权 token 编码进路径或 query;高级用法可以加 `headers` 字段(本仓库当前 `config.py` 还没解析,只读 `url` 一个字段——要支持自定义 header 需要在 `MCPServerConfig` 里加)。

#### AgentFlow 里走 Streamable HTTP 的链路(回顾 §4)

```python
# main.py::_startup_mcp
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

transport_ctx = streamable_http_client(server.url, http_client=httpx_client, terminate_on_close=True)
read_stream, write_stream, _ = await transport_ctx.__aenter__()

session_ctx = ClientSession(read_stream, write_stream)
session = await session_ctx.__aenter__()
await session.initialize()              # ← MCP 握手
await manager.discover_tools()          # ← 调 session.list_tools()
```

`streamable_http_client` 内部就帮我们处理了:JSON / SSE 的 Content-Type 协商、`Mcp-Session-Id` header、长连接保活。我们只看到一对 `(read_stream, write_stream)`,跟 stdio 接口形式上对称。

### 1.4 三种方式怎么选?

| 你的情况 | 选 |
|---|---|
| 工具就在本机,只给本机的 client 用(Claude Code 桌面、本地脚本) | **stdio** |
| 工具部署在云端,要给多个客户端共享(我们的后端就是这种) | **Streamable HTTP** |
| 在网上看到老教程用 SSE | 知道是历史格式即可,**新项目别用** |
| 第三方只提供了 SSE 端点 | 联系对方升级到 Streamable HTTP,或自己写一层 SSE→HTTP 代理 |

> ⚠️ 在 AgentFlow 当前实现里,**只有 Streamable HTTP 可用**。要加 stdio 支持,需要:
> 1. `config.py` 解析 `type: "stdio"`、`command`、`args`、`env`
> 2. `_startup_mcp` 增加分支调用 `mcp.client.stdio.stdio_client`,管理子进程生命周期
> 3. `_shutdown_mcp` 增加子进程清理逻辑(SIGTERM + 超时后 SIGKILL)

---

## 2. 安装与配置一个 MCP server

### 2.1 安装依赖(已经做过的可跳过)

`backend/pyproject.toml` 已经声明:

```toml
"mcp>=1.27.2",
```

如果是新环境:

```bash
cd backend
uv sync
```

### 2.2 在项目根写 `.mcp.json`

文件路径:**项目根目录**(和 `backend/`、`frontend/` 平级),不是 backend 子目录。

```json
{
  "mcpServers": {
    "cmapi00074002": {
      "type": "http",
      "url": "http://mcpservergateway.market.alicloudapi.com/mcpnacos/cmapi00074002/<token>"
    }
  }
}
```

字段说明:

| key | 必填 | 说明 |
|---|---|---|
| `mcpServers.<name>` | ✅ | 唯一服务名,会出现在 startup 日志 `mcp_connecting` 里 |
| `type` | ✅ | 当前只支持 `"http"` 或 `"streamableHttp"`,其它(stdio / sse)会在 `MCPConfig` 解析阶段被跳过,日志输出 `mcp_skip_unsupported_transport` |
| `url` | ✅ | MCP server 的 streamable HTTP 端点 |

> 解析逻辑见 `backend/app/core/mcp/config.py:MCPConfig.from_project_root` —— 它从 `app/core/mcp/config.py` 向上数 4 级定位项目根。

### 2.3 多 server 限制

目前 `main.py::_startup_mcp()` 在循环里有显式的 `break`,**只会连接 .mcp.json 里的第一个 server**:

```python
# Only connect to the first server for now
break
```

需要多 server 时,移除该 `break` 并扩展 `MCPClientManager` 支持多 session(当前是单例单 session)。

### 2.4 启动后端验证

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

启动日志里应看到:

```
mcp_connecting       server=cmapi00074002 url=http://...
mcp_tools_discovered count=37 tools=[...]
mcp_connected        server=cmapi00074002 tool_count=37
```

如果 server 连不上,看到的是 `mcp_connection_failed`(带堆栈),**应用仍会正常启动,只是没有 MCP 工具可用**——这是有意的优雅降级。

---

## 3. 系统在生命周期中如何感知 MCP

### 3.1 启动:`lifespan` 三步走

`backend/app/main.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    CheckpointerManager.init_postgres()
    await _startup_mcp()       # ← 这里
    yield
    await _shutdown_mcp()
    CheckpointerManager.shutdown()
```

`_startup_mcp()` 的关键动作:

1. `MCPConfig.from_project_root()` 读 `.mcp.json`
2. 对每个 server:
   - 用 `httpx.AsyncClient`(connect/read/write/pool 都 15–30s 超时)做底层 HTTP
   - 进入 `streamable_http_client(url, http_client, terminate_on_close=True)` 这个 async context,拿到 `(read_stream, write_stream, _)`
   - 进入 `ClientSession(read, write)`,调 `await session.initialize()`(MCP 握手)
   - `manager._set_session(session)`,把 transport_ctx / session_ctx / http_client 都挂到 manager 上(为了 shutdown 时能反向 `__aexit__`)
   - `await manager.discover_tools()` ← **协议层发现**,调 `session.list_tools()`,把结果缓存成 `{name: mcp.types.Tool}`

### 3.2 工具发现:MCP 协议 `tools/list`

`backend/app/core/mcp/client.py:MCPClientManager.discover_tools`

```python
result = await self._session.list_tools()
self._tools = {t.name: t for t in result.tools}
```

每个 `mcp.types.Tool` 自带:
- `name`(原始名,可能是中文)
- `description`(自然语言)
- `inputSchema`(JSON Schema dict)

**这一刻"系统"已经知道有哪些工具了**,但模型还不知道——还差适配和 bind。

### 3.3 关闭:反向退出 context

`_shutdown_mcp()` 按 `session_ctx → transport_ctx → http_client` 顺序退出,保证 streamable HTTP 长连接正确关闭,日志 `mcp_shutdown_complete`。

---

## 4. Agent 如何感知 tools(MCP → LangChain → OpenAI 三层翻译)

### 4.1 首次请求时:懒构建 LangChain tools

`backend/app/api/v1/chat.py`

```python
async def _get_mcp_langchain_tools() -> list:
    if _mcp_langchain_tools is not None:
        return _mcp_langchain_tools          # 进程内缓存
    manager = get_mcp_client()
    if not manager.is_initialized:
        _mcp_langchain_tools = []            # MCP 没起来 → 空 list
        return _mcp_langchain_tools
    _mcp_langchain_tools = await build_mcp_langchain_tools(manager)
    return _mcp_langchain_tools
```

随后 `_get_chat_engine()` 一次性把 tools 注入到 engine:

```python
mcp_tools = await _get_mcp_langchain_tools()
_chat_engine = ChatGraphEngine(tools=mcp_tools)
```

> ⚠️ Engine 也是 **进程内单例**——一旦创建就不会重建。如果运行时 MCP 才连上,需要重置 `_chat_engine = None` 才能让新 tools 生效。

### 4.2 适配核心:`build_mcp_langchain_tools` 做了什么

`backend/app/core/mcp/langchain_adapter.py`,每个 MCP tool 经过三步转换:

#### (a) 工具名 ASCII 化 —— `_sanitize_tool_name`

DeepSeek API 要求工具名匹配 `^[a-zA-Z0-9_-]+$`,而很多 MCP 工具名是中文(如 `城市天气15日预报`)。函数按 **关键词 + 入参** 映射:

| 中文名片段 | + 入参 | → ASCII 名 |
|---|---|---|
| `15日` | `cityname` | `weather_15d_by_city` |
| `24小时` `空气` | `lat`+`lon` | `air_quality_24h_by_latlon` |
| `天气实况` | `cityId` | `weather_current_by_cityid` |
| `临近降水` | `poi` | `precipitation_by_poi` |

调用时仍用 **原始中文名** 走 MCP——这通过 `wrapper._tool_name = mcp_name` 保留。

#### (b) inputSchema → Pydantic —— `_json_schema_to_pydantic_model`

MCP 的 `inputSchema` 是一个 JSON Schema:

```json
{ "type":"object",
  "properties": {"cityname": {"type":"string","description":"城市名称"}},
  "required": ["cityname"] }
```

被 `pydantic.create_model` 动态拼成一个 BaseModel 类作为 LangChain `args_schema`。`required` 里的字段是必填,其余字段类型变成 `T | None` 默认 `None`。空 properties 时塞一个 `_placeholder` 字段避免空模型。

#### (c) 包成 BaseTool —— `_MCPToolWrapper`

继承 `langchain_core.tools.BaseTool`,关键的 `_arun` 闭包回到 MCP:

```python
async def _arun(self, **kwargs):
    return await self._call_fn(self._tool_name, **kwargs)
```

其中 `_call_fn` 在 `build_mcp_langchain_tools` 里通过闭包绑定:

```python
async def _call_mcp_tool(tool_name=name, **kwargs):
    return await manager.call_tool(tool_name, kwargs)
```

这一步保证 LangChain 调用 → 走 `MCPClientManager.call_tool` → `session.call_tool(原始中文名, args)` → 拿到 `CallToolResult` → `_extract_text` 抽出文本返回。

### 4.3 模型怎么"看到"工具:`bind_tools`

`backend/app/core/engine/chat_engine.py`

```python
def _get_llm(self):
    if self.tools:
        return self._llm.bind_tools(self.tools)
    return self._llm
```

`ChatOpenAI.bind_tools` 会把每个 BaseTool 的 `name / description / args_schema` 序列化成 **OpenAI Function Calling 协议**,夹在每次 chat completion 请求里:

```json
"tools": [
  { "type":"function",
    "function": {
      "name":"weather_15d_by_city",
      "description":"[城市天气15日预报] ...",
      "parameters": { /* 从 Pydantic 生成的 JSON Schema */ }
    }
  }, ...
]
```

模型看到这个就会按需返回 `tool_calls`——它根本不需要知道 MCP 是什么。

### 4.4 软提示通道(双保险)

`chat.py::_build_tools_description()` 还会调 `manager.build_tools_description()` 生成一段 Markdown 工具清单,注入 layered prompt 的 `tools_description` 字段。等于在 system prompt 里再写一遍"你有这些工具",显著提升触发率,尤其对天气这种领域强提示场景。

---

## 5. 运行时:ReAct 调用循环

`ChatGraphEngine` 在 `tools` 非空时,图结构变成:

```
START → chat ──[has tool_calls?]──→ tools ──→ chat ──→ ...
                       │                                  │
                       └────[no tool_calls]───────────────┴→ END
```

详细步骤(以"北京未来3天天气?"为例):

1. `chat_node` 调 `llm.ainvoke(messages)`,模型返回 `AIMessage(tool_calls=[{name:"weather_15d_by_city", args:{"cityname":"北京"}, id:"..."}])`
2. `_should_continue` 检查最后一条消息有 `tool_calls` → 路由到 `tools`
   - 同时统计已有 `ToolMessage` 数量,**≥ `MAX_TOOL_ITERATIONS=5` 直接收尾**,防止死循环
3. `_tools_node`:
   - 从 `self._tool_map` 按 name 找 wrapper
   - `await tool.ainvoke(args)` → 走 3.2(c) 链路 → MCP server 返回 JSON 文本
   - 包成 `ToolMessage(content, tool_call_id, name)` 追加到 messages
4. 回到 `chat_node`,模型基于工具结果生成最终自然语言回答 → `_should_continue` 看到没有新的 tool_calls → END

`_serialize_messages` 在导出对话历史时会把 `tool_calls` 和 `ToolMessage` 一并序列化(`role: "tool"`),前端可据此渲染工具调用过程。

---

## 6. 关键代码地图

| 关注点 | 文件 | 入口符号 |
|---|---|---|
| MCP server 声明 | `.mcp.json` | — |
| 配置解析 | `backend/app/core/mcp/config.py` | `MCPConfig.from_project_root` |
| 启动连接 | `backend/app/main.py` | `_startup_mcp` / `_shutdown_mcp` |
| 连接 + 工具发现 | `backend/app/core/mcp/client.py` | `MCPClientManager` |
| MCP → LangChain | `backend/app/core/mcp/langchain_adapter.py` | `build_mcp_langchain_tools` |
| 名字 ASCII 化 | 同上 | `_sanitize_tool_name` |
| Schema 转 Pydantic | 同上 | `_json_schema_to_pydantic_model` |
| 注入 engine | `backend/app/api/v1/chat.py` | `_get_mcp_langchain_tools` / `_get_chat_engine` |
| ReAct 循环 | `backend/app/core/engine/chat_engine.py` | `ChatGraphEngine._build_graph` |
| 防死循环上限 | 同上 | `MAX_TOOL_ITERATIONS = 5` |

---

## 7. 排错速查

| 现象 | 检查 |
|---|---|
| 启动看不到 `mcp_connecting` | `.mcp.json` 不在项目根,或 server `type` 不是 `http`/`streamableHttp` |
| `mcp_connection_failed` | URL 不可达 / 网络拒绝 / 鉴权 token 失效;检查 `httpx` 超时与代理 |
| `mcp_tools_discovered count=0` | server 上未注册工具,联系 MCP 服务方 |
| 模型不调工具 | 看请求里是否带 `tools=...`(在 engine 单例创建之后才会注入);确认 `_chat_engine.tools` 非空;必要时增强 `build_tools_description` 的提示 |
| `Tool 'xxx' not found` | LLM 返回的名字和 `_tool_map` 不匹配——大概率被 sanitize 改过,翻 `_sanitize_tool_name` 看路由分支 |
| 中文工具名报 400 invalid name | 漏走 sanitize,直接把 MCP 原名 bind 给了 LLM——确认走的是 `_MCPToolWrapper`,`name` 字段是 ASCII |
| 调用一直循环不止 | `MAX_TOOL_ITERATIONS` 兜底,但应排查模型为何反复调同一个工具(描述歧义?args_schema 不准?) |

---

## 8. 新增一个 MCP server 的清单(TL;DR)

1. 在 `.mcp.json` 的 `mcpServers` 里加一项(`type: "http"` + `url`)
2. 如果要同时连多个,移除 `main.py::_startup_mcp` 里的 `break`,并把 `MCPClientManager` 改造成支持多 session(当前是单例)
3. 重启后端,看日志 `mcp_tools_discovered`
4. 触发一次 chat,看日志 `mcp_langchain_tools_built` 和 `chat_engine_created tool_count=N`
5. 在前端发个问题验证 ReAct 循环
