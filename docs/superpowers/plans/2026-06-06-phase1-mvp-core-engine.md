# Phase 1 — MVP 核心引擎 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个可对话 + 可文档问答 + 可部署的 AI Agent 平台 MVP

**Architecture:** FastAPI 后端 + LangGraph 对话/RAG 引擎 + PostgreSQL/pgvector 存储 + React/Vite 前端，Monorepo 管理，Docker Compose 部署

**Tech Stack:** Python 3.12+ / FastAPI / LangGraph / LangChain / PostgreSQL+pgvector / Redis / Celery / React 18 + TypeScript + Tailwind CSS / Docker

**Spec reference:** `docs/specs/2026-06-06-agentflow-design.md`

---

## File Map (Phase 1 deliverables)

```
agentflow/
├── backend/
│   ├── pyproject.toml                    ← uv project
│   ├── alembic.ini                       ← DB migrations config
│   ├── alembic/                          ← Migration files
│   ├── app/
│   │   ├── main.py                       ← FastAPI entry (NEW)
│   │   ├── config.py                     ← pydantic-settings (NEW)
│   │   ├── api/v1/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py                   ← Chat API (NEW)
│   │   │   ├── knowledge.py              ← Knowledge base API (NEW)
│   │   │   └── deps.py                   ← Dependency injection (NEW)
│   │   ├── core/
│   │   │   ├── engine/
│   │   │   │   ├── base.py               ← BaseGraphEngine (NEW)
│   │   │   │   ├── chat_engine.py        ← ChatGraphEngine (NEW)
│   │   │   │   └── checkpoint.py         ← Checkpointer manager (NEW)
│   │   │   ├── llm/
│   │   │   │   ├── factory.py            ← LLMFactory (NEW) ⭐
│   │   │   │   ├── router.py             ← LLMRouter (NEW) ⭐
│   │   │   │   └── providers/
│   │   │   │       ├── base.py           ← BaseLLMProvider (NEW) ⭐
│   │   │   │       ├── deepseek.py       ← DeepSeekProvider (NEW)
│   │   │   │       └── qwen.py           ← QwenProvider (NEW)
│   │   │   ├── rag/
│   │   │   │   ├── pipeline.py           ← RAGPipeline (NEW) ⭐
│   │   │   │   ├── chunker.py            ← Document chunking (NEW)
│   │   │   │   ├── embedder.py           ← Embedding manager (NEW)
│   │   │   │   ├── retriever.py          ← Hybrid retriever (NEW) ⭐
│   │   │   │   └── reranker.py           ← Reranker (NEW)
│   │   │   └── tool/
│   │   │       ├── registry.py           ← ToolRegistry (NEW)
│   │   │       └── base.py               ← BaseTool (NEW)
│   │   ├── models/
│   │   │   ├── base.py                   ← SQLAlchemy Base (NEW)
│   │   │   ├── user.py                   ← User model (NEW)
│   │   │   ├── knowledge.py              ← Knowledge/KB models (NEW)
│   │   │   └── conversation.py           ← Conversation models (NEW)
│   │   ├── schemas/
│   │   │   ├── chat.py                   ← Chat req/resp (NEW)
│   │   │   └── knowledge.py              ← KB schemas (NEW)
│   │   ├── services/
│   │   │   ├── chat_service.py           ← Chat service (NEW)
│   │   │   └── knowledge_service.py      ← KB service (NEW)
│   │   └── tasks/
│   │       ├── __init__.py               ← Celery app (NEW)
│   │       └── document.py               ← Document processing (NEW)
│   └── tests/
│       ├── conftest.py                   ← Test fixtures (NEW)
│       ├── unit/
│       └── integration/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx                       ← Root with router (NEW)
│   │   ├── main.tsx                      ← Entry (NEW)
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx             ← Home page (NEW)
│   │   │   ├── ChatApp.tsx               ← Chat page (NEW)
│   │   │   └── KnowledgeBase.tsx         ← KB management (NEW)
│   │   ├── components/chat/
│   │   │   ├── ChatWindow.tsx            ← Message list+input (NEW)
│   │   │   ├── MessageBubble.tsx         ← Single message (NEW)
│   │   │   └── CitationCard.tsx          ← Source citation (NEW)
│   │   ├── components/common/
│   │   │   ├── Sidebar.tsx               ← Navigation (NEW)
│   │   │   └── Loading.tsx               ← Spinner (NEW)
│   │   ├── api/
│   │   │   └── client.ts                 ← Axios wrapper (NEW)
│   │   ├── stores/
│   │   │   └── chat.ts                   ← Chat Zustand store (NEW)
│   │   └── types/
│   │       └── index.ts                  ← Shared TS types (NEW)
│   └── index.html
├── docker-compose.yml                    ← Local dev (NEW)
├── .env.example                          ← Env template (NEW)
├── .gitignore                            ← Git ignore (NEW)
└── README.md                             ← Project README (NEW)
```

