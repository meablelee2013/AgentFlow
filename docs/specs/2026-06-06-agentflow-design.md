# AgentFlow — 类 Dify 的 AI Agent 平台设计文档

> 📅 创建时间：2026-06-06  
> 🎯 目标：构建一个生产可用的 AI Agent 开发平台，用于面试展示和阿里云部署  
> 📐 模式：混合模式 — 代码按生产规范，结构按学习实战路径  

---

## 一、项目定位与面试叙事

### 一句话定位

**AgentFlow** 是一个开源的 AI Agent 开发平台，让开发者通过可视化画布编排 Agent 工作流，集成 RAG 知识库和工具调用，一键部署到阿里云。

### 面试叙事逻辑（1 分钟电梯演讲）

> "我做了一个类 Dify 的 AI Agent 平台，叫 AgentFlow。整个项目分三个阶段迭代：  
> **Phase 1** 证明我能把 LLM + RAG 工程化落地，支持文档问答和对话管理；  
> **Phase 2** 证明我理解 Agent 架构和 Workflow 编排引擎，实现可视化画布和工具调用；  
> **Phase 3** 证明我有生产级系统思维，包括多租户、可观测性和阿里云部署。  
> 全程基于 LangGraph，深度使用了 StateGraph、Checkpointer、interrupt、Conditional Edges 等核心机制。"

### 面试官视角的加分点

| 维度 | 具体体现 |
|------|---------|
| **技术深度** | LangGraph 内核机制（Checkpointer 继承链、Reducer 原理、interrupt 生命周期） |
| **工程能力** | Monorepo 结构、API 设计、Docker Compose + 阿里云部署 |
| **产品思维** | 三阶段迭代、用户故事、架构决策记录 |
| **前沿意识** | MCP 协议支持、多模态 RAG、流式响应 |
| **代码质量** | 类型注解、测试覆盖、关键方法注释 + 时序图/流程图 |

---

## 二、技术栈总览

| 层级 | 技术 | 说明 |
|------|------|------|
| **LLM 框架** | LangGraph + LangChain | Agent 编排 + RAG 管道 |
| **LLM Provider** | DeepSeek（主力）/ 通义千问 / OpenAI 兼容 | 多 LLM 热切换 |
| **后端框架** | FastAPI (Python 3.12+) | REST + WebSocket |
| **后端依赖管理** | **uv** | 10-100x 速度提升，pyproject.toml 原生，可管理 Python 版本 |
| **数据库** | PostgreSQL 15 + pgvector | 业务数据 + 向量存储 |
| **向量数据库** | pgvector（Phase 1）/ Milvus（Phase 3 可选） | RAG 检索 |
| **缓存** | Redis | Session + 热点缓存 |
| **异步任务** | Celery + Redis Broker | 文档处理、Embedding |
| **前端** | Vite + React 18 + TypeScript | SPA |
| **前端依赖管理** | **pnpm** | 严格依赖隔离，无幽灵依赖，磁盘高效 |
| **可视化** | ReactFlow (xyflow) | 工作流画布拖拽 |
| **样式** | Tailwind CSS 4 | 原子化 CSS |
| **状态管理** | Zustand | 轻量前端状态 |
| **部署** | Docker Compose（本地）/ 阿里云 ACK（生产） |
| **可观测** | Prometheus + Grafana（Phase 3） | 监控告警 |

---

---

## 三、依赖管理工具与初始化

### Backend：uv

```bash
# 安装 uv（如果还没有）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 初始化项目
cd agent-platform
mkdir backend && cd backend
uv init --python 3.12

# 核心依赖
uv add fastapi[standard] uvicorn[standard] langgraph langchain-openai \
       sqlalchemy[asyncio] asyncpg alembic pgvector \
       redis[hiredis] celery structlog pydantic-settings \
       python-multipart python-jose[cryptography] bcrypt \
       pypdf2 python-docx markdown unstructured

# 开发依赖
uv add --dev pytest pytest-asyncio httpx ruff mypy pre-commit

# 日常命令
uv run uvicorn app.main:app --reload    # 启动开发服务器
uv run pytest                           # 运行测试
uv run ruff check .                     # 代码规范检查
```

### Frontend：pnpm

