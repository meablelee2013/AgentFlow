# Agent 循环安全防护系统设计

> 面试高频考点：AI Agent 的循环终止、死循环防护、Token 预算管理、可观测性

## 1. 背景与问题

### 1.1 为什么 Agent 需要循环防护？

ReAct（Reasoning + Acting）模式的 Agent 本质上是 LLM ↔ Tool 的循环：

```
LLM 推理 → 决定调用工具 → 执行工具 → 结果反馈给 LLM → 继续推理 → ...
```

这个循环存在三类典型风险：

| 风险类别 | 具体表现 | 案例 |
|----------|----------|------|
| **逻辑死循环** | LLM 反复调用同一工具得到相同结果，无法收敛 | 每次查天气都得到"35°C"，却连续查 5 次 |
| **资源耗尽** | 上下文窗口被不断追加的消息填满，Token 费用失控 | 单次对话消耗 80K tokens |
| **信心崩塌** | 工具返回空结果/错误，LLM 不知道如何优雅退出 | 搜索"不存在的概念"反复尝试 |

### 1.2 现有方案的不足

改造前，AgentFlow 的循环终止仅依赖简单计数：

```python
MAX_TOOL_ITERATIONS = 5  # 硬编码

if tool_count >= MAX_TOOL_ITERATIONS:
    return "end"  # 强制终止
```

**缺陷：**
- 不知道"为什么终止"——是正常完成还是异常退出
- 无法区分"5 轮有效推理"和"5 轮重复无效调用"
- 缺少资源预算控制，单次对话 Token 无上限
- 没有可观测性——出了问题只能看日志

---

## 2. 设计思路：五层组合策略

### 2.1 架构总览

```
                    ┌──────────────────────────────────────┐
                    │           LoopGuard 安全网关          │
                    │                                      │
   Agent 循环 ──────┤  Layer 1  业务层: 任务完成检测        │
   (每轮迭代)       │  Layer 2  安全层: 最大步数阈值        │
                    │  Layer 3  性能层: Token 比率熔断      │
                    │  Layer 4  交互层: 用户取消接口        │
                    │  Layer 5  生产层: 去重 + 置信度       │
                    │                                      │
                    └──────────┬───────────────────────────┘
                               │
                    ┌──────────▼───────────────────────────┐
                    │     Prometheus /metrics               │
                    │     Grafana Dashboard                 │
                    └──────────────────────────────────────┘
```

**设计原则：纵深防御（Defense in Depth）** — 每一层独立运作，任一层触发即可终止，不依赖单一机制。

### 2.2 各层详解

#### Layer 1 — 业务层：任务状态机

保留 LangGraph `_should_continue()` 的条件边路由逻辑——LLM 不再产生 `tool_calls` 即视为任务完成。

```python
def _should_continue(self, state):
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"  # 继续循环
    return "end"        # 正常终止
```

这是最理想的终止路径，代表 Agent"自我感知"任务完成。

#### Layer 2 — 安全层：最大步数阈值

```python
if self.iteration > self.config.max_iterations:
    return LoopVerdict.STOP_MAX_ITERATIONS
```

设计考量：
- 每轮迭代（LLM 调用 + 工具执行）计为一步
- 阈值通过 `Settings.MAX_TOOL_ITERATIONS` 配置（默认 5）
- 这是**最后防线**——如果 LLM 始终输出 tool_calls，第 6 轮强制终止

#### Layer 3 — 性能层：Token 比率熔断 ★ 面试重点

**不使用简单的绝对 Token 计数，而是采用比率模型：**

```
                    cumulative_input_tokens
    token_ratio = ────────────────────────────
                  context_window - max_output_tokens
```

为什么这么设计？

| 方案 | 问题 |
|------|------|
| `total_tokens > 8000` | 不考虑模型差异（4K vs 128K 上下文），硬编码上限不通用 |
| `token_ratio > 0.8` | **自适应**——128K 模型能承受更多，4K 模型更早触发 |

三级响应：

