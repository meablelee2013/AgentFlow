# 业务 API 能力注册表 — 设计方案

> 📅 2026-06-10 | 状态：📝 设计阶段（待实现）

---

## 一、要解决什么问题

当前 AgentFlow 的能力注册表只有 6 个通用 Builtin（web_search、chat、http_api、rag、database、code）和 3 个 Agent（analyst、coder、writer）。

**接入真实企业系统时，需要回答一个问题：**

> "用户问'我的订单到哪了'，系统怎么知道该调哪个 API？"

如果在代码里每种业务都写一个专用节点（OrderNode、LogisticsNode、RefundNode...），每接一个新公司就得写一堆代码。如果不约束直接让 LLM 去选裸 URL，可靠性太低。

**目标：新增一个业务 API 只加一条配置，不改代码。**

---

## 二、核心设计

### 2.1 一句话概括

**能力层面做细分（每种业务一个能力 ID），执行层面做统一（共用 http_api 执行器）。**

```
┌──────────────────────────────────────────────────────────────────┐
│                    Capability Registry                             │
│                                                                   │
│  ┌─ Builtin（通用能力，不可配置）────────────────────────────┐    │
│  │  web_search    → DDG 搜索                                  │    │
│  │  chat          → LLM 推理                                  │    │
│  │  code          → Docker 沙箱执行                           │    │
│  │  ...                                                       │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                   │
│  ┌─ Business APIs（业务能力，纯配置，不改代码）──────────────┐    │
│  │                                                             │    │
│  │  erp:order_query    → POST https://erp.company.com/api/    │    │
│  │                        orders/search                       │    │
│  │                                                             │    │
│  │  erp:product_query  → GET  https://erp.company.com/api/    │    │
│  │                        products/{id}                       │    │
│  │                                                             │    │
│  │  erp:logistics      → GET  https://erp.company.com/api/    │    │
│  │                        logistics/{tracking_id}             │    │
│  │                                                             │    │
│  │  erp:refund_query   → POST https://erp.company.com/api/    │    │
│  │                        refunds/search                      │    │
│  │                                                             │    │
│  │  crm:customer_info  → GET  https://crm.company.com/api/    │    │
│  │                        customers/{id}                      │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                   │
│  两者对 Decompose 完全透明 — 都只是 ExecutorCapability 对象        │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 能力定义格式

每条业务 API 是一个 `ExecutorCapability`，用 `executor_config` 描述 HTTP 细节：

```python
ExecutorCapability(
    # ── 对 LLM 可见的语义描述 ──
    id="erp:order_query",
    type="builtin_node",
    label="订单查询",
    description=(
        "根据订单号、用户ID或时间范围查询订单信息，"
        "返回订单状态、金额、商品列表、物流单号。"
        "适合处理'我的订单到哪了'、'最近有哪些订单'等查询。"
    ),
    input_schema={
        "order_id":  {"type": "string",  "required": False, "description": "订单号"},
        "user_id":   {"type": "string",  "required": False, "description": "用户ID"},
        "date_from": {"type": "string",  "required": False, "description": "开始日期"},
        "date_to":   {"type": "string",  "required": False, "description": "结束日期"},
    },

    # ── 对执行器可见的 HTTP 配置 ──
    executor_config={
        "url": "https://erp.company.com/api/orders/search",
        "method": "POST",
        "auth": "credential:erp_token",            # 引用 credential 系统
        "headers": {"Content-Type": "application/json"},
        "body_template": {                          # 模板渲染后发送
            "order_id": "{{order_id}}",
            "user_id": "{{user_id}}",
            "date_range": {
                "from": "{{date_from}}",
                "to": "{{date_to}}"
            },
        },
        "response_path": "data.orders",            # JSONPath 提取
        "timeout": 30,
        "retry_count": 1,
    },
)
```

**LLM 看到的是前者（语义描述 + 参数说明），执行器用的是后者（URL + Method + Template），两者通过 `id` 关联。**

### 2.3 执行流程

```
Decompose 发出:
  { executor: "erp:order_query", input: { user_id: "U123" } }

     │
     ▼