```bash
# 安装 pnpm（如果没有）
npm install -g pnpm

# 初始化项目
cd agent-platform
pnpm create vite frontend --template react-ts
cd frontend

# 运行时依赖
pnpm add react-router-dom @xyflow/react zustand \
        react-markdown remark-gfm rehype-highlight \
        lucide-react clsx tailwind-merge

# 开发依赖
pnpm add -D tailwindcss @tailwindcss/vite typescript \
             @types/react @types/react-dom eslint prettier

# 日常命令
pnpm dev        # 启动开发服务器
pnpm build      # 生产构建
pnpm lint       # 代码检查
```

> `uv` 和 `pnpm` 都会在各自目录生成 lockfile（`uv.lock` / `pnpm-lock.yaml`），确保团队依赖版本一致。

---

## 三-附录：为什么选 Monorepo？（ADR-001）

### 什么是 Monorepo？

**Monorepo**（单一仓库）= 前端 + 后端 + 部署脚本 + 文档全部放在一个 Git 仓库里，而不是各自建独立仓库。

```
Monorepo（本项目）：                  Polyrepo（多仓库）：
agent-platform/                      ├── agent-platform-api/       ← 独立 Git 仓库
├── backend/                          ├── agent-platform-frontend/  ← 独立 Git 仓库
├── frontend/                         └── agent-platform-deploy/    ← 独立 Git 仓库
├── deploy/
└── docs/         ← 一个 Git 仓库
```

### 为什么选 Monorepo？

| 维度 | Monorepo ✅ | Polyrepo ❌（对本项目不适用） |
|------|------------|------------------------------|
| **原子提交** | 一个 PR 同时改 API + 前端 + 类型定义，关联性强 | 需跨 2-3 个仓库开 PR，容易漏、容易版本不对齐 |
| **共享类型** | `shared/types/` 一份，前后端共用 Pydantic/TS 类型 | 要么复制粘贴两份，要么发内部 npm/pypi 私有包（过度工程） |
| **重构成本** | 改一个 API → 前后端一起改一起测 | 先改后端发布 → 再改前端发布，中间需要版本协调 |
| **CI/CD** | 一条 pipeline，按 diff 构建受影响的部分 | 每个仓库各一套 CI，总配置量翻倍 |
| **新人上手** | 一个 `git clone` + `docker-compose up` 跑起来 | 要分别 clone 3 个仓库，各自配环境 |
| **本地调试** | 同目录开发，前后端断点无缝切换 | 两个 IDE 窗口，跨项目调试体验割裂 |
| **依赖管理** | `pnpm workspace` 统一 Node 版本，`uv` 统一 Python 版本 | 各自锁定，可能出现后端 Python 3.12、前端 Node 22 的版本漂移 |

### 决策原则

> **本项目前后端紧密耦合**（API 变更前端必同步），且**单人开发**。Monorepo 是这种场景的默认选择。

### 其他方案对比

| 方案 | 工具 | 适合场景 | 升级路径 |
|------|------|---------|---------|
| **简单 Monorepo（本项目选择）** | 目录约定 + `pnpm workspace` | 个人 / 小团队，前后端紧耦合 | ← 当前方案 |
| **构建型 Monorepo** | Turborepo / Nx / Bazel | 大团队，需要增量构建、缓存、并行任务 | 简单 Monorepo → 平滑引入 Turborepo |
| **Polyrepo** | 独立 Git 仓库 | 大团队，前后端由不同组独立维护，版本独立发布 | 不适合本项目 |

### 面试话术

> "为什么选 Monorepo？因为我们前后端类型共享、API 变更需要原子提交、一个 docker-compose 就能快速启动全栈，适合小团队快速迭代。如果团队扩大到多人维护不同模块，可以从简单 Monorepo 平滑升级到 Turborepo 做增量构建和缓存，不需要拆仓库。这个决策遵循了 YAGNI 原则——当前场景用最简单方案解决，但要确保升级路径存在。"

### 升级预案

将来如果需要从简单 Monorepo 升级到 Turborepo：

```
目录约定 Monorepo                    Turborepo Monorepo
agent-platform/                     agent-platform/
├── backend/                        ├── apps/
├── frontend/           →           │   ├── api/
└── deploy/                         │   └── web/
                                    ├── packages/
                                    │   └── shared-types/
                                    ├── turbo.json
                                    └── pnpm-workspace.yaml
```

迁移成本很低：只是重组目录 + 加 `turbo.json` 配置文件，前端代码和后端代码的逻辑零改动。

