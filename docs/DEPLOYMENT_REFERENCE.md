# AgentFlow 部署与配置参考

> 最后更新：2026-06-06

---

## 一、快速访问地址

| 服务 | URL | 说明 |
|------|-----|------|
| **Frontend** | http://localhost:5173 | React SPA |
| **Backend API** | http://localhost:8000 | FastAPI |
| **Swagger UI** | http://localhost:8000/docs | 交互式 API 文档 |
| **OpenAPI JSON** | http://localhost:8000/openapi.json | 机器可读 Schema |
| **Health Check** | http://localhost:8000/health | K8s liveness probe |
| **SearXNG** | http://localhost:8080 | 搜索服务 Web UI |
| **PostgreSQL** | `localhost:5434` | 用 Navicat/TablePlus 连接 |
| **Redis** | `localhost:6379` | `redis-cli` 连接 |

---

## 二、Docker Compose 服务清单

启动命令：`docker compose up -d`

| 服务 | 镜像 | 端口 | 用途 | 依赖 |
|------|------|------|------|------|
| `db` | `pgvector/pgvector:pg16` | `5434:5432` | PostgreSQL + pgvector 向量存储 | — |
| `redis` | `redis:7-alpine` | `6379:6379` | Celery broker + 缓存 | — |
| `searxng` | `searxng/searxng:latest` | `8080:8080` | 自部署元搜索引擎 | — |
| `api` | `deploy/docker/Dockerfile.api` | `8000:8000` | FastAPI 后端 | db, redis, searxng |
| `frontend` | `deploy/docker/Dockerfile.frontend` | `5173:5173` | React 前端 | api |

SearXNG 配置文件：
- `deploy/searxng/settings.yml` — 搜索引擎开关、语言、安全搜索
- `deploy/searxng/limiter.toml` — 速率限制

---

## 三、全部可配置环境变量

> 以下变量均在 `.env` 文件中配置。`.env.example` 包含所有变量的模板。

### 3.1 应用配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_NAME` | `AgentFlow` | 应用名称（显示在 Swagger） |
| `APP_VERSION` | `0.1.0` | 版本号 |
| `DEBUG` | `false` | 调试模式 |
| `SECRET_KEY` | `change-me-in-production` | JWT 签名密钥（**生产环境必须改**） |

### 3.2 数据库

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DATABASE_URL` | `postgresql+asyncpg://agentflow:agentflow@localhost:5434/agentflow` | PostgreSQL 连接串 |

> Docker 内部用 `db:5432`，宿主机用 `localhost:5434`（端口映射）

### 3.3 Redis

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串 |

### 3.4 LLM Provider

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API 密钥（**必填**） |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `QWEN_API_KEY` | — | 通义千问 API 密钥（可选） |
| `QWEN_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 通义千问 API 地址 |

### 3.5 Embedding

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding 模型名 |
| `VECTOR_DIMENSION` | `384` | 向量维度（模型决定，别随便改） |

### 3.6 Web Search

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SEARCH_BACKEND` | `searxng` | 搜索后端：`searxng` / `duckduckgo` / `tavily` / `brave` |
| `SEARXNG_URL` | `http://localhost:8080` | SearXNG 服务地址 |
| `TAVILY_API_KEY` | — | Tavily API 密钥（仅 tavily 后端需要） |
| `BRAVE_API_KEY` | — | Brave Search API 密钥（仅 brave 后端需要） |

### 3.7 可观测（Phase 3 预留）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PROMETHEUS_PORT` | `9090` | Prometheus Metrics 端口（未实现） |

---

## 四、配置文件位置一览

| 文件 | 用途 | 是否提交 Git |
|------|------|-------------|
| `.env` | 实际环境变量 | ❌ `.gitignore` |
| `.env.example` | 环境变量模板（无敏感值） | ✅ |
| `backend/app/config.py` | Pydantic Settings（读 .env） | ✅ |
| `docker-compose.yml` | 容器编排 | ✅ |
| `deploy/searxng/settings.yml` | SearXNG 配置 | ✅ |
| `deploy/searxng/limiter.toml` | SearXNG 限流 | ✅ |
| `docs/config.md` | 本地开发连接信息 | ❌ `.gitignore` |
| `deploy/docker/Dockerfile.api` | API 镜像 | ✅ |
| `deploy/docker/Dockerfile.frontend` | 前端镜像 | ✅ |

---

## 五、生产环境部署差异

开发环境（现在）→ 生产环境要改的：

| 项目 | 开发 | 生产 |
|------|------|------|
| `SECRET_KEY` | `change-me-in-production` | 随机 64 位字符串 |
| `DATABASE_URL` | `localhost:5434` | 阿里云 RDS 地址 |
| `REDIS_URL` | `localhost:6379` | 阿里云 Redis 地址 |
| `SEARXNG_URL` | `localhost:8080` | `http://searxng:8080`（容器内 DNS） |
| `DEBUG` | `true`（本地） | `false` |
| CORS origins | `localhost:5173` | 你的域名 |
| SSL | 无 | Nginx + Let's Encrypt |

---

## 六、如何添加新配置

```python
# 1. 在 backend/app/config.py 中添加字段
class Settings(BaseSettings):
    MY_NEW_CONFIG: str = "default-value"

# 2. 在 .env.example 中添加说明
# MY_NEW_CONFIG=your-value

# 3. 在代码中使用
from app.config import settings
value = settings.MY_NEW_CONFIG
```
