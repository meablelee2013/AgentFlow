# RAG 管道技术详解

> 本文档深入解释 AgentFlow 的 RAG（Retrieval-Augmented Generation）管道从文件解析到向量检索的完整技术链路。

---

## 一、整体流程概览

```
文件上传
  │
  ▼
① Parser 解析    →  原始文件 → 纯文本
  │
  ▼
② Chunker 分块   →  长文本 → 小块（每个块可独立检索）
  │
  ▼
③ Embedder 向量化 →  文本块 → 384 维浮点数向量
  │
  ▼
④ 存入 pgvector  →  content + embedding → document_chunks 表
  │
  ▼
⑤ 检索时          →  用户问题 → 向量 → 余弦距离 → Top-K chunks → 喂给 LLM
```

---

## 二、为什么要存向量，不能直接存文件吗？

**问题**：用户搜索 "Who works in Engineering?"，文件里有一行 `Alice,30,Engineering,80000`。怎么找到它？

**方案 A：直接存文件 + 关键词搜索**
```
SELECT * FROM documents WHERE content LIKE '%Engineering%';
```
- ❌ 用户搜 "tech staff" 找不到 "Engineering"
- ❌ 用户搜 "研发部门" 找不到 "Engineering department"  
- ❌ CSV 里是 `Engineering`，用户搜 `engineer` 找不到（大小写、单复数）

**方案 B：存向量 + 语义搜索**
```
question = "Who works in Engineering?"  → [0.1, -0.05, 0.23, ...] 384 dims
chunk_1  = "Alice, Engineering, 80000" → [0.09, -0.04, 0.21, ...] 384 dims
chunk_2  = "Bob, Marketing, 60000"     → [-0.03, 0.12, -0.08, ...] 384 dims

余弦距离(question, chunk_1) = 0.02  ← 很近！语义相似
余弦距离(question, chunk_2) = 0.87  ← 很远！不相关
```
- ✅ "tech staff" 和 "Engineer" 语义相近 → 向量也相近
- ✅ 中文 "研发" 和英文 "Engineering" 在嵌入空间也接近
- ✅ 关键词完全匹配不了的时候，语义还能匹配

**为什么不存文件里（比如 JSON 文件）？**
- PostgreSQL 支持 **索引加速**（pgvector 的 IVFFlat 索引），1 万条内 < 1ms
- 文件里你要自己写代码遍历计算余弦距离，100 万条 O(n) 全扫描
- 数据库支持 **事务、并发、备份、权限**，文件没有

---

## 三、Embedding 到底是什么？

### 3.1 直观理解

想象你有一个 384 维的"语义空间"。每个维度代表一个语义概念：

```
维度 0:  人类相关程度
维度 1:  数字相关程度  
维度 2:  技术相关程度
维度 3:  负面情绪程度
...
维度 383: 时间相关程度
```

一段文字经过 Embedder，在这 384 个维度上打分，得到一个坐标：

```
"Alice is an engineer"     → [0.8, 0.1, 0.9, 0.0, ..., 0.0]
"2 + 2 = 4"                → [0.0, 0.9, 0.1, 0.0, ..., 0.0]
"This product is terrible" → [0.3, 0.0, 0.0, 0.95, ..., 0.0]
```

相似的文本 → 相近的坐标 → 相近的向量。

### 3.2 TF-IDF 是怎么算出这些数字的？（我们的实现）

```
文档集合:
  Doc A: "Alice works in Engineering"
  Doc B: "Bob works in Marketing"

Step 1: 统计每个词出现了多少次（TF = Term Frequency）
  Doc A: alice=1, works=1, engineering=1
  Doc B: bob=1, works=1, marketing=1

Step 2: 统计每个词出现在多少篇文档里（DF = Document Frequency）
  works: 出现在 2 篇文档
  alice: 出现在 1 篇文档
  engineering: 出现在 1 篇文档

Step 3: 计算 TF-IDF
  TF-IDF(works, Doc A) = TF × log(N/DF) = 1 × log(2/2) = 1 × 0 = 0
  TF-IDF(alice, Doc A) = 1 × log(2/1) = 1 × 0.69 = 0.69

关键洞察: "works" 每篇文档都有 → 不重要 → TF-IDF = 0
          "alice" 只在 A 出现 → 很区分性 → TF-IDF = 0.69
```

**TF-IDF 的局限**：只看词频，不理解语义。`"engineer"` 和 `"developer"` 在我们的实现里是完全不同的两个词，向量不接近。