---

## 四、阿里云部署架构

```
                           ┌─────────────────┐
                           │   阿里云 SLB     │  ← 负载均衡 + HTTPS
                           └────────┬────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
           ┌───────────┐   ┌───────────┐   ┌───────────┐
           │  ECS /     │   │  ECS /     │   │  ECS /     │  ← 阿里云 ACK (K8s)
           │  Pod #1    │   │  Pod #2    │   │  Pod #3    │
           │  (API)     │   │  (Worker)  │   │  (Frontend)│
           └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
                 │               │               │
         ┌───────┼───────┬───────┘               │
         │       │       │                       │
         ▼       ▼       ▼                       ▼
   ┌─────────┐ ┌──────┐ ┌──────────┐   ┌──────────────┐
   │ 阿里云   │ │ 阿里云│ │ 阿里云    │   │ 阿里云 OSS    │
   │ RDS PG  │ │ Redis│ │ NAS (EFS)│   │ (文件/图片)   │
   │+pgvector│ │      │ │ 共享存储  │   │              │
   └─────────┘ └──────┘ └──────────┘   └──────────────┘
```

| 阿里云服务 | 用途 | 规格建议 |
|-----------|------|---------|
| **ACK (K8s)** | 容器编排，运行 API/Worker/Frontend | 3 节点，ecs.g7.xlarge |
| **RDS PostgreSQL** | 业务数据 + pgvector 向量 | 4C8G，SSD 100GB |
| **Redis** | Celery Broker + Session 缓存 | 2G 标准版 |
| **OSS** | 文档/图片存储 | 按量付费 |
| **NAS** | 容器间共享存储（上传文件） | 通用型 |
| **SLB** | 负载均衡 + HTTPS 终止 | 公网 CLB |
| **ACM** | SSL 证书管理 | 免费证书 |

---

## 五、项目目录结构

