# AgentFlow 实施路线图

> 📅 起始日期：2026-06-06  
> 📊 当前进度：Phase 1 主体完成 + Phase 2 Tool System 完成  
> ⏰ 实际投入：2 天（6/6 — 6/7），大幅超前于 12 周计划  
> 🎯 下一步：Multi-Agent Supervisor Pattern（2.2）

---

## Phase 1: MVP 核心引擎

> **目标**：能对话 + 能查文档 + 能部署  
> **状态**：✅ 主体完成，可演示

### Week 1 (6/6): 项目脚手架 + LLM 抽象层

| 模块 | 任务 | 状态 | PR |
|------|------|------|-----|
| 1.1.1 | 后端脚手架 (FastAPI + config + health) | ✅ | — |
| 1.1.1 | .env / .gitignore / README | ✅ | — |
| 1.1.2 | 前端脚手架 (Vite + React + Tailwind + Sidebar) | ✅ | — |
| 1.1.3 | 数据库模型 (Conversation/Message/KnowledgeBase ORM) | ✅ | — |
| 1.1.3 | Alembic + docker-compose.yml | ✅ | #6 |
| 1.2.1 | BaseLLMProvider (DeepSeek + Qwen + Mermaid 类图) | ✅ | — |
| 1.2.2 | LLMFactory + LLMRouter (Registry Pattern + 13 tests) | ✅ | — |
| extra | 多租户模型 (User/Workspace/WorkspaceMember + RBAC) | ✅ | #2 |
| extra | 全部注释英文化 (15 文件) | ✅ | #3 |

### Week 2 (6/6 — 6/7): 对话引擎

| 模块 | 任务 | 状态 | PR |
|------|------|------|-----|
| 1.3.1 | ChatGraphEngine (StateGraph + Reducer 机制) | ✅ | #1 |
| 1.3.2 | Checkpointer 集成 (MemorySaver + 继承链 Mermaid) | ✅ | #1 |
| 1.3.3 | Chat API (POST /chat + SSE /stream + /history) | ✅ | #1 |
| 1.3.4 | Chat 持久化到 PostgreSQL (ChatService) | ✅ | #5 |
| 1.3.5 | Chat API Key 修复 | ✅ | #4 |
| 1.3.6 | 对话列表 API + 新建对话 | ✅ | #8 |
| 1.3.7 | 对话单元测试 (13 tests) | ✅ | — |
| 1.3.8 | System Prompt Markdown 指令 | ✅ | #8 |

### Week 3 (6/7): RAG 管道

| 模块 | 任务 | 状态 | PR |
|------|------|------|-----|
| 1.4.1 | 文档上传 API (POST /knowledge/upload) | ✅ | #7 |
| 1.4.2 | URL 摄入 API (POST /knowledge/ingest-url) | ✅ | #7 |
| 1.4.3 | 10 Parser 策略模式 (Pdf/Docx/Csv/Excel/Pptx/Json/Epub/Html/Md/Txt) | ✅ | #7 |
| 1.4.4 | DocumentChunker (fixed-size + recursive + overlap) | ✅ | #7 |
| 1.4.5 | Embedder (纯 Python TF-IDF 384-dim) | ✅ | #7 |
| 1.4.6 | HybridRetriever (vector cosine + BM25 + RRF fusion) | ✅ | #7 |
| 1.4.7 | RAG Query API (POST /knowledge/query) | ✅ | #7 |
| 1.4.8 | KB CRUD (create/list/delete + documents) | ✅ | #7 |
| 1.4.9 | URL User-Agent 修复 | ✅ | #9 |
| 1.4.10 | created_at timestamp on document_chunks | ✅ | #9 |

### Week 4 (6/7): 前端 + 部署