Fan-out 调度器:
  1. registry.get("erp:order_query")  → 拿到 ExecutorCapability
  2. 判断 type == "builtin_node"  → 走 _execute_builtin
  3. 发现 executor_config 存在  → 走统一 HTTP 执行器
  4. render(body_template, input) → '{"user_id": "U123"}'
  5. 用 credential:erp_token 签发请求
  6. POST → 解析 response_path → 返回结构化数据
```

**对 Decompose 来说，`erp:order_query` 和 `web_search` 没有任何区别——都只是一个能力 ID。**

---

## 三、对比三种方案

| 维度 | 方案 A：每种业务一个专用节点 | 方案 B：LLM 自由查 URL 表 | **方案 C：注册表 + 统一执行器** |
|------|---------------------------|--------------------------|-------------------------------|
| **新增一个业务 API** | 写 Python + 前端配置面板，半天 | 加一行 URL 到表里，但不可靠 | **加一条配置，5 分钟** |
| **LLM 选错风险** | 低（节点语义明确，用户手动连线） | **高**（裸 URL，LLM 可能编造不存在的 endpoint） | **低**（能力 ID 是语义化的 + input_schema 约束参数） |
| **跨公司复用** | ❌ 不能（每个公司的 API 不同） | ✅ 能 | ✅ 能 |
| **参数校验** | ✅ 有（代码层） | ❌ 无（LLM 自己编参数） | ✅ 有（`input_schema` 自动校验） |
| **鉴权管理** | 分散在各节点代码里 | 分散在 URL 表里 | ✅ 统一走 `credential` 系统 |
| **非技术人员可维护** | ❌ 不能（需要写代码） | ❌ 不能（需要了解 HTTP） | ✅ 能（**屏蔽了 HTTP 细节**，运维在后台填表单即可） |
| **Agent 与后端隔离** | 同方案 C | 同方案 C | **HTTP 天然无状态 + API Gateway 限流熔断** |
| **适合阶段** | Demo / 概念验证 | — | **生产环境** |

---

## 四、与现有 http_api 节点的关系

**结论：不矛盾，而是互补。**

| | 现有 http_api 节点 | 未来业务 API 能力 |
|------|-------------------|-------------------|
| **使用方式** | 在画布上**手动拖拽**一个 http_api 节点，填 URL、Method | 在配置界面**注册一条能力**，Decompose **自动选用** |
| **适用场景** | 静态工作流："我提前知道要调这个 API" | 动态任务拆解："用户问什么，LLM 决定调哪个 API" |
| **谁来决定用哪个** | 画工作流的人 | **LLM** |
| **底层执行器** | `nodes/http_api.py` | **同一个** `nodes/http_api.py` |

两者底层共用同一个 HTTP 执行器，区别只在于**被调用的方式**——一个是被工作流固定连线触发，一个是被 Decompose 的 LLM 规划触发。

---

## 五、配置管理

### 5.1 存储方式

业务 API 能力不写在代码里，而是存到数据库（`business_capabilities` 表）或配置文件（`business_apis.yaml`）。

**推荐方案：数据库 + 管理后台**（方便非技术人员维护）

```sql
CREATE TABLE business_capabilities (
    id              TEXT PRIMARY KEY,       -- "erp:order_query"
    label           TEXT NOT NULL,          -- "订单查询"
    description     TEXT NOT NULL,          -- 给 LLM 看的语义描述
    input_schema    JSONB NOT NULL,         -- 参数定义
    executor_config JSONB NOT NULL,         -- HTTP 配置（url/method/auth/body_template）
    credential_id   TEXT,                   -- 引用的凭证 ID
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

CapabilityRegistry 启动时从数据库加载，合并到内置能力清单中。

### 5.2 管理方式

提供 REST API 管理业务能力：

```
GET    /api/v1/business-capabilities          # 列表
POST   /api/v1/business-capabilities          # 新增一条
PUT    /api/v1/business-capabilities/{id}     # 修改
DELETE /api/v1/business-capabilities/{id}     # 删除
POST   /api/v1/business-capabilities/{id}/test  # 测试连通性
```

前端提供一个简单的表单页，填入：名称、描述、URL、Method、Headers、Body 模板、Response JSONPath。

---

## 六、安全与隔离

### 6.1 Agent 与后端的隔离策略

```
┌──────────┐     HTTP      ┌──────────────┐     HTTP      ┌──────────┐
│  Agent   │ ──────────────▶│  API Gateway │ ──────────────▶│  后端    │
│          │                │  (Nginx/Kong)│                │          │
│          │ ◀──────────────│              │ ◀──────────────│          │
└──────────┘                └──────────────┘                └──────────┘
                                   │
                            ┌──────┴──────┐
                            │ 限流 (rate limit)
                            │ 鉴权 (API Key)
                            │ 超时 (30s disconnect)
                            │ 熔断 (circuit breaker)
                            │ 日志 (audit log)
                            └─────────────┘
```

- **Agent 挂了** → 对后端零影响（HTTP 是无状态的）
- **后端挂了** → Agent 收到 5xx，标记子任务 failed，不影响其他子任务
- **生产环境加强**：不同重要级别的业务 API 用不同的 Gateway 配置（查订单 10s 超时，查报表 60s 超时）

### 6.2 鉴权统一管理

```
业务 API 声明:   credential_id = "erp_token"
                       │
                       ▼
Credential 系统:  {
                    auth_type: "bearer",
                    token: "eyJhbG...",        ← Fernet 加密存储
                    expires_at: "2026-06-11",
                  }
                       │
                       ▼
HTTP 执行器:      Authorization: Bearer eyJhbG...
```

**不同环境用不同凭证**——开发环境连测试 ERP，生产环境连正式 ERP，只需改凭证配置，不动能力定义。

---

## 七、实施路线

| 阶段 | 内容 | 预估 |
|------|------|------|
| **Phase 1** | `ExecutorCapability` 新增 `executor_config` 字段，http_api 执行器支持从 `executor_config` 读取配置 | 半天 |
| **Phase 2** | CapabilityRegistry 新增 `register_business()` 方法，支持从 YAML/JSON 文件加载业务能力 | 半天 |
| **Phase 3** | 数据库模型 `business_capabilities` + CRUD API | 1 天 |
| **Phase 4** | 前端管理页面（业务能力列表 + 新增/编辑表单 + 测试连通性按钮） | 1 天 |
| **Phase 5** | API Gateway 限流/熔断/鉴权集成 | 1 天 |
| **Phase 6** | 文档 + 示例（电商场景：订单/商品/物流/退款 4 个能力的完整配置） | 半天 |

---

## 八、与现有代码的关系

| 现有模块 | 改动方式 |
|---------|---------|
| `capability_registry.py` | `register_business()` 从 DB/YAML 加载业务能力 |
| `ExecutorCapability` | 新增 `executor_config: dict` 字段 |
| `fanout.py` · `_execute_builtin()` | http_api 分支增加从 `executor_config` 取 URL/Method/Body 的逻辑 |
| `nodes/http_api.py` | 已有 URL/Method/Body/Auth 逻辑，只需增加 `executor_config` 参数入口 |
| `schema.py` | 不变（`SubTask.input` 已经能承载任意参数） |
| `nodes/decompose.py` | 不变（LLM 看到的是 `ExecutorCapability` 的语义描述，不关心底层是 HTTP 还是代码） |

---

## 九、与 Agent 调用公司后端的结合

当 Decompose 将业务 API 注册为能力后，整个流程变为：

```
用户: "帮我查一下 U123 最近三个月有哪些订单，有没有退款的"

  → Decompose:
      task_1: erp:order_query   { user_id: "U123", date_from: "2026-03-10", date_to: "2026-06-10" }
      task_2: erp:refund_query  { user_id: "U123", date_from: "2026-03-10", date_to: "2026-06-10" }
      task_3: chat              { prompt: "基于订单和退款数据汇总..." }  [depends_on: task_1, task_2]

  → task_1、task_2 并行调后端（通过 API Gateway，鉴权透明）
  → task_3 拿到两个结果后生成用户友好的回复
```

整个过程代码零改动——只是新增了两条业务能力配置。