```
agent-platform/
├── README.md                   # 项目说明 + 快速开始
├── ARCHITECTURE.md             # 架构文档（含关键决策记录 ADR）
├── docker-compose.yml          # 本地一键启动
├── Makefile                    # 常用命令
├── .env.example
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic/                # 数据库迁移
│   ├── app/
│   │   ├── main.py             # FastAPI 入口
│   │   ├── config.py           # 配置管理（pydantic-settings）
│   │   ├── api/                # 路由层
│   │   │   ├── v1/
│   │   │   │   ├── chat.py           # 对话 API
│   │   │   │   ├── knowledge.py      # 知识库 API
│   │   │   │   ├── workflow.py       # Workflow API
│   │   │   │   ├── agent.py          # Agent API
│   │   │   │   ├── tool.py           # 工具 API
│   │   │   │   ├── admin.py          # 管理后台 API
│   │   │   │   └── auth.py           # 认证 API
│   │   │   └── deps.py         # 依赖注入
│   │   ├── core/               # 核心业务层
│   │   │   ├── engine/         # LangGraph 引擎
│   │   │   │   ├── base.py           # BaseGraphEngine（抽象类）
│   │   │   │   ├── chat_engine.py    # 对话引擎
│   │   │   │   ├── agent_engine.py   # Agent 引擎
│   │   │   │   ├── workflow_engine.py # Workflow 执行引擎
│   │   │   │   └── checkpoint.py     # Checkpointer 管理
│   │   │   ├── llm/            # LLM 抽象层
│   │   │   │   ├── factory.py        # LLM Factory（策略模式）
│   │   │   │   ├── providers/        # 各 Provider 实现
│   │   │   │   └── router.py         # 智能路由（成本/延迟）
│   │   │   ├── rag/            # RAG 管道
│   │   │   │   ├── pipeline.py       # RAG Pipeline（管道模式）
│   │   │   │   ├── chunker.py        # 文档分块策略
│   │   │   │   ├── embedder.py       # Embedding 管理
│   │   │   │   ├── retriever.py      # 混合检索
│   │   │   │   └── reranker.py       # 重排序
│   │   │   ├── tool/           # 工具系统
│   │   │   │   ├── registry.py       # Tool Registry
│   │   │   │   ├── base.py           # BaseTool（抽象类）
│   │   │   │   └── builtins/         # 内置工具
│   │   │   ├── workflow/       # Workflow 引擎（Phase 2）
│   │   │   │   ├── schema.py         # Workflow DSL 定义
│   │   │   │   ├── compiler.py       # DSL → LangGraph 编译
│   │   │   │   ├── executor.py       # 执行器（含中断/恢复）
│   │   │   │   └── node_types/       # 节点类型定义
│   │   │   └── auth/           # 认证授权
│   │   │       ├── jwt.py
│   │   │       └── rbac.py
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   ├── services/           # 业务逻辑层
│   │   └── tasks/              # Celery 异步任务
│   │       ├── document.py           # 文档处理任务
│   │       └── embedding.py          # Embedding 任务
│   └── tests/
│       ├── unit/
│       └── integration/
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx         # 仪表盘
│   │   │   ├── ChatApp.tsx           # 对话应用
│   │   │   ├── KnowledgeBase.tsx     # 知识库管理
│   │   │   ├── WorkflowEditor.tsx    # 工作流编辑器（Phase 2）
│   │   │   ├── AgentBuilder.tsx      # Agent 构建器（Phase 2）
│   │   │   └── Admin.tsx             # 管理后台（Phase 3）
│   │   ├── components/
│   │   │   ├── chat/                 # 对话组件
│   │   │   ├── workflow/             # ReactFlow 节点组件
│   │   │   ├── common/               # 通用 UI 组件
│   │   │   └── layout/               # 布局组件
│   │   ├── hooks/                    # 自定义 Hooks
│   │   ├── stores/                   # Zustand stores
│   │   ├── api/                      # API 调用层
│   │   └── types/                    # TypeScript 类型
│   └── public/
│
├── deploy/
│   ├── docker/
│   │   ├── Dockerfile.api
│   │   ├── Dockerfile.worker
│   │   └── Dockerfile.frontend
│   ├── k8s/                           # 阿里云 ACK 部署
│   │   ├── namespace.yaml
│   │   ├── api-deployment.yaml
│   │   ├── worker-deployment.yaml
│   │   ├── frontend-deployment.yaml
│   │   ├── ingress.yaml
│   │   └── configmap.yaml
│   ├── terraform/                     # IaC（可选）
│   └── nginx/
│       └── nginx.conf
│
├── docs/
│   ├── specs/                         # 设计文档
│   ├── adr/                           # 架构决策记录
│   ├── api/                           # API 文档
│   └── diagrams/                      # 架构图/时序图源文件
│
└── scripts/
    ├── setup.sh                       # 初始化脚本
    ├── migrate.sh                     # 数据库迁移
    └── seed.sh                        # 初始数据填充
```

---

## 六、Phase 1 — MVP 核心引擎 功能清单

> **目标**：能对话 + 能查文档 + 能部署  
> **周期**：3-4 周  
> **可演示**：上传 PDF → 问问题 → 带来源引用的回答

### 1.1 项目脚手架

| # | 任务 | 交付物 | 技术点 |
|---|------|--------|--------|
| 1 | Monorepo 初始化 | `agent-platform/` 目录结构 | 工程化规范 |
| 2 | FastAPI 项目初始化 | `backend/` + pyproject.toml（uv） | uv 依赖管理 |
| 3 | Vite + React 项目初始化 | `frontend/` + 基础路由（pnpm） | TypeScript 配置 |
| 4 | Docker Compose 本地环境 | `docker-compose.yml`（API + PG + Redis + Frontend） | 容器化 |
| 5 | 配置管理系统 | `backend/app/config.py`（pydantic-settings） | 12-Factor App |
| 6 | 日志系统 | 结构化日志（structlog） | 生产日志规范 |
| 7 | 健康检查 + 基础中间件 | `/health`、CORS、请求 ID | FastAPI Middleware |
| 8 | 统一错误处理 | 全局异常处理器 + 错误码体系 | REST API 最佳实践 |

### 1.2 LLM 抽象层 ⭐ 核心学习点