**Phase 2 升级方案**：all-MiniLM-L6-v2（384 维）或 text-embedding-3-small（512 维），这两个能理解语义："engineer" 和 "developer" 的向量会很接近。

---

## 四、向量是如何存储的？

### 4.1 数据库表结构

```sql
CREATE TABLE document_chunks (
    id          UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,          -- 原始文本（给人看、给 LLM 读）
    chunk_index INTEGER NOT NULL,       -- 第几个块
    embedding   VECTOR(384),            -- 384 维浮点数向量（给机器算距离）
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

### 4.2 实际存储的数据

```sql
SELECT chunk_index,
       LEFT(content, 50) AS content,
       vector_dims(embedding) AS dims,  -- 查看向量维度
       LEFT(embedding::text, 60) AS vector_preview  -- 向量的文本表示
FROM document_chunks;
```

结果：
```
 chunk_index | content              | dims | vector_preview
-------------+----------------------+------+-----------------------------------------
           0 | Row 1: name: Alice.. | 384  | [0.045,0.023,0.011,0.089,...]
```

**一行的存储大小**：
- content（文本）: ~100-1000 bytes
- embedding（向量）: 384 × 4 bytes = **1,536 bytes (1.5 KB)**
- 元数据: ~50 bytes
- **总计**: 约 2 KB 每块

10 万块 = 约 200 MB，完全在 PostgreSQL 的能力范围内。

---

## 五、检索时如何匹配？

### 5.1 余弦相似度

两个向量的夹角越小 → 方向越一致 → 语义越相似。

```
余弦相似度 = (A · B) / (|A| × |B|)

A = [0.8, 0.1, 0.9]     问题 "who works in Engineering?"
B = [0.7, 0.15, 0.85]   文本 "Alice, Engineering, 80000"
C = [0.1, 0.8, 0.05]    文本 "2 + 2 = 4"

A · B = 0.8×0.7 + 0.1×0.15 + 0.9×0.85 = 1.34  ← 点积大 = 夹角小 = 相似
A · C = 0.8×0.1 + 0.1×0.8 + 0.9×0.05 = 0.21  ← 点积小 = 夹角大 = 不相似
```

### 5.2 pgvector 的 `<=>` 运算符

```sql
-- pgvector 内置的余弦距离运算符
-- 返回值 0 = 完全相同（夹角 0°），1 = 完全不同（夹角 90°）
SELECT LEFT(content, 60) AS content,
       ROUND((embedding <=> question_vector)::numeric, 4) AS distance
FROM document_chunks
ORDER BY embedding <=> question_vector  -- 按距离升序
LIMIT 5;
```

### 5.3 为什么极快？

**没有索引时（全表扫描）**：
```
100 万条 × 384 维 × 4 bytes = 1.5 GB 数据
每条计算余弦距离 → 遍历 100 万次 → ~100ms
```

**有 IVFFlat 索引时**：
```
pgvector 把 100 万个向量分成若干个"列表"（cluster）
查询时只看最近的几个列表，跳过 95%+ 的数据
100 万条 → ~1ms
```

索引创建：
```sql
CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

| 数据量 | 无索引 | 有 IVFFlat 索引 |
|--------|--------|----------------|
| 1,000 条 | ~1ms | ~0.3ms |
| 10,000 条 | ~8ms | ~0.5ms |
| 100,000 条 | ~80ms | ~1ms |
| 1,000,000 条 | ~800ms | ~5ms |

---

## 六、完整检索 SQL 示例

```sql
-- 用户问: "Who works in Engineering?"
-- Step 1: 应用层把问题 Embedding 为向量 question_vector
-- Step 2: 执行 pgvector 余弦搜索
-- Step 3: 返回 top-3 chunks

SELECT dc.chunk_index,
       dc.content,
       d.filename,
       (1 - (dc.embedding <=> :question_vector)) AS similarity  -- 余弦相似度
FROM document_chunks dc
JOIN documents d ON dc.document_id = d.id
WHERE dc.embedding IS NOT NULL
ORDER BY dc.embedding <=> :question_vector  -- 余弦距离升序
LIMIT 3;
```

返回：
```
chunk_index | content                              | filename      | similarity
------------+--------------------------------------+---------------+-----------
          0 | Row 1: name: Alice | age: 30 | ...  | employees.csv | 0.94
          0 | Row 3: name: Charlie | age: 35 | ...  | employees.csv | 0.87
```