| 模块 | 任务 | 状态 | PR |
|------|------|------|-----|
| 1.5.1 | ChatWindow (流式 + Markdown 渲染 + 打字效果) | ✅ | #8 |
| 1.5.2 | MessageBubble (复制/编辑 + hover 操作) | ✅ | #8 |
| 1.5.3 | 可折叠/拖拽 Sidebar | ✅ | #8 |
| 1.5.4 | 对话列表 (新建/切换/历史) | ✅ | #8 |
| 1.5.5 | KnowledgeBase 管理 (多 KB + 拖拽上传 + 中转站) | ✅ | #8, #9 |
| 1.5.6 | Dashboard (项目面板 + 统计) | ✅ | #8 |
| 1.6.1 | Dockerfile (API multi-stage + Frontend) | ✅ | #6 |
| 1.6.2 | docker-compose.yml (db + redis + api + frontend) | ✅ | #6 |
| 1.6.3 | Nginx 配置 | ⬜ | — |
| 1.6.4 | 阿里云 RDS + Redis 配置 | ⬜ | — |
| 1.6.5 | Phase 1 端到端验收测试 | ⬜ | — |

---

## Phase 2: Agent + Workflow 能力构建

> **目标**：工具调用、Supervisor 多 Agent、可视化编排、HITL  
> **状态**：🔜 2.2 Multi-Agent 下一步

### ✅ Phase 2.1: 工具系统（已完成）

| 模块 | 任务 | 状态 | PR |
|------|------|------|-----|
| 2.1.1 | BaseTool 抽象类 (Command Pattern + JSON Schema) | ✅ | #9 |
| 2.1.2 | ToolRegistry (Registry Pattern + OpenAI schema) | ✅ | #9 |
| 2.1.3 | CalculatorTool (safe math eval) | ✅ | #9 |
| 2.1.4 | DateTimeTool (now/today/timestamp) | ✅ | #9 |
| 2.1.5 | WebSearchTool (placeholder, API in Phase 3) | ✅ | #9 |
| 2.1.6 | HTTPRequestTool (GET/POST/PUT/DELETE) | ✅ | #9 |
| 2.1.7 | AgentGraphEngine (ReAct Tool Loop + Mermaid) | ✅ | #9 |
| 2.1.8 | Agent API (POST /agent + SSE /stream + GET /tools) | ✅ | #9 |
| 2.1.9 | Tool Loop 验证 (calculator: 2+2 → "4") | ✅ | #9 |

### ⬜ Phase 2.2: Supervisor 多 Agent（下一步）

| 模块 | 任务 | 状态 |
|------|------|------|
| 2.2.1 | SupervisorGraphEngine (LangGraph 状态路由) | ⬜ |
| 2.2.2 | Researcher Agent (web search + summarization) | ⬜ |
| 2.2.3 | Coder Agent (code generation + review) | ⬜ |
| 2.2.4 | Reviewer Agent (quality check + feedback loop) | ⬜ |
| 2.2.5 | Multi-Agent API + 流式 | ⬜ |
| 2.2.6 | Supervisor 时序图 (Mermaid) | ⬜ |

### ⬜ Phase 2.3: Workflow 可视化编排

| 模块 | 任务 | 状态 |
|------|------|------|
| 2.3.1 | Workflow DSL Schema (JSON 描述) | ⬜ |
| 2.3.2 | DSL → LangGraph 编译器 | ⬜ |
| 2.3.3 | ReactFlow 画布 (拖拽节点 + 连线) | ⬜ |
| 2.3.4 | 节点类型 (Chat/RAG/Tool/Condition/Loop/HITL) | ⬜ |
| 2.3.5 | 条件分支 + 循环节点 | ⬜ |
| 2.3.6 | 画布对接 API | ⬜ |

### ⬜ Phase 2.4: Workflow 运行时 (HITL)

| 模块 | 任务 | 状态 |
|------|------|------|
| 2.4.1 | HITL 审批节点 (interrupt_before) | ⬜ |
| 2.4.2 | 断点续传 (update_state + invoke(None)) | ⬜ |
| 2.4.3 | 暂停/恢复 Command | ⬜ |
| 2.4.4 | 流式执行 + WebSocket 推送 | ⬜ |
| 2.4.5 | Workflow 发布 API | ⬜ |

---

## Phase 3: 企业化 + 可观测