⭐ = 面试关键类，需要详细注释 + Mermaid 时序图/流程图

---
```


## Module 1.1: 项目脚手架

### Task 1.1.1: 初始化 Backend (uv + FastAPI)

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`

- [ ] **Step 1: 用 uv 初始化 Python 项目**

```bash
cd /Users/keta/dataanalytics/agentflow/backend
uv init --python 3.12
uv add fastapi[standard] uvicorn[standard] pydantic-settings structlog
```

- [ ] **Step 2: 创建 config.py**

```python
# backend/app/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置 — 从 .env 和系统环境变量读取"""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 应用 ---
    APP_NAME: str = "AgentFlow"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # --- 数据库 ---
    DATABASE_URL: str = "postgresql+asyncpg://agentflow:agentflow@localhost:5432/agentflow"

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- LLM ---
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # --- Embedding ---
    EMBEDDING_MODEL: str = "deepseek-chat"  # or "text-embedding-v3"

    # --- 向量存储 ---
    VECTOR_DIMENSION: int = 1536


settings = Settings()
```

- [ ] **Step 3: 创建 main.py（FastAPI 入口）**

```python
# backend/app/main.py
"""
AgentFlow API — FastAPI Application Entry

请求生命周期:
    Request → CORS Middleware → Request ID → Logging → Router → Response
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的资源管理"""
    logger.info("AgentFlow starting", version=settings.APP_VERSION)
    # TODO: 初始化数据库连接池、Redis 连接
    yield
    logger.info("AgentFlow shutting down")
    # TODO: 关闭连接


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """健康检查端点 — 用于 K8s liveness probe"""
    return {"status": "ok", "version": settings.APP_VERSION}
```

- [ ] **Step 4: 启动验证**

```bash
cd /Users/keta/dataanalytics/agentflow/backend
uv run uvicorn app.main:app --reload --port 8000
# 访问 http://localhost:8000/health
# 预期: {"status":"ok","version":"0.1.0"}
```

- [ ] **Step 5: 创建 .gitignore**

```bash
cat > /Users/keta/dataanalytics/agentflow/.gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
.venv/
*.egg

# Environment
.env
.env.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Build
frontend/dist/
frontend/node_modules/

# Database
*.db
*.sqlite3

# Docker
docker-data/
EOF
```

- [ ] **Step 6: 创建 README.md**

```bash
cat > /Users/keta/dataanalytics/agentflow/README.md << 'EOF'
# AgentFlow — AI Agent 开发平台

开源的 AI Agent 开发平台，可视化编排 Agent 工作流，集成 RAG 知识库和工具调用。

## 快速开始

```bash
# 1. 克隆
git clone <repo-url> && cd agentflow

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY

# 3. 启动
docker-compose up -d

