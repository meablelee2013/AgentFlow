# Decompose 测试用例 & 预期输出

> 用于验证 Task Decomposition 管道的标准测试用例集

---

## 用例 1：双对象对比调研

**输入：**
```
对比分析特斯拉和比亚迪在2025年Q1的财务表现，包括营收、利润率、交付量，并给出投资建议
```

**预期拆解（2-4 个子任务）：**

| 子任务 | Executor | 描述 | 并行？ |
|--------|----------|------|--------|
| task_1 | `web_search` | 搜索特斯拉 2025 Q1 财务数据 | ✅ 与 t2 并行 |
| task_2 | `web_search` | 搜索比亚迪 2025 Q1 财务数据 | ✅ 与 t1 并行 |
| task_3 | `chat` | 对比分析两家数据并给出投资建议 | 等待 t1, t2 |

**预期结果：**
- 3 个子任务全部完成
- Aggregate 输出包含营收/利润率/交付量对比 + 投资建议
- 总耗时 ≈ 最慢的搜索（~1-2s） + chat（~2-3s），因为搜索并行

**关键验证点：**
- ✅ 两个搜索任务确实并行执行（t1 和 t2 的 duration_ms 重叠）
- ✅ chat 任务确保拿到了两个搜索结果后才执行
- ✅ Aggregate 报告包含具体数据和投资建议

---

## 用例 2：简单问答（不应过度拆解）

**输入：**
```
What is the capital of France?
```

**预期拆解（1 个子任务）：**

| 子任务 | Executor | 描述 |
|--------|----------|------|
| task_1 | `chat` | 回答法国首都是什么 |

**预期结果：**
- 只有 1 个子任务
- 直接回答 "Paris"

**关键验证点：**
- ✅ **这是最重要的测试** — 验证 LLM 不会过度拆解简单问题
- ✅ 如果拆出 2+ 个子任务，说明 prompt 需要调整

---

## 用例 3：技术调研 + 报告生成

**输入：**
```
Research the latest advancements in quantum computing in 2025, identify the top 3 companies leading the field, and write a summary report with their key breakthroughs.
```

**预期拆解（2-3 个子任务）：**

| 子任务 | Executor | 描述 | 并行？ |
|--------|----------|------|--------|
| task_1 | `web_search` | 搜索 2025 量子计算最新进展 | ✅ 与 t2 并行 |
| task_2 | `web_search` | 搜索量子计算领先公司 | ✅ 与 t1 并行 |
| task_3 | `chat` | 汇总生成技术报告 | 等待 t1, t2 |

**预期结果：**
- 搜索返回 2025 年量子计算进展资讯
- Aggregate 报告列出 3 家公司 + 各自突破
- 报告用英文，Markdown 格式

**关键验证点：**
- ✅ 搜索结果包含 2025 年时间戳
- ✅ 报告确实命名了 3 家公司

---

## 用例 4：单步搜索

**输入：**
```
搜索一下苹果公司今天的最新股价
```

**预期拆解（1 个子任务）：**

| 子任务 | Executor | 描述 |
|--------|----------|------|
| task_1 | `web_search` | 搜索苹果最新股价 |

**预期结果：**
- 1 个子任务，直接用搜索完成
- 不额外创建一个 chat 去做"总结"（那是浪费）

**关键验证点：**
- ✅ 不会拆成 "搜索 + 汇总" 两个任务（过度拆解）
- ✅ 验证 LLM 理解"搜索就够了"

---

## 用例 5：数据分析 + 写作

**输入：**
```
Analyze the pros and cons of remote work vs office work based on recent studies, and write a balanced 500-word article suitable for a corporate blog.
```

**预期拆解（2-3 个子任务）：**

| 子任务 | Executor | 描述 | 并行？ |
|--------|----------|------|--------|
| task_1 | `web_search` | 搜索远程办公 vs 办公室的最新研究 | - |
| task_2 | `chat` | 基于研究数据撰写 500 字文章 | 等待 t1 |

**预期结果：**
- 搜索返回多项研究数据
- 文章约 500 字，平衡正反面
- 适合企业博客的语气

**关键验证点：**
- ✅ 搜索结果被正确传递给 chat
- ✅ 文章长度接近 500 字

---

## 用例 6：多维度竞品分析

**输入：**
```
帮我做一份完整的竞品分析：竞品A和竞品B。需要包括产品功能对比、定价策略、用户评价、市场份额。最后给出我方的竞争策略建议。
```

**预期拆解（4-5 个子任务）：**

| 子任务 | Executor | 描述 | 并行？ |
|--------|----------|------|--------|
| task_1 | `web_search` | 搜竞品A的功能和定价 | ✅ 全部并行 |
| task_2 | `web_search` | 搜竞品B的功能和定价 | ✅ |
| task_3 | `web_search` | 搜竞品A和B的用户评价 | ✅ |
| task_4 | `web_search` | 搜竞品A和B的市场份额 | ✅ |
| task_5 | `chat` | 汇总生成竞品分析报告 + 策略建议 | 等待所有搜索 |

**预期结果：**
- 4 个搜索并行执行（如果 LLM 聪明的话）
- 最终报告包含完整的对比表格和策略建议

**关键验证点：**
- ✅ 多个搜索真正并行（总耗时 ≈ 最慢的搜索 + chat，而非累加）
- ✅ 报告包含所有要求的维度

---

## 测试检查清单

运行测试脚本：
```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/test_decompose_cases.py
```

| 检查项 | 用例 | 期望 |
|--------|------|------|
| 不过度拆解简单问题 | 用例 2, 4 | subtask_count ≤ 2 |
| 复杂任务充分拆解 | 用例 1, 6 | subtask_count ≥ 3 |
| 搜索类任务使用 web_search | 用例 1-6 | web_search in executors |
| 无 LLM halucination (不虚构 executor) | 全部 | 所有 executor 在 enabled 列表中 |
| 并行执行生效 | 用例 1, 3, 6 | 独立的搜索任务同时执行 |
| Aggregate 包含所有子任务结果 | 全部 | 报告中引用每个子任务的数据 |
| ExecutionTrace 正确 | 全部 | total = completed + failed |

---

## 常见失败模式

| 问题 | 表现 | 原因 | 修复 |
|------|------|------|------|
| 过度拆解 | 简单问题拆 5 个任务 | prompt 太激进 | 加强 "minimize count" 指令 |
| 拆解不足 | 复杂任务只拆 1 个 | prompt 太保守 | 例子不够丰富 |
| 虚构 executor | 用了未注册的 executor | LLM 自由发挥 | validator 拦截 + 加强 prompt 约束 |
| 假并行 | 任务标记为并行但实际串行 | 未正确使用 gather | 检查 fanout.py |
| 汇总丢失数据 | 报告中少了某个子任务的结果 | prompt 不够强调完整性 | Aggregate prompt 加 "引用所有子任务" |