> **目标**：多用户、可观测、生产就绪  
> **状态**：⬜ 未开始

### 3.1 多租户 & 认证

| 模块 | 任务 | 状态 |
|------|------|------|
| 3.1.1 | User model + 注册/登录 API | ⬜ |
| 3.1.2 | JWT + Middleware | ⬜ |
| 3.1.3 | RBAC 角色 (Admin/Developer/Viewer) | ⬜ |
| 3.1.4 | 工作空间隔离 | ⬜ |
| 3.1.5 | API Key 管理 | ⬜ |
| 3.1.6 | Admin 后台 (用户管理 + 用量仪表盘) | ⬜ |

### 3.2 可观测

| 模块 | 任务 | 状态 |
|------|------|------|
| 3.2.1 | 对话日志 + Token 监控 | ⬜ |
| 3.2.2 | Prometheus Metrics | ⬜ |
| 3.2.3 | Grafana Dashboard | ⬜ |

### 3.3 部署上线

| 模块 | 任务 | 状态 |
|------|------|------|
| 3.3.1 | 阿里云 ACK 部署配置 | ⬜ |
| 3.3.2 | HTTPS + 域名 + SSL | ⬜ |
| 3.3.3 | 压力测试 + 性能优化 | ⬜ |
| 3.3.4 | 面试材料整理 (架构图 + 话术) | ⬜ |
| 3.3.5 | README + 快速开始指南 | ⬜ |

---

## 里程碑总览

```
✅ Week 1  ████ 项目跑起来 (后端 + 前端 + DB 连通)
✅ Week 2  ████ 能对话 (LangGraph + 流式 + Markdown)
✅ Week 3  ████ 能检索 (RAG 管道 + 17 格式 + 混合检索)
✅ Week 4  ████ 🎯 MVP 可演示 (Phase 1 完成)
✅ Week 5  ████ 能调工具 (Function Calling + ReAct + 4 tools)
⬜ Week 6  ████ Supervisor 多 Agent ← 下一步
⬜ Week 7  ████ 可视化画布 (ReactFlow + DSL 编译器)
⬜ Week 8  ████ HITL 人机协作
⬜ Week 9  ████ 🎯 Phase 2 完成
⬜ Week 10 ████ 多用户 (JWT + RBAC)
⬜ Week 11 ████ 可观测 (Prometheus + Grafana)
⬜ Week 12 ████ 🎯 阿里云 v1.0
```

## 已部署 API（20 个端点）

```
POST   /api/v1/chat                  ✅ 对话
POST   /api/v1/chat/stream           ✅ SSE 流式
GET    /api/v1/chat/conversations    ✅ 对话列表
GET    /api/v1/chat/history/{tid}    ✅ 历史消息
POST   /api/v1/knowledge/upload      ✅ 文档上传 (17 formats)
POST   /api/v1/knowledge/ingest-url  ✅ URL 摄入
POST   /api/v1/knowledge/query       ✅ 混合检索
GET    /api/v1/knowledge/bases       ✅ KB 列表
POST   /api/v1/knowledge/bases       ✅ 创建 KB
DELETE /api/v1/knowledge/bases/{id}  ✅ 删除 KB
GET    /api/v1/knowledge/bases/{id}/documents  ✅ 文档列表
DELETE /api/v1/knowledge/bases/{id}/documents/{did} ✅ 删除文档
POST   /api/v1/agent                 ✅ Agent 对话
POST   /api/v1/agent/stream          ✅ Agent SSE
GET    /api/v1/agent/tools           ✅ 工具列表
GET    /health                       ✅ 健康检查
```

## 面试时间线建议

| 阶段 | 建议 |
|------|------|
| **现在** | 已有 MVP + RAG + Agent Tools，可以开始投简历 |
| **Phase 2 完成后** | 核心竞争力具备 (Supervisor + Workflow + HITL) |
| **Phase 3 完成后** | 完整全栈作品集 (多租户 + 可观测 + 阿里云) |

---

> **状态说明**：⬜ 待做 / 🔄 进行中 / ✅ 完成