# 4. 访问
# Frontend: http://localhost:5173
# API Docs: http://localhost:8000/docs
```

## 技术栈

- **Backend**: Python 3.12+ / FastAPI / LangGraph / LangChain
- **Frontend**: React 18 + TypeScript + Tailwind CSS
- **Database**: PostgreSQL 15 + pgvector
- **Infra**: Docker Compose / 阿里云 ACK
EOF
```

- [ ] **Step 7: 创建 .env.example**

```bash
cat > /Users/keta/dataanalytics/agentflow/.env.example << 'EOF'
# AgentFlow 环境变量
# 复制为 .env 并填入实际值

# --- 应用 ---
SECRET_KEY=change-me-to-random-string
DEBUG=true

# --- 数据库 ---
DATABASE_URL=postgresql+asyncpg://agentflow:agentflow@localhost:5432/agentflow

# --- Redis ---
REDIS_URL=redis://localhost:6379/0

# --- LLM (至少配置一个) ---
DEEPSEEK_API_KEY=sk-your-deepseek-key
QWEN_API_KEY=sk-your-qwen-key
EOF
```

- [ ] **Step 8: Git 初始化 + 首次提交**

```bash
cd /Users/keta/dataanalytics/agentflow
git init
git add -A
git commit -m "feat: initialize AgentFlow project scaffold

- FastAPI backend with health check and config
- Project README and .gitignore
- Environment variable template

Ref: docs/specs/2026-06-06-agentflow-design.md"
```

---

### Task 1.1.2: 初始化 Frontend (Vite + React + TypeScript)

**Files:**
- Create: `frontend/package.json` (via pnpm create)
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: 用 pnpm create vite 初始化**

```bash
cd /Users/keta/dataanalytics/agentflow
pnpm create vite frontend --template react-ts
cd frontend
pnpm install
```

- [ ] **Step 2: 安装额外依赖**

```bash
cd /Users/keta/dataanalytics/agentflow/frontend
pnpm add react-router-dom zustand react-markdown remark-gfm rehype-highlight lucide-react clsx tailwind-merge axios
pnpm add -D tailwindcss @tailwindcss/vite @types/react @types/react-dom eslint prettier
```

- [ ] **Step 3: 配置 Tailwind**

```css
/* frontend/src/index.css — 替换默认内容 */
@import "tailwindcss";
```

```typescript
// frontend/vite.config.ts — 确保 tailwindcss plugin
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 4: 创建最小 App.tsx**

```tsx
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Sidebar } from './components/common/Sidebar'

function Dashboard() {
  return <div className="p-8"><h1 className="text-2xl font-bold">AgentFlow Dashboard</h1></div>
}

function ChatApp() {
  return <div className="p-8"><h1 className="text-2xl font-bold">Chat</h1></div>
}