| # | 任务 | 交付物 | 面试可讲 |
|---|------|--------|---------|
| 1 | `BaseLLMProvider` 抽象类 | 统一接口：`invoke`, `stream`, `embeddings` | **策略模式** — 为什么不用 if-else |
| 2 | `DeepSeekProvider` 实现 | DeepSeek Chat API 适配 | OpenAI 兼容协议适配 |
| 3 | `QwenProvider` 实现 | 阿里云通义千问 API | 阿里云 SDK 集成 |
| 4 | `LLMFactory` | 工厂创建 Provider 实例 | **工厂模式** — 解耦创建逻辑 |
| 5 | `LLMRouter` | 按成本/延迟自动选择模型 | **责任链模式** — 面试高频考点 |
| 6 | `LLMSwitcher`（运行时热切换） | 不停机切换 LLM | **观察者模式** — 通知消费者切换 |
| 7 | 故障转移 | 主 LLM 失败 → 自动切换备用 | **熔断器模式** — 生产必备 |
| 8 | Provider 注册机制 | `@register_provider` 装饰器 | **注册表模式** — 插件化扩展 |

> 📐 **需注释/时序图**：LLMFactory → LLMRouter → Provider 的调用链时序图

### 1.3 对话引擎 ⭐ 核心学习点

| # | 任务 | 交付物 | 面试可讲 |
|---|------|--------|---------|
| 1 | `ChatState` 定义 | TypedDict + `Annotated[list, operator.add]` | **Reducer 机制** — 覆盖 vs 累加 |
| 2 | `ChatGraphEngine` | StateGraph 构建：`chat_node` → 条件路由 | **LangGraph 编译原理** |
| 3 | `BaseCheckpointSaver` 集成 | 支持 MemorySaver / SqliteSaver 切换 | **继承链**：BaseCheckpointSaver → InMemorySaver → SqliteSaver |
| 4 | 会话管理 | thread_id 生成、会话列表、会话删除 | **Checkpointer 存储结构** |
| 5 | 对话历史恢复 | 相同 thread_id → 从 SQLite/PG 恢复 | **断点续传原理** — 面试重点 |
| 6 | 多轮对话上下文 | 滑动窗口 + 摘要压缩 | **Token 管理策略** |
| 7 | 流式响应 (SSE) | `astream_events()` → FastAPI StreamingResponse | **LangGraph 流式机制** |
| 8 | System Prompt 模板 | Jinja2 模板 + 变量注入 | Prompt 工程化 |

> 📐 **需注释/时序图**：
> - ChatGraphEngine 从编译到执行的完整时序图（`compile()` → `invoke()` → `get_tuple()` → `put()` → `put_writes()`）
> - Checkpointer 的存储结构图（thread_id → checkpoint_id → channel_values 的三级映射）

### 1.4 RAG 管道 ⭐ 核心学习点

| # | 任务 | 交付物 | 面试可讲 |
|---|------|--------|---------|
| 1 | 文档上传与解析 | PDF/Word/Markdown/TXT → 纯文本 | PyPDF2, python-docx |
| 2 | 分块策略 | 固定大小 / 语义分块 / 递归分块 | **Chunking 策略对比** |
| 3 | Embedding 管理 | DeepSeek Embedding / Qwen Embedding | **Embedding 模型选择** |
| 4 | pgvector 集成 | PostgreSQL + pgvector 扩展 | **向量索引原理**（IVFFlat vs HNSW） |
| 5 | 混合检索 | 向量相似度 0.7 + BM25 关键词 0.3 加权 | **融合检索算法** — 面试高频 |
| 6 | Rerank | BGE Reranker / Cohere Rerank | **两阶段检索** — 召回+精排 |
| 7 | 引用溯源 | 返回 chunk 来源文档 + 页码 | **上下文窗口构建** |
| 8 | 知识库 CRUD API | 创建/删除/更新/列表 知识库 | REST 设计 |
| 9 | 文档列表与状态 | 上传中 → 分块中 → Embedding 中 → 就绪 | 异步任务状态机 |
| 10 | Celery 异步文档处理 | 上传 → Celery → 分块 → Embedding → 写入 pgvector | **任务队列架构** |

> 📐 **需注释/时序图**：
> - RAG Pipeline 完整时序图（上传 → Celery 分块 → Embedding → 写入 pgvector → 检索 → Rerank → 生成）
> - 混合检索流程图（向量检索 + BM25 → 融合 → Rerank → Top-K）

### 1.5 聊天 UI（前端）

| # | 任务 | 交付物 |
|---|------|--------|
| 1 | 基础布局 | 侧边栏 + 对话区 + 输入框 |
| 2 | 对话列表 | 会话历史、新建/切换/删除 |
| 3 | 消息渲染 | Markdown 渲染、代码高亮、流式打字效果 |
| 4 | 知识库选择器 | 选择关联的知识库 |
| 5 | 引用展示 | 回答下方展示引用来源卡片 |
| 6 | 知识库管理页 | 创建/上传/文档列表 |