然后把这些 chunk 的内容拼成 context：
```
Context:
...Row 1: name: Alice | age: 30 | department: Engineering | salary: 80000
...Row 3: name: Charlie | age: 35 | department: Engineering | salary: 95000

Prompt to LLM:
"Based on the following information, answer the user's question:
{context}

Question: Who works in Engineering?"
```

---

## 七、关键代码路径

| 步骤 | 文件 | 类/方法 |
|------|------|---------|
| 解析 | `parsers/csv_parser.py` | `CsvParser.parse()` |
| 分块 | `chunker.py` | `DocumentChunker.split()` |
| 向量化 | `embedder.py` | `Embedder.embed()` |
| 存储 | `pipeline.py` | `RAGPipeline.ingest_file()` |
| 检索 | `retriever.py` | `HybridRetriever.search()` |
| 查询 | `pipeline.py` | `RAGPipeline.query()` |

---

## 八、Phase 2 升级路线

| 环节 | Phase 1 (当前) | Phase 2 |
|------|---------------|---------|
| Embedding | TF-IDF 384-dim（词频统计） | all-MiniLM-L6-v2（语义理解） |
| 检索 | 纯向量余弦搜索 | 混合检索：向量 + BM25 + RRF 融合 |
| 索引 | 无（数据少） | IVFFlat / HNSW 索引 |
| 分块 | 固定大小 + 递归 | 语义分块 + 重叠窗口 |
| 召回 | Top-K | Rerank（召回 20 → 精排 Top-5） |

---

## 九、面试题汇总

> 点击展开查看答案。

### Q1: 什么是 RAG？为什么需要 RAG？

<details>
<summary>展开答案</summary>

**RAG**（Retrieval-Augmented Generation）= 检索增强生成。

LLM 有两个致命问题：
1. **知识截止**：训练数据有截止日期，不知道最新信息
2. **幻觉**：不知道的事会编造

RAG 解决思路：**先检索，再回答**。
- 用户提问 → 从知识库检索相关文档 → 把文档和问题一起喂给 LLM → LLM 基于文档回答
- 优点：答案可溯源（有引用）、知识可更新（加文档就行）、减少幻觉（有事实约束）

```python
# 传统 LLM
answer = llm("Who works in Engineering?")  # 可能编造

# RAG
chunks = vector_search("Who works in Engineering?")  # 先检索
context = "\n".join([c.content for c in chunks])
answer = llm(f"Based on: {context}\n\nWho works in Engineering?")  # 有据可查
```
</details>

---

### Q2: Embedding 是什么？为什么相似文本的向量会相近？

<details>
<summary>展开答案</summary>

**Embedding** = 把文本映射到高维空间中的一个点（向量）。

核心原理：**分布式假设**——"一个词的含义由它周围的词决定"。
- "The cat sat on the mat" → cat 和 mat 总是出现在相似语境 → 向量相近
- 训练时模型学习：让语义相近的文本向量靠近，语义无关的文本向量远离

举例：
```
"Alice is an engineer"         → [0.8, 0.1, 0.9] 
"Bob is a software developer"  → [0.7, 0.15, 0.85]  ← 和上面接近（都是技术人员）
"The weather is nice today"    → [0.0, 0.5, 0.0]    ← 向量完全不同
```

为什么 384 维？维度越高，能编码的语义信息越多，但计算越慢。384 是轻量级的 sweet spot。
</details>

---

### Q3: 为什么用向量检索而不是直接用 SQL LIKE 或 Elasticsearch？

<details>
<summary>展开答案</summary>

| 方法 | 匹配方式 | 问题 |
|------|---------|------|
| SQL LIKE | 字符串匹配 | "engineer" ≠ "developer"，找不到同义词 |
| Elasticsearch BM25 | 关键词匹配 | "tech staff" 找不到 "Engineering dept" |
| 向量检索 | 语义相似度 | "研发" 和 "R&D" 向量接近，能互相找到 |

**三者不是替代关系，是互补关系。**

我们的实现用了混合检索（Phase 2）：
```python
# 向量检索：理解语义
vector_results = cosine_search(question_embedding)  # "engineer" 能找到 "developer"

# 关键词检索：精确匹配
keyword_results = bm25_search(question)  # "Error-500" 精确匹配日志中的错误码

# RRF 融合：取两种结果的重叠高分项
final = rrf_fusion(vector_results, keyword_results, weight=0.7)
```