```
ratio < 0.6  → CONTINUE   正常执行
ratio ≥ 0.6  → WARN       提示 Agent 尽快收尾
ratio ≥ 0.8  → STOP       强制熔断，返回已有结果
```

关键实现细节：
- 使用 `cumulative_input_tokens`（累计输入），因为上下文窗口主要由输入填充
- 分母减去 `max_output_tokens` 为输出预留空间
- 每次 LLM 调用后从 `response.response_metadata.token_usage` 提取真实 usage

#### Layer 4 — 交互层：用户取消

```python
# API: POST /agent/{thread_id}/cancel
LoopGuard.request_cancel(thread_id)

# Guard 检查（每轮迭代前）
if self._is_cancelled():
    return LoopVerdict.STOP_CANCELLED
```

设计考量：
- 当前用内存 `set` 存储取消标志，单进程有效
- 后续可迁移到 Redis 实现跨进程取消
- Agent 完成当前 LLM 调用后优雅退出，不会强制杀进程

#### Layer 5 — 生产层：去重看门狗 + 置信度评分 ★ 面试重点

**5a. 去重看门狗（Dedup Watchdog）**

```python
# 连续 3 次工具调用结果完全相同 → 强制终止
last_n = tool_results[-window:]
if len(set(last_n)) == 1:
    return LoopVerdict.STOP_DEDUP
```

解决的问题：LLM 反复调用同一工具得到相同结果，但自己不知道在循环。

实际案例：
```
Round 1: web_search("北京天气") → "35°C 晴天"
Round 2: web_search("北京天气") → "35°C 晴天"  ← 完全重复
Round 3: web_search("北京天气") → "35°C 晴天"  ← 触发 STOP_DEDUP
```

**5b. 置信度评分（Confidence Scoring）**

每次工具调用后评估结果质量：

```python
# 启发式置信度估算
"Error: connection refused"      → 0.1  (明确错误)
"No results found"               → 0.2  (无结果)
"short"                          → 0.4  (内容不足)
"完整的有意义的结果..."           → 0.8  (正常)
```

触发条件：**连续 N 次置信度 < 阈值 → STOP_LOW_CONFIDENCE**（默认 N=2, 阈值=0.3）

关键设计：
- 支持显式传入 `confidence` 参数（如果模型支持 token_logprob）
- 非连续低置信度自动重置计数（偶发的搜索失败不应终止）
- 可配置 `LOW_CONFIDENCE_STREAK` 和 `CONFIDENCE_THRESHOLD`

---

## 3. 配置体系

所有参数通过 `backend/app/config.py` + `.env` 配置，运行时零代码修改：

```bash
# .env
MAX_TOOL_ITERATIONS=5         # 最大迭代轮次
CONTEXT_WINDOW=65536          # 模型上下文窗口（DeepSeek-v3 = 64K）
MAX_OUTPUT_TOKENS=2048        # 每轮最多输出 Token
TOKEN_WARN_RATIO=0.6          # 60% 触发警告
TOKEN_STOP_RATIO=0.8          # 80% 触发熔断
DEDUP_WINDOW=3                # 去重窗口大小
CONFIDENCE_THRESHOLD=0.3      # 低置信度阈值
LOW_CONFIDENCE_STREAK=2       # 连续低置信度触发次数
LLM_TIMEOUT_SECONDS=60        # 单次 LLM 调用超时
METRICS_ENABLED=true          # 启用 Prometheus 指标
```

---

## 4. 可观测性

### 4.1 Prometheus 指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `llm_call_total` | Counter | LLM 调用总次数（按 model/provider 分 label） |
| `llm_call_latency_seconds` | Histogram | LLM 调用延迟分布（bucket: 0.1/0.5/1/2/5/10/30/60s） |
| `llm_call_errors_total` | Counter | LLM 调用错误（按 error_type 分） |
| `llm_call_qps` | Gauge | 60s 滑动窗口 QPS |
| `agent_loop_verdict_total` | Counter | 各类 verdict 触发次数 |
| `agent_token_ratio` | Gauge | 当前 Token 使用比率 |
| `agent_confidence` | Gauge | 当前平均置信度 |