### 1.6 部署

| # | 任务 | 交付物 |
|---|------|--------|
| 1 | docker-compose.yml | 本地一键启动（API + Worker + Frontend + PG + Redis） |
| 2 | Dockerfile | 多阶段构建（API / Worker / Frontend） |
| 3 | 阿里云 RDS 配置 | pgvector 扩展启用 + 连接安全组 |
| 4 | 阿里云 Redis 配置 | 连接配置 |
| 5 | Nginx 反向代理 | HTTPS + API 路由 + 前端静态文件 |
| 6 | 环境变量管理 | .env 模板 + 阿里云配置说明 |

---

## 七、Phase 2 — Agent + Workflow 功能清单

> **周期**：4-5 周  
> **可演示**：在画布上搭一个客服工作流，用户问→意图识别→查知识库/调工具→人工审批→回复

### 2.1 Function Calling 与工具系统 ⭐

| # | 任务 | 交付物 | 面试可讲 |
|---|------|--------|---------|
| 1 | `BaseTool` 抽象类 | name, description, parameters (JSON Schema), execute | **命令模式** |
| 2 | `ToolRegistry` | 注册/发现/调用工具 | **注册表模式** |
| 3 | Tool Loop 引擎 | LLM决定调用 → 执行工具 → 结果回传 → 判断继续/结束 | **ReAct 循环原理** |
| 4 | 内置工具集 | WebSearch, Calculator, HTTPRequest, DateTime | 正则安全校验 |
| 5 | 工具分类管理 | 搜索类/计算类/API类/自定义 | 产品设计 |
| 6 | 参数提取节点 | LLM 从 NL → 结构化参数 | Prompt 设计 |

> 📐 **需注释/时序图**：Tool Loop 时序图（LLM → tool_choice → execute → feedback → LLM → final_answer）

### 2.2 Workflow 可视化编排 ⭐

| # | 任务 | 交付物 | 面试可讲 |
|---|------|--------|---------|
| 1 | Workflow DSL 定义 | JSON/YAML Schema 描述工作流 | **DSL 设计** — 领域建模 |
| 2 | DSL → LangGraph 编译器 | 解析 DSL → 构建 StateGraph → 注入 Checkpointer | **编译器模式** |
| 3 | ReactFlow 画布 | 拖拽节点、连线、属性面板 | 前端架构 |
| 4 | 节点类型（8种） | Start, Chat, RAG, Tool, Condition, Loop, HITL, End | **节点抽象** |
| 5 | 条件分支节点 | if/else 路由 → Conditional Edges | LangGraph 条件路由 |
| 6 | 循环节点 | Iteration：对数组每项执行子图 | **子图编译** |
| 7 | HITL 审批节点 | `interrupt_before` + `update_state` | **中断机制原理** |
| 8 | Workflow 发布 | 发布 → 生成 API endpoint | API 生成 |

> 📐 **需注释/时序图**：DSL 编译流程图（DSL JSON → Parser → StateGraph Builder → compile() → 可执行的 app）

### 2.3 Workflow 运行时

| # | 任务 | 交付物 |
|---|------|--------|
| 1 | 断点续传 | 运行时失败 → `get_state()` → 修复 → `invoke(None)` |
| 2 | 暂停/恢复 | `interrupt` → 人工处理 → `Command(resume=...)` |
| 3 | 流式执行 | `astream_events()` → WebSocket 推送每步状态 |
| 4 | 执行历史 | `get_state_history()` 查看所有 checkpoint |

---

## 八、Phase 3 — 企业化 + 可观测 功能清单

> **周期**：3-4 周  
> **可演示**：多用户各自创建 App，管理员看用量，全链路可观测

### 3.1 多租户 & 认证

| # | 任务 | 交付物 |
|---|------|--------|
| 1 | 用户注册/登录 | JWT + bcrypt |
| 2 | RBAC 角色 | Admin / Developer / Viewer |
| 3 | 工作空间隔离 | 用户只能看自己的 App 和知识库 |
| 4 | API Key 管理 | 生成/撤销 API Key，用于外部调用 |

### 3.2 Admin 后台