面试金句：**"向量检索管语义，全文检索管精确，两者互补。"**
</details>

---

### Q4: 文档分块（chunking）为什么重要？块太大或太小有什么问题？

<details>
<summary>展开答案</summary>

分块是 RAG 最被低估的环节。块大小直接影响检索质量：

| 块大小 | 问题 |
|--------|------|
| **太小** (100 chars) | 上下文断裂，`"Alice, 30, Engineering"` 没有标题行不知道列含义 |
| **太大** (5000 chars) | 噪音多，检索时匹配到 irrelevant 内容，LLM 上下文窗口浪费 |
| **合适** (500-1000 chars) | 一个块包含一个完整语义单元 |

我们的策略：
```python
class DocumentChunker:
    strategy = "recursive"  # 优先按段落分，其次按句子分
    chunk_size = 1000       # 每块最多 1000 字符
    overlap = 200           # 相邻块之间重叠 200 字符
    
    # 为什么要 overlap？
    # "Alice works in Engineering. She earns 80000."
    # 块 1: "Alice works in Engineering."
    # 块 2: "Engineering. She earns 80000."  ← overlap 保证"Engineering"不丢失
```

面试时可以提的进阶点：**语义分块**（用 LLM 判断自然段落边界）、**父子分块**（小块检索 + 大块回填上下文）。
</details>

---

### Q5: pgvector 索引原理是什么？为什么能这么快？

<details>
<summary>展开答案</summary>

pgvector 的 **IVFFlat 索引**（Inverted File with Flat compression）：

```
Step 1: 预计算阶段（建索引时）
  100 万个向量 → K-means 聚类 → 分成 100 个"列表"（lists）
  每个列表有一个"中心点"（centroid）

Step 2: 查询时
  查询向量 → 只跟 100 个中心点比较距离
  → 找到最近的 1-3 个列表
  → 只扫描这 1-3 个列表中的向量（约 1-3 万条）
  → 而不是全表 100 万条！

加速比: 100万 / 3万 ≈ 33x
```

```sql
-- 建索引
CREATE INDEX ON document_chunks 
  USING ivfflat (embedding vector_cosine_ops) 
  WITH (lists = 100);

-- lists 参数经验值:
-- 数据量 < 10万: lists = 数据量/1000
-- 数据量 > 10万: lists = sqrt(数据量)
```

**HNSW 索引**（更先进，pgvector 也支持）：
- 构建多层图结构，像"高速公路 + 城市道路"
- 查询时从高层快速定位区域 → 低层精确搜索
- 比 IVFFlat 快 5-10x，但构建时间更长、内存占用更大
</details>

---

### Q6: 从上传文件到用户检索到答案，完整链路是什么？

<details>
<summary>展开答案</summary>

```
用户上传 PDF
  │
  ▼
① Parser 解析  (PdfParser/DocxParser/CsvParser...)
  → "Alice, 30, Engineering, 80000\nBob, 25, Marketing..."
  │
  ▼
② Chunker 分块 (DocumentChunker, recursive strategy)
  → [Chunk 0: "Row 1: name: Alice | age: 30 | ...", Chunk 1: "Row 2: ..."]
  │
  ▼
③ Embedder 向量化 (TF-IDF, 384-dim)
  → Chunk 0: [0.045, 0.023, ...] (384 floats)
  → Chunk 1: [0.032, 0.067, ...] (384 floats)
  │
  ▼
④ 存入 PostgreSQL (pgvector)
  → INSERT INTO document_chunks (content, embedding) VALUES (...)
  │
  ▼
⑤ 用户提问: "Who works in Engineering?"
  │
  ▼
⑥ 问题向量化 (相同 Embedder)
  → [0.041, 0.028, ...] (384 floats)
  │
  ▼
⑦ pgvector 余弦搜索 (IVFFlat 索引)
  → SELECT ... ORDER BY embedding <=> question_vector LIMIT 5
  → 返回最相似的 5 个 chunk
  │
  ▼
⑧ 拼接 Context
  → "Row 1: name: Alice | ...\nRow 3: name: Charlie | ..."
  │
  ▼
⑨ 喂给 LLM
  → System: "Based on the following info, answer the question."
  → Context: {chunks}
  → User: "Who works in Engineering?"
  │
  ▼
⑩ LLM 回答
  → "Alice and Charlie work in Engineering. Alice earns 80k, Charlie 95k."
```