function KnowledgeBase() {
  return <div className="p-8"><h1 className="text-2xl font-bold">Knowledge Base</h1></div>
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-50">
        <Sidebar />
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/chat" element={<ChatApp />} />
            <Route path="/knowledge" element={<KnowledgeBase />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
```

- [ ] **Step 5: 创建 Sidebar**

```tsx
// frontend/src/components/common/Sidebar.tsx
import { NavLink } from 'react-router-dom'
import { MessageSquare, Database, Home } from 'lucide-react'

const navItems = [
  { to: '/', icon: Home, label: 'Dashboard' },
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/knowledge', icon: Database, label: 'Knowledge Base' },
]

export function Sidebar() {
  return (
    <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
      <div className="p-6 font-bold text-lg text-blue-600">AgentFlow</div>
      <nav className="flex-1 px-3 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-700 font-medium'
                  : 'text-gray-600 hover:bg-gray-100'
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
```

- [ ] **Step 6: 启动前端验证**

```bash
cd /Users/keta/dataanalytics/agentflow/frontend
pnpm dev
# 访问 http://localhost:5173
# 预期: 侧边栏 + 三个页面路由可用
```

- [ ] **Step 7: Commit**

```bash
cd /Users/keta/dataanalytics/agentflow
git add frontend/ .gitignore
git commit -m "feat: initialize React + Vite + Tailwind frontend

- React 18 + TypeScript + Vite + Tailwind CSS 4
- React Router with 3 routes: Dashboard, Chat, Knowledge Base
- Sidebar navigation component
- Vite proxy to backend API"
```

---

### Task 1.1.3: 数据库初始化 (PostgreSQL + pgvector)

**Files:**
- Create: `backend/app/models/base.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/knowledge.py`
- Create: `backend/app/models/conversation.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `docker-compose.yml`

- [ ] **Step 1: 添加数据库依赖**

```bash
cd /Users/keta/dataanalytics/agentflow/backend
uv add sqlalchemy[asyncio] asyncpg alembic pgvector redis[hiredis] celery python-dotenv python-multipart
uv add --dev pytest pytest-asyncio httpx
```

- [ ] **Step 2: 创建 SQLAlchemy Base**

```python
# backend/app/models/base.py
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs


class Base(AsyncAttrs, DeclarativeBase):
    """SQLAlchemy 声明式基类 — 所有 ORM 模型继承此类"""
    pass
```

- [ ] **Step 3: 创建 Conversation model**

```python
# backend/app/models/conversation.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base


class Conversation(Base):
    """对话会话 — 一个 conversation = 一个 thread_id"""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), default="New Conversation")
    thread_id: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    """对话消息"""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
```

- [ ] **Step 4: 创建 Knowledge/KnowledgeBase model**

```python
# backend/app/models/knowledge.py
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, Integer, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
import enum

from app.models.base import Base


class KnowledgeBaseStatus(str, enum.Enum):
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class KnowledgeBase(Base):
    """知识库"""

    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[KnowledgeBaseStatus] = mapped_column(
        SAEnum(KnowledgeBaseStatus), default=KnowledgeBaseStatus.PROCESSING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Document(Base):
    """文档"""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentChunk(Base):
    """文档分块 — 存 pgvector embedding"""

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=True)
    metadata: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
```

> ⚠️ `from app.models.base import Base` 需要在 models `__init__` 层注册；稍后在 `backend/app/models/__init__.py` 中 import 所有 model

- [ ] **Step 5: 配置 Alembic**

```bash
cd /Users/keta/dataanalytics/agentflow/backend
uv run alembic init alembic
# 然后修改 alembic/env.py 指向 async engine
```

- [ ] **Step 6: 创建 docker-compose.yml**

```yaml
# docker-compose.yml
version: "3.9"

services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: agentflow
      POSTGRES_PASSWORD: agentflow
      POSTGRES_DB: agentflow
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build:
      context: ./backend
      dockerfile: ../deploy/docker/Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://agentflow:agentflow@db:5432/agentflow
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    volumes:
      - ./backend:/app

  worker:
    build:
      context: ./backend
      dockerfile: ../deploy/docker/Dockerfile.worker
    environment:
      - DATABASE_URL=postgresql+asyncpg://agentflow:agentflow@db:5432/agentflow
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis

  frontend:
    build:
      context: ./frontend
      dockerfile: ../deploy/docker/Dockerfile.frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules

volumes:
  pgdata:
```

- [ ] **Step 7: Commit**

```bash
cd /Users/keta/dataanalytics/agentflow
git add backend/app/models/ backend/alembic.ini docker-compose.yml
git commit -m "feat: add database models and docker-compose

- Conversation and Message models
- KnowledgeBase, Document, DocumentChunk models with pgvector
- Alembic migration setup
- Docker Compose with pgvector + Redis + API + Frontend"
```

---

## Module 1.2: LLM 抽象层 ⭐

> 面试关键模块 — 每个类都需要详细注释 + 类图

### Task 1.2.1: BaseLLMProvider 抽象类 + DeepSeek 实现

**Files:**
- Create: `backend/app/core/llm/providers/base.py`
- Create: `backend/app/core/llm/providers/deepseek.py`
- Create: `backend/app/core/llm/providers/__init__.py`
- Create: `backend/tests/unit/test_llm_provider.py`

- [ ] **Step 1: 创建 BaseLLMProvider 抽象类（含 Mermaid 注释）**

```python
# backend/app/core/llm/providers/base.py
"""
LLM Provider 抽象基类

类继承关系 (Mermaid):
```mermaid
classDiagram
    class BaseLLMProvider {
        <<abstract>>
        +invoke(messages) str
        +stream(messages) AsyncGenerator
        +embeddings(texts) list
        +model_name str
        +supports_tools bool
    }
    class DeepSeekProvider {
        +invoke(messages) str
        +stream(messages) AsyncGenerator
    }
    class QwenProvider {
        +invoke(messages) str
        +stream(messages) AsyncGenerator
    }
    BaseLLMProvider <|-- DeepSeekProvider
    BaseLLMProvider <|-- QwenProvider
```

设计模式: **策略模式 (Strategy Pattern)** — StateGraph 通过切换 Provider 实例
来改变 LLM 调用行为，无需修改上层代码。

```python
# 使用示例 — 只需换 provider 参数，其余代码不变
provider = DeepSeekProvider(api_key="...")
provider = QwenProvider(api_key="...")
```
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator


class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类

    定义所有 Provider 必须实现的接口。
    类似 Java 的 Interface，子类必须实现所有 @abstractmethod。
    """

    model_name: str = ""
    supports_tools: bool = False

    @abstractmethod
    async def invoke(self, messages: list[dict]) -> str:
        """同步调用 LLM，返回完整响应"""
        ...

    @abstractmethod
    async def stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """流式调用 LLM，逐 token 返回"""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化"""
        ...
```

- [ ] **Step 2: 创建 DeepSeekProvider**

```python
# backend/app/core/llm/providers/deepseek.py
"""
DeepSeek Provider — 适配 DeepSeek Chat API (OpenAI 兼容协议)

调用时序 (Mermaid):
```mermaid
sequenceDiagram
    participant Caller
    participant DeepSeekProvider
    participant OpenAI Client
    participant DeepSeek API

    Caller->>DeepSeekProvider: invoke(messages)
    DeepSeekProvider->>OpenAI Client: chat.completions.create()
    OpenAI Client->>DeepSeek API: POST /v1/chat/completions
    DeepSeek API-->>OpenAI Client: ChatCompletion
    OpenAI Client-->>DeepSeekProvider: response.choices[0].message
    DeepSeekProvider-->>Caller: content str
```
"""

import os
from typing import AsyncGenerator
from openai import AsyncOpenAI
from app.core.llm.providers.base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek Chat API Provider — 主力模型，高性价比"""

    model_name = "deepseek-chat"
    supports_tools = True

    def __init__(self, api_key: str | None = None):
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    async def invoke(self, messages: list[dict]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""

    async def stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        stream = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # DeepSeek 目前用 chat model 做 embedding（简化版）
        # 生产环境应使用专门的 embedding model
        embeddings = []
        for text in texts:
            response = await self.client.embeddings.create(
                model="deepseek-chat",
                input=text,
            )
            embeddings.append(response.data[0].embedding)
        return embeddings
```

- [ ] **Step 3: 创建 providers __init__.py**

```python
# backend/app/core/llm/providers/__init__.py
from app.core.llm.providers.base import BaseLLMProvider
from app.core.llm.providers.deepseek import DeepSeekProvider
# QwenProvider 将在下一 task 添加

__all__ = ["BaseLLMProvider", "DeepSeekProvider"]
```

- [ ] **Step 4: 写单元测试**

```python
# backend/tests/unit/test_llm_provider.py
import pytest
from unittest.mock import AsyncMock, patch
from app.core.llm.providers.deepseek import DeepSeekProvider


@pytest.mark.asyncio
async def test_deepseek_invoke_returns_string():
    """测试 DeepSeek invoke 返回字符串"""
    with patch("openai.resources.chat.completions.AsyncCompletions.create") as mock_create:
        mock_create.return_value = AsyncMock(
            choices=[AsyncMock(message=AsyncMock(content="Hello World"))]
        )
        provider = DeepSeekProvider(api_key="test-key")
        result = await provider.invoke([{"role": "user", "content": "Hi"}])
        assert result == "Hello World"
        assert provider.model_name == "deepseek-chat"


@pytest.mark.asyncio
async def test_deepseek_stream_yields_tokens():
    """测试 DeepSeek stream 逐 token 返回"""

    async def mock_stream(*args, **kwargs):
        chunk1 = AsyncMock(choices=[AsyncMock(delta=AsyncMock(content="Hello "))])
        chunk2 = AsyncMock(choices=[AsyncMock(delta=AsyncMock(content="World"))])
        chunk3 = AsyncMock(choices=[AsyncMock(delta=AsyncMock(content=None))])
        for chunk in [chunk1, chunk2, chunk3]:
            yield chunk

    with patch("openai.resources.chat.completions.AsyncCompletions.create") as mock_create:
        mock_create.return_value = mock_stream()

        provider = DeepSeekProvider(api_key="test-key")
        tokens = []
        async for token in provider.stream([{"role": "user", "content": "Hi"}]):
            tokens.append(token)

        assert tokens == ["Hello ", "World"]


def test_provider_supports_tools():
    """DeepSeek 应支持 Function Calling"""
    provider = DeepSeekProvider(api_key="test-key")
    assert provider.supports_tools is True
```

- [ ] **Step 5: 运行测试**

```bash
cd /Users/keta/dataanalytics/agentflow/backend
uv run pytest tests/unit/test_llm_provider.py -v
# 预期: 3 passed
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/llm/ backend/tests/
git commit -m "feat: add BaseLLMProvider and DeepSeekProvider with tests

- Abstract BaseLLMProvider with invoke/stream/embed interface
- DeepSeekProvider adapting OpenAI-compatible DeepSeek Chat API
- Unit tests with mocked OpenAI client
- Mermaid class diagram and sequence diagram in docstrings"
```

---

### Task 1.2.2: LLMFactory + LLMRouter

**Files:**
- Create: `backend/app/core/llm/factory.py`
- Create: `backend/app/core/llm/router.py`
- Create: `backend/tests/unit/test_llm_factory.py`

- [ ] **Step 1: 创建 LLMFactory**

```python
# backend/app/core/llm/factory.py
"""
LLMFactory — 使用工厂模式创建 Provider 实例

设计模式: **工厂方法 (Factory Method)**
    解耦 Provider 创建逻辑与使用逻辑。
    新增 Provider 只需在 FACTORY_MAP 中注册，无需改动调用方代码。

调用链 (Mermaid):
```mermaid
sequenceDiagram
    participant Service
    participant LLMFactory
    participant LLMRouter
    participant DeepSeekProvider
    participant QwenProvider

    Service->>LLMFactory: create("auto")
    LLMFactory->>LLMRouter: route(messages)
    LLMRouter-->>LLMFactory: "deepseek" (最低成本)
    LLMFactory->>DeepSeekProvider: new DeepSeekProvider()
    DeepSeekProvider-->>LLMFactory: provider instance
    LLMFactory-->>Service: provider
    Service->>DeepSeekProvider: invoke(messages)
    DeepSeekProvider-->>Service: response
```
"""

from app.core.llm.providers.base import BaseLLMProvider
from app.core.llm.providers.deepseek import DeepSeekProvider


# Provider 注册表 — 新增 Provider 在此添加
# 注册表模式 (Registry Pattern): 用 dict 解耦工厂的 if-else 分支
PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "deepseek": DeepSeekProvider,
    # "qwen": QwenProvider,   # Phase 2
    # "openai": OpenAIProvider,
}


class LLMFactory:
    """LLM Provider 工厂

    使用方式:
        factory = LLMFactory()
        provider = factory.create("deepseek")
        response = await provider.invoke([...])
    """

    @staticmethod
    def create(provider_name: str = "deepseek", **kwargs) -> BaseLLMProvider:
        """创建 LLM Provider 实例

        Args:
            provider_name: Provider 名称 (deepseek / qwen / openai)
            **kwargs: 传递给 Provider 构造函数的额外参数

        Returns:
            BaseLLMProvider 实例

        Raises:
            ValueError: 不支持的 provider_name
        """
        provider_class = PROVIDER_REGISTRY.get(provider_name)
        if not provider_class:
            available = ", ".join(PROVIDER_REGISTRY.keys())
            raise ValueError(
                f"Unsupported LLM provider: '{provider_name}'. "
                f"Available: {available}"
            )
        return provider_class(**kwargs)

    @staticmethod
    def list_providers() -> list[str]:
        """列出所有已注册的 Provider"""
        return list(PROVIDER_REGISTRY.keys())
```

- [ ] **Step 2: 创建 LLMRouter（占位）**

```python
# backend/app/core/llm/router.py
"""
LLMRouter — 智能模型路由

根据消息特征（复杂度、长度、语言）自动选择最合适的 LLM。
Phase 1: 默认返回 deepseek（后续 Phase 2-3 加入成本/延迟路由）。

设计模式: **策略 + 责任链**
    每个路由规则是一个 handler，匹配则返回，不匹配则传递给下一个。
"""

from app.core.llm.providers.base import BaseLLMProvider


class LLMRouter:
    """智能模型路由器"""

    DEFAULT_PROVIDER = "deepseek"

    async def route(self, messages: list[dict]) -> str:
        """根据消息内容选择最佳 Provider

        Phase 1 简化: 始终返回 deepseek
        Phase 2 升级: 短消息 → deepseek, 长上下文 → qwen, 代码 → moonshot
        """
        return self.DEFAULT_PROVIDER
```

- [ ] **Step 3: 写工厂测试**

```python
# backend/tests/unit/test_llm_factory.py
import pytest
from app.core.llm.factory import LLMFactory
from app.core.llm.providers.deepseek import DeepSeekProvider


def test_factory_create_deepseek():
    """工厂应正确创建 DeepSeekProvider"""
    provider = LLMFactory.create("deepseek", api_key="test")
    assert isinstance(provider, DeepSeekProvider)


def test_factory_create_invalid_raises():
    """不支持的 provider 应抛出 ValueError"""
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        LLMFactory.create("unknown_provider")


def test_factory_list_providers():
    """list_providers 应返回已注册的列表"""
    providers = LLMFactory.list_providers()
    assert "deepseek" in providers
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/llm/ backend/tests/
git commit -m "feat: add LLMFactory and LLMRouter

- LLMFactory with registry pattern for provider creation
- LLMRouter placeholder (always deepseek for Phase 1)
- Unit tests for factory creation and error handling
- Mermaid sequence diagram showing factory→provider call chain"
```

---

## 后续模块 (1.3—1.6) 将在下一批计划中详细展开

### 待实现概览

| Module | 核心文件 | 预估 Tasks |
|--------|---------|-----------|
| 1.3 对话引擎 | `chat_engine.py`, `checkpoint.py`, `chat.py` (API) | 8 tasks |
| 1.4 RAG 管道 | `pipeline.py`, `chunker.py`, `embedder.py`, `retriever.py`, `reranker.py` | 10 tasks |
| 1.5 聊天 UI | `ChatWindow.tsx`, `MessageBubble.tsx`, `chat.ts` (store) | 6 tasks |
| 1.6 部署 | `Dockerfile.*`, `nginx.conf`, 阿里云配置 | 6 tasks |