### 4.2 Grafana Dashboard

6 个面板，位于 `deploy/grafana/dashboard.json`：

```
┌───────────────────────┬───────────────────────┬───────────────────────┐
│  Loop Iterations      │  Token Usage Ratio    │  Action Confidence    │
│  (Gauge, 0-10)        │  (Gauge, 0-100%)      │  (Gauge, 0-1)         │
│  绿<4 橙<5 红≥5       │  绿<60% 橙<80% 红≥80% │  红<0.3 黄<0.7 绿≥0.7 │
├───────────────────────┴───────────────────────┴───────────────────────┤
│  LLM Latency P50/P90/P99 (Time Series, ms)                            │
├───────────────────────────────────────────────────────────────────────┤
│  LLM QPS (Time Series, req/s)                                         │
├───────────────────────────────────────────────────────────────────────┤
│  LoopGuard Verdicts (Stacked Time Series, 5m rate)                    │
└───────────────────────────────────────────────────────────────────────┘
```

### 4.3 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/metrics` | GET | Prometheus 抓取端点 |
| `/api/v1/agent/{tid}/cancel` | POST | 取消运行中的 Agent |
| `/api/v1/agent/{tid}/guard` | GET | 查看 Guard 状态摘要 |
| `/api/v1/agent/stats/llm` | GET | 实时 LLM 调用统计 JSON |

---

## 5. 代码架构

### 5.1 组件关系

```
app/core/engine/loop_guard.py        ← 独立可复用组件
    ├── LoopConfig (dataclass)       ← 配置对象
    ├── LoopVerdict (enum)           ← 7 种判决结果
    └── LoopGuard (class)            ← 核心安全网关

app/core/metrics/llm_metrics.py      ← Prometheus 集成
    ├── @track_llm_call              ← LLM 调用装饰器
    ├── SlidingWindow                ← QPS 滑动窗口
    ├── P99Tracker                   ← P50/P90/P99 计算
    └── record_verdict / update_guard_metrics  ← 指标更新

集成位置:
    agent_engine.py     → LoopGuard + @track_llm_call (主要目标)
    supervisor_engine.py → LoopGuard + @track_llm_call
    agent_executor.py    → LoopGuard + @track_llm_call
    chat_engine.py       → timeout + max_tokens (无循环)
```

### 5.2 LoopGuard 核心接口

```python
class LoopGuard:
    def check(
        self,
        input_tokens: int = 0,              # 最近一次 LLM 调用的输入 Token
        tool_results: list[str] | None = None,  # 累积的工具结果
    ) -> LoopVerdict: ...                   # 返回判决

    def record_token_usage(self, usage: dict): ...   # 记录 Token 用量
    def record_tool_result(self, result: str, confidence=None): ...  # 记录工具结果
    def request_cancel(thread_id): ...       # 类方法：标记取消
    def clear_cancel(thread_id): ...         # 类方法：清除取消

    @property
    def token_ratio(self) -> float: ...      # 当前 Token 比率
    @property
    def avg_confidence(self) -> float: ...   # 平均置信度
    @property
    def summary(self) -> dict: ...           # 完整状态摘要
```

### 5.3 Verdict 优先级

```
1. STOP_CANCELLED          (用户取消最高优先)
2. STOP_MAX_ITERATIONS     (安全阈值)
3. STOP_TOKEN_BUDGET       (资源熔断)
4. STOP_LOW_CONFIDENCE     (质量崩塌)
5. STOP_DEDUP              (死循环检测)
6. WARN                    (预警，不终止)
7. CONTINUE                (一切正常)
```

---

## 6. 面试要点：核心设计决策

### Q1: 为什么不用简单的 `total_tokens > N` 而用比率？