优化点：
- 步骤⑦⑧ 之间加 **Rerank**：召回 20 个 chunks → 精排模型打分 → 取 Top-3
- 步骤③ 升级为 **Sentence Transformers** → 语义理解更好
- 步骤④ 可以加 **缓存**：相同问题直接返回，不重复检索
</details>

---

### Q7: 混合检索（Hybrid Search）的原理是什么？

<details>
<summary>展开答案</summary>

混合检索 = 向量检索 + 关键词检索 + RRF 融合。

```python
# 1. 向量检索（语义匹配）
vector_results = pgvector_cosine_search("Who works in Engineering?")
# → 返回: Alice(0.94), Charlie(0.87), Diana(0.43)

# 2. 关键词检索（精确匹配）  
keyword_results = postgresql_fulltext_search("Engineering")
# → 返回: Alice(1.0), Charlie(1.0), # 精确匹配分数高

# 3. RRF (Reciprocal Rank Fusion) 融合
def rrf_fusion(vector_results, keyword_results, k=60):
    scores = {}
    for rank, item in enumerate(vector_results):
        scores[item.id] = 0.7 / (k + rank)   # vector weight = 0.7
    for rank, item in enumerate(keyword_results):
        scores[item.id] += 0.3 / (k + rank)   # keyword weight = 0.3
    return sorted(scores.items(), key=lambda x: -x[1])
# → 最终排序: Alice(高分), Charlie(高分), Diana(低分，只在vector中有)
```

**什么时候混合检索比纯向量好？**
- 搜错误码：`"Error-500"` → 关键词精确匹配比向量语义匹配靠谱
- 搜人名：`"Alice"` → 关键词直接匹配比向量快
- 搜概念：`"如何优化性能"` → 向量语义搜索更好（"加速"、"提升效率"都能匹配）
</details>

---

### Q8: RAG 的常见坑和优化手段有哪些？

<details>
<summary>展开答案</summary>

**坑 1：分块策略太粗糙**
- 问题：固定 1000 字符切分，一句话被切成两半
- 解决：递归分块（优先按段落、句子边界切），重叠窗口

**坑 2：检索的 chunk 和问题不相关**
- 问题：`"公司请假流程"` 检索到了 `"公司年假政策"`，用户要的是流程不是政策
- 解决：混合检索 + Rerank（精排模型纠正初排错误）

**坑 3：LLM 不按文档回答**
- 问题：文档有答案但 LLM 用了自己的知识
- 解决：Prompt 约束 `"If the context doesn't contain the answer, say 'I don't know'"`

**坑 4：Embedding 模型不匹配语言**
- 问题：英文 embedding 模型处理中文文档，检索效果差
- 解决：中文用 `bge-large-zh-v1.5` 或 `text-embedding-3-large`

**坑 5：文件格式处理不完整**
- 问题：PDF 表格、PPTX 图片文字解析不出来
- 解决：多 parser 策略（我们已支持 17 种格式），图片加 OCR

**性能优化清单：**
- [ ] pgvector IVFFlat/HNSW 索引
- [ ] Redis 缓存高频问题
- [ ] 文档预处理（去噪、去重）
- [ ] 分块元数据过滤（先按标签筛选再向量检索）
- [ ] LLM 流式输出（用户不用等完整回答）
</details>

---

### Q9: 你们的 RAG 和生产级 RAG 有什么区别？

<details>
<summary>展开答案</summary>

| 环节 | 我们 (Phase 1) | 生产级 | 差距 |
|------|---------------|--------|------|
| Embedding | TF-IDF (384-dim) | text-embedding-3-large / bge-large | 语义理解弱 |
| 检索 | 纯向量余弦 | 混合检索 + Rerank | 召回精度低 |
| 索引 | 无 | IVFFlat / HNSW | 大数据量慢 |
| 分块 | 递归 + 重叠 | 语义分块 + 父子块 | 上下文完整性 |
| 缓存 | 无 | Redis 语义缓存 | 重复计算 |
| 监控 | 无 | Langfuse / 自建日志 | 质量无法追踪 |
| 多模态 | 纯文本 | 图片/表格 OCR | 富文档支持弱 |

我们 Phase 2 的目标就是填平这些差距。面试时这样讲加分：**"我知道差距在哪，也知道怎么解决，有明确的升级路线。"**
</details>
