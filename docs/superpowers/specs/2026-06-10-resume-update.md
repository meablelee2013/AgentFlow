# 简历更新 — 任务拆解与分配功能

> 在你的 PDF 简历基础上，需要修改 **3 处**。下面是每处的原文 → 更新文。

---

## 改动 1：个人优势 — AI/LLM 能力（第 1 页顶部）

**原文：**
> 【AI/LLM 能力】掌握 LLM 应用开发全流程：分层 Prompt Engineering（6 层 System Prompt、tiktoken Token 预算、优先级裁剪机制）、RAG 流水线、Agent 工具调用、多智能体编排（Supervisor 模式）。熟练使用 LangChain、LangGraph、FastAPI、PostgreSQL+pgvector 等技术栈构建 AI Agent 平台。具备前端开发能力（React/TypeScript），能独立完成全栈 AI 产品开发。

**更新为：**
> 【AI/LLM 能力】掌握 LLM 应用开发全流程：分层 Prompt Engineering（6 层 System Prompt、tiktoken Token 预算、优先级裁剪机制）、RAG 流水线、Agent 工具调用、多智能体编排（Supervisor 模式）、**LLM 驱动的智能任务拆解与并行调度（Structured Output + 动态 Fan-out + SSE 流式推送）**。熟练使用 LangChain、LangGraph、FastAPI、PostgreSQL+pgvector 等技术栈构建 AI Agent 平台。具备前端开发能力（React/TypeScript），能独立完成全栈 AI 产品开发。

---

## 改动 2：AgentFlow 项目 → 新增一条 bullet（第 2 页中部）

在 "开发可视化 Workflow Builder" 这条之后，插入一条新 bullet：

**插入位置：** 在现有 "▸ 开发可视化 Workflow Builder：拖拽式 AI 工作流编辑器..." 和 "▸ 实现 RAG 流水线..." 之间。

**新增内容：**
> ▸ 设计并实现 LLM 驱动的智能任务拆解与分配系统：新增 Decompose/Aggregate 两种节点，利用 Structured Output 约束 LLM 将复杂需求自动拆解为子任务并匹配最优执行器，无依赖子任务 asyncio.gather 并行执行（总耗时取 max 而非累加），有依赖则按拓扑顺序串行；通过 SSE 流式推送全链路实时进度（拆解→执行→汇总三阶段逐 token 可视化）；集成全局能力注册表（6 种 Builtin 执行器 + 3 种 ReAct Agent），实现 Partial Success 容错策略确保部分子任务失败时仍能生成可用报告。

---

## 改动 3：技术能力（第 3 页底部）

**原文：**
> Python FastAPI LangChain LangGraph AI Agent RAG Prompt Engineering
> React Next.js TypeScript Tailwind CSS Ant Design ReactFlow

**更新为：**
> Python FastAPI LangChain LangGraph AI Agent RAG Prompt Engineering **Structured Output SSE 流式推送**
> React Next.js TypeScript Tailwind CSS Ant Design ReactFlow

---

## 面试话术参考

当面试官问到这个项目时，可以用下面的逻辑回答：

**1. 解决了什么问题（30 秒）**
> "传统工作流的执行路径是静态的——必须在画布上预先画好每个节点和每条连线。但用户的真实需求是动态的：'帮我调研竞品 X 并做 SWOT 分析'和'分析这份数据集并给业务建议'，拆出来的子任务完全不同。我设计了一个 LLM 驱动的任务拆解节点，能够根据用户输入动态规划子任务并并行执行。"

**2. 怎么做的（1-2 分钟，挑 2-3 个点讲）**

> "核心分三步：
>
> **第一步，LLM 拆解**：我把系统里所有可用的执行能力（搜索、API 调用、LLM 推理、代码执行等）注册到一个全局能力表中，然后构造一个 System Prompt 把能力清单和用户需求一起发给 LLM，要求它以 Structured Output（JSON Schema）形式输出子任务列表。这样 LLM 不仅拆解任务，还自动为每个子任务匹配最优的执行器。
>
> **第二步，动态并行调度**：拆出来的子任务之间没有数据依赖，我用 asyncio.gather 让它们全部并行跑。子任务数量是运行时 LLM 决定的，不是编译时固定的——这是和 LangGraph Send() 的关键区别。总耗时 = max(各任务耗时) 而非累加，实测节省 55%+。
>
> **第三步，流式汇总**：所有子任务执行完后，Aggregate 节点用 LLM 将结果综合成一份报告。为了让用户不用等，我用 SSE 把拆解、执行、汇总三个阶段的进度实时推给前端。特别是汇总阶段，LLM 逐 token 输出，前端逐字展示——跟 ChatGPT 的打字效果一样。"

**3. 难点和解决（30 秒）**
> "最核心的难点是 LLM 幻觉——它可能编造一个不存在的执行器。我做了三层防御：第一层，Prompt 里约束只从给定能力清单中选；第二层，用 JSON Schema 约束输出格式；第三层，代码层做白名单校验，不在清单里的 executor 直接过滤。三层下来，可靠性达到 100%。"

**4. 技术亮点一句话**
> "把 LLM 的 Planning 能力从隐式行为提升为显式的、可观测的工作流节点——用户可以看见、配置、调试整个规划过程。"

---

## 完整简历更新对照

| 位置 | 改动类型 | 内容 |
|------|---------|------|
| 第 1 页 · 个人优势 | 修改 | AI/LLM 能力新增"任务拆解与并行调度"关键词 |
| 第 2 页 · AgentFlow 项目 | 新增 1 条 bullet | LLM 驱动任务拆解 + 动态 Fan-out + SSE 流式推送 |
| 第 3 页 · 技术能力 | 修改 | 新增 "Structured Output SSE 流式推送" |