```
答：比率模型是自适应的。
  - Claude 200K 上下文窗口: ratio=0.8 → 160K tokens 才熔断
  - DeepSeek 64K: ratio=0.8 → 51K tokens 就熔断
  如果用绝对值 8000，对 200K 模型太保守，对 4K 模型太危险。
  
另外，用 input_tokens/(window-max_output) 而非 total/(window):
  - 上下文窗口主要被输入（历史消息）消耗
  - max_output_tokens 是为输出预留的空间
  - 如果输入已经占满窗口，输出空间不足会导致截断
```

### Q2: 去重看门狗为什么不直接用简单的"结果相等"？

```
答：用的是"连续 N 次相等"而非"任意 N 次重复"。
  
  - 连续重复 = 死循环特征（Agent 在同一轨迹上打转）
  - 非连续重复（如 Round 1 和 Round 5 查了同一个城市）= 可能是合理的
  
此外，跳过空字符串（falsy check），避免工具调用失败被误判为重复。
dedup_window 可配置，不同场景可调整灵敏度。
```

### Q3: 五层之间如何协作？

```
答：每一层独立运作，任一层触发即终止。

  - Layer 1 是"正常路径"——LLM 自我决定完成
  - Layer 2-3 是"资源路径"——防止 Token/迭代超限
  - Layer 4 是"人工路径"——用户随时可终止
  - Layer 5 是"质量路径"——检测异常的 Agent 行为模式

这种纵深防御设计确保没有单点故障：
  如果 LLM 始终输出 tool_calls → Layer 2 兜底
  如果每次 tool_calls 不一样但无进展 → Layer 5a 兜底
  如果结果看起来正常但都是垃圾 → Layer 5b 兜底
```

### Q4: 如何保证不误杀正常 Agent？

```
答：通过阈值设计避免误杀。

  - 去重窗口=3：Agent 偶尔两次相同结果是正常的（重试机制）
  - 置信度 streak=2：单次工具失败不会终止，连续失败才终止
  - Token 比率 60% 仅 WARN 不终止，80% 才熔断
  - 所有参数可通过 .env 配置，不同场景可调优
  
实际效果：正常 Agent 通常在 2-3 轮内完成（远低于 5 轮上限），
去重和置信度检查均不会触发。
```

### Q5: 可观测性为什么重要？

```
答：Agent 系统的核心挑战是"它是个黑盒"。

  - 没有可观测性 → 出了问题只能猜
  - 有了 /metrics + Grafana → 可以：
      * 看 Token 比率趋势判断是否有内存泄漏式的上下文膨胀
      * 看 P99 延迟判断 LLM 服务是否降级
      * 看 Verdict 分布判断哪种异常终止最常见
      * 设置告警：当 STOP_DEDUP 速率 > 0.1/min 时通知
  
Prometheus 指标是"生产就绪"的标准做法，面试中体现工程成熟度。
```

---

## 7. 测试覆盖

36 个单元测试覆盖所有判决路径：

```
TestMaxIterations:  4 个 — 正常/超限/自定义/大数据量
TestTokenRatio:     6 个 — 低于/警告/停止/累积/零分母/超标
TestCancel:         4 个 — 取消/恢复/隔离/幂等
TestDedup:          7 个 — 不足窗口/触发/不同/可调窗口/空字符串/尾部/禁用
TestConfidence:     9 个 — 高/低/未找到/重置/空/自定义阈值/显式覆盖
TestVerdictPriority: 3 个 — 停止>警告/取消优先/熔断优先
TestSummary:        3 个 — 摘要/比率/平均置信度
```

---

## 8. 后续演进

| 方向 | 优先级 | 说明 |
|------|--------|------|
| Redis 取消标志 | P1 | 跨进程取消 + 自动过期（当前内存 set 单进程） |
| LangGraph `interrupt()` | P1 | 工具执行前暂停等待用户确认（HITL） |
| Token 预算动态调整 | P2 | 根据实际窗口使用率自适应调整阈值 |
| DSL 编译器循环防护 | P2 | 用户自定义工作流的循环检测 |
| 前端取消按钮 | P2 | 配合 API 取消端点 |