| # | 任务 | 交付物 |
|---|------|--------|
| 1 | 用户管理 | 用户列表、禁用/启用 |
| 2 | 用量统计 | 每个 App 的调用次数、Token 消耗 |
| 3 | 仪表盘 | 日活、总调用、热门知识库 |

### 3.3 LLMOps & 可观测

| # | 任务 | 交付物 |
|---|------|--------|
| 1 | 对话日志 | 完整记录每轮对话（用户输入 + LLM 输出 + 工具调用） |
| 2 | Token 监控 | 按模型/按 App/按用户统计 Token 用量 |
| 3 | 延迟监控 | API P50/P95/P99 延迟 |
| 4 | 标注系统 | 对回答点赞/踩、人工修正 |
| 5 | Prometheus Metrics | `/metrics` endpoint + Grafana Dashboard |
| 6 | 告警规则 | 错误率 > 5%、P95 > 5s → 告警 |

### 3.4 发布管理

| # | 任务 | 交付物 |
|---|------|--------|
| 1 | App 版本管理 | 保存/回滚历史版本 |
| 2 | 发布/下线 | 切换 App 状态（draft/published/archived） |
| 3 | API 文档生成 | 每个 App 自动生成 OpenAPI 文档 |

### 3.5 多模态（可选）

| # | 任务 | 交付物 |
|---|------|--------|
| 1 | 图片理解 | 支持上传图片 + 视觉模型（Qwen-VL） |
| 2 | 图片 Embedding | 多模态向量检索 |
| 3 | OCR | 图片文字提取 → 入知识库 |

---

## 九、实施顺序（推荐）

```
Week 1-2:  1.1 项目脚手架 → 1.2 LLM 抽象层
Week 2-3:  1.3 对话引擎
Week 3-4:  1.4 RAG 管道 → 1.5 聊天 UI
Week 4:     1.6 部署（Docker + 阿里云 RDS）
━━━━━━━━━━━━━━━━━━━━ ✨ Phase 1 完成，可演示
Week 5-6:  2.1 Function Calling 与工具系统
Week 7-8:  2.2 Workflow 可视化编排（ReactFlow 前端 + DSL 编译器）
Week 8-9:  2.3 Workflow 运行时（断点续传/HITL/流式）
━━━━━━━━━━━━━━━━━━━━ ✨ Phase 2 完成，核心差异化能力
Week 10-11: 3.1 多租户 & 认证 → 3.2 Admin 后台
Week 11-12: 3.3 LLMOps & 可观测
Week 12:    3.4 发布管理 → 阿里云 ACK 生产部署
━━━━━━━━━━━━━━━━━━━━ ✨ Phase 3 完成，生产可用
```

---

## 十、关键注释与图要求

在实现过程中，以下位置需要添加**详细的注释 + 时序图/流程图**（用 Mermaid 语法写在代码注释中或单独的 diagrams/ 目录）：

| 序号 | 位置 | 内容 | 格式 |
|------|------|------|------|
| 1 | `core/engine/base.py` — `BaseGraphEngine` 类 | Graph 从编译到执行的完整时序图 | Mermaid sequenceDiagram |
| 2 | `core/engine/checkpoint.py` — Checkpointer 初始化 | BaseCheckpointSaver 继承链 + 存储结构图 | Mermaid classDiagram |
| 3 | `core/llm/factory.py` — `LLMFactory` + `LLMRouter` | 策略模式类图 + Provider 调用时序图 | Mermaid |
| 4 | `core/rag/pipeline.py` — `RAGPipeline` 类 | 完整 RAG 管道流程图 | Mermaid flowchart |
| 5 | `core/rag/retriever.py` — `HybridRetriever` | 混合检索 + Rerank 流程图 | Mermaid |
| 6 | `core/tool/registry.py` — `ToolRegistry` | Tool Loop 时序图 | Mermaid sequenceDiagram |
| 7 | `core/workflow/compiler.py` — `WorkflowCompiler` | DSL 编译为 LangGraph 的流程图 | Mermaid |
| 8 | `core/workflow/executor.py` — HITL 相关 | interrupt → update_state → resume 时序图 | Mermaid |
| 9 | `core/engine/chat_engine.py` — `ChatGraphEngine` | Checkpoint 读写时机 + thread_id 隔离 | Mermaid sequenceDiagram |
| 10 | `backend/app/main.py` — 启动入口 | 中间件栈 + 请求生命周期 | Mermaid flowchart |
