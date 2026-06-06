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
