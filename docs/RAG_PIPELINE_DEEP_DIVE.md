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

### 3.2 TF-IDF 是怎么算出这些数字的?(我们的实现)

> 这一节假设你**没接触过 TF-IDF**。从"为什么需要它"开始,一直推到我们 `embedder.py` 的代码,最后摆出我们这版实现的**真实缺陷**——这些缺陷不写明白,以后排查检索质量问题会到处碰壁。

#### 3.2.1 先回答:为什么要有 TF-IDF?

把文本变成向量,最朴素的方法叫 **Bag-of-Words(词袋)**:

```
词表: [alice, bob, works, in, engineering, marketing]
Doc A "Alice works in Engineering" → [1, 0, 1, 1, 1, 0]
Doc B "Bob works in Marketing"     → [0, 1, 1, 1, 0, 1]
```

每个维度对应词表里一个词,值是这个词出现的次数。问题来了:

| 朴素词袋的毛病 | 例子 |
|---|---|
| **常见词被高估** | `the / in / works` 几乎每篇都有,但它们对"区分文档"没贡献,却占了向量里很大权重 |
| **罕见词被低估** | `quantum / mitochondria` 只出现一次,但往往就是"这篇文档讲什么"的关键信号 |
| **长文档天然得分高** | 100 个词 vs 10 个词,纯靠词频比,长文档无脑赢 |

**TF-IDF 就是给词袋打的两个补丁**——一个修"罕见词更重要"(IDF),一个修"长文档不该天然占便宜"(TF 归一化)。

#### 3.2.2 TF / IDF / TF-IDF 三个概念分开讲

**TF — Term Frequency(词频)** —— 这个词在**当前这篇文档**里出现了多少次。

```
TF(t, d) = 词 t 在文档 d 里出现的次数 / 文档 d 的总词数
                                       ↑
                              除以总词数 = 长度归一化
                              防止长文档天然占便宜
```

直觉:"这个词在这篇里有多重要"。频次越高 → 这篇文档越可能在讲这个词。

**DF — Document Frequency(文档频率)** —— 这个词出现在了**多少篇不同的文档**里。注意是"篇数"不是"总次数",同一篇出现 100 次只算 1。

```
DF(t) = 包含词 t 的文档数
N = 总文档数
```

**IDF — Inverse Document Frequency(逆文档频率)** —— "这个词有多稀有"的量化:

```
IDF(t) = log(N / DF(t))           ← 教科书公式
       = log(总文档数 / 含 t 的文档数)
```

直觉:稀有 → IDF 大 → 该词更"有信息量"。
- `the` 出现在 100% 的文档里 → `log(N/N) = log(1) = 0` → IDF 为 0,**完全没区分度**
- `quantum` 出现在 1/100 的文档里 → `log(100/1) = 4.6` → 高 IDF,**很能区分**

**TF-IDF** —— 两者相乘:

```
TF-IDF(t, d) = TF(t, d) × IDF(t)
              ↑              ↑
        在这篇里有多频繁   这个词本身有多稀有
```

一句话:**"在这篇里频繁,且在全集里稀有的词" 权重最高**。这就是"该词能定位到这篇文档"的数学表达。

#### 3.2.3 手算一遍(对应代码里的两篇文档例子)

```
文档集合(N = 2):
  Doc A: "Alice works in Engineering"  → 4 个词
  Doc B: "Bob works in Marketing"       → 4 个词

Step 1: 统计 TF(每个词在每篇里的次数,除以文档总词数)
  Doc A: alice=1/4=0.25, works=0.25, in=0.25, engineering=0.25
  Doc B: bob=0.25,       works=0.25, in=0.25, marketing=0.25

Step 2: 统计 DF(每个词出现在几篇文档里)
  alice=1, bob=1, engineering=1, marketing=1, works=2, in=2

Step 3: 计算 IDF (用教科书公式 log(N/DF))
  IDF(alice)       = log(2/1) = 0.693
  IDF(bob)         = log(2/1) = 0.693
  IDF(engineering) = log(2/1) = 0.693
  IDF(marketing)   = log(2/1) = 0.693
  IDF(works)       = log(2/2) = 0      ← 每篇都有 → IDF=0
  IDF(in)          = log(2/2) = 0      ← 同上

Step 4: TF-IDF = TF × IDF
  Doc A: alice=0.173, works=0, in=0, engineering=0.173
  Doc B: bob=0.173,   works=0, in=0, marketing=0.173
```

关键洞察:
- **`works` 和 `in` 的 TF-IDF 都是 0** —— 自动被去权重,等价于内置了"停用词过滤"
- **`alice` 和 `bob` 的 TF-IDF 都是 0.173** —— 这两个词成了"区分两篇文档的指纹"
- 如果再加一篇 Doc C "Alice talks to Bob",alice 和 bob 的 IDF 会从 0.693 降到 log(3/2)=0.405,因为它们不再独占了——**TF-IDF 是动态的,加一篇新文档,所有词的权重都会变**

#### 3.2.4 我们 `embedder.py` 实际做了什么(逐行对照)

```python
async def embed(self, texts: list[str]) -> list[list[float]]:
    # ① 全集统计:每个词的总频次 + 文档频次
    word_counts = Counter()           # 全局总词频(只用于挑词表)
    doc_freqs = Counter()             # 每个词出现在几篇里(用于 IDF)
    for text in texts:
        words = self._tokenize(text)
        word_counts.update(words)
        doc_freqs.update(set(words))  # set() 保证一篇只算一次

    # ② 挑词表 = 按全局频次取 top-N (N = VECTOR_DIMENSION = 384)
    vocab = [w for w, _ in word_counts.most_common(self.dimension)]

    # ③ 给每篇文档算 TF-IDF 向量(维度 = 384)
    N = len(texts)
    idx = {w: i for i, w in enumerate(vocab)}
    vectors = []
    for text in texts:
        words = self._tokenize(text)
        tf = Counter(words)
        vec = [0.0] * self.dimension
        for word, count in tf.items():
            if word in idx:                       # 不在 top-384 直接丢弃
                df = doc_freqs.get(word, 1)
                # 注意这里的公式 ↓
                vec[idx[word]] = (count / max(len(words), 1)) \
                                 * math.log(N / (df + 1) + 1)
        vectors.append(vec)
    return vectors
```

几个跟教科书不一样的工程细节:

| 行为 | 教科书写法 | 我们的写法 | 为什么 |
|---|---|---|---|
| 词表 | 全部词 | 只取 top-384 | 维度必须固定为 384 (跟 pgvector `VECTOR(384)` 列对齐) |
| IDF 公式 | `log(N/DF)` | `log(N/(DF+1) + 1)` | `+1` 平滑:防 DF=0 报错 / 防 N=DF 时 log(1)=0 让该词完全消失 |
| 长度归一化 | `TF = count/total_words` | 同左 | 防长文档天然占便宜 |
| Tokenizer | 一般用 NLTK/spaCy | 正则 `[a-zA-Z0-9]{2,}` | 零依赖;但**只认英文**——见下方缺陷 |

#### 3.2.5 ⚠️ 我们这版实现的真实缺陷(关键)

教科书 TF-IDF 已经有它固有的局限(不懂语义),但**我们这版在工程上还有 6 个具体缺陷**——以后排查"为什么这个查询召不回该有的文档",八成是踩到下面某条:

##### ① 完全不懂中文 ❌(最致命)

```python
return re.findall(r"[a-zA-Z0-9]{2,}", text.lower())
```

`[a-zA-Z0-9]{2,}` 只匹配英文字母和数字。中文字符全部被丢掉:

```python
_tokenize("Alice 在工程部工作")
# → ['alice']     ← 中文全没了!
```

结果:**任何含中文的文档,向量里几乎全是 0**,余弦距离全部接近 1,检索基本随机。这是当前实现最大的雷区,处理任何中文语料前必须改。

> 临时方案:换正则为 `[\w]+` 并加中文分词(jieba);**真正方案**:Phase 2 上 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`。

##### ② 词表只取 top-384,小词全丢 ❌

`vocab = word_counts.most_common(384)` —— 只保留全集里最高频的 384 个词,其他词在向量里**完全不存在**。

这跟 IDF 的设计哲学**直接打架**:IDF 本来要让稀有词权重高,结果这一刀把稀有词整个砍掉了。意味着:
- "quantum"、"mitochondria" 这种 **真正能定位文档的关键词,在小语料里**容易因为出现次数少而不进 top-384,等于看不见
- 词表大小硬绑在 embedding 维度上,改 384 → 改向量列宽度 → 数据库迁移

正常 TF-IDF 实现(如 sklearn `TfidfVectorizer`)的词表可以几万几十万,稀疏向量存储。我们把维度上限当词表上限,是 MVP 期的妥协。

##### ③ embedding 不是"独立计算",它跟批次绑死 ❌

注意 `embed(texts)` 是**对传入的这一批文本统一建词表 + IDF**。同一段话,在不同批次里 embed,**向量值不一样**!

```python
emb1 = await embedder.embed(["Alice works in Engineering"])
emb2 = await embedder.embed(["Alice works in Engineering", "Bob in Marketing"])
emb1[0] != emb2[0]   # ← 同一段话,但两次向量不一样
```

这导致两个严重后果:
- **检索时的 query 向量,和入库时的 chunk 向量不在同一个坐标系**——余弦距离的含义被破坏
- 后续增量入库,新加的文档跟老文档**词表/IDF 都不同**,老向量等于过期

正常做法:**先用整个语料库 fit 一次(算全局 vocab + IDF),保存,以后所有 transform 用同一个 vocab/IDF**。我们当前没做这一步——这是 MVP 阶段尚未暴露的核弹级 bug,数据量一上来就会显现。

##### ④ 完全不懂同义/近义/上下位关系 ❌

```python
"engineer" vs "developer"  → 两个完全不同的维度,余弦距离很远
"NYC"      vs "New York"   → 同上
"猫"        vs "猫咪"        → 同上(还叠加缺陷①)
```

这是教科书 TF-IDF 的固有局限,不是工程 bug——但**用户提问几乎从不用文档里的原词**。"我们公司有谁是搞机器学习的?"这种问题,文档里写的是"AI 工程师",TF-IDF 召不回。

##### ⑤ 完全不懂词序/否定/反义 ❌

```
"Alice loves Bob"      → TF-IDF 向量 V1
"Bob loves Alice"      → TF-IDF 向量 V1 (完全一样!词袋模型)
"Alice doesn't like Bob" → 跟前两句 TF-IDF 几乎一样(只多一个 doesn't)
```

凡是涉及"谁对谁做了什么"、"有没有否定"的检索都会出错。这也是词袋模型族的通病。

##### ⑥ 没做 L2 归一化,余弦距离的语义被弱化 ❌

教科书 TF-IDF 工程实现一般会在最后做一次 **L2 归一化**(`v / ||v||`),让所有向量都在单位球面上。这样:
- 余弦相似度 = 点积(简单一个乘加就出结果,极快)
- 长短文档对距离的影响被进一步消解

我们的实现没做这一步,而是把"长度归一化"放在了 TF 那一步。pgvector 的 `<=>` 是余弦距离,数学上仍然能算,但**长短文档之间的距离会有偏差**。

#### 3.2.6 这些缺陷对你的开发意味着什么?

| 你的场景 | 影响 | 是否需要现在就解决 |
|---|---|---|
| 全英文 RAG demo / 单元测试 | 基本能用 | 不用 |
| 中文语料 | **召回质量接近随机** | **必须先改 tokenizer 或上 Phase 2** |
| 增量入库(新文档持续上传) | 老向量越用越偏 | 必须先解决缺陷③,或定期全量 reindex |
| 用户提问用自然语言(同义词、口语化) | 召回率低 | 拉 Phase 2,叠加混合检索(BM25 + vector) |
| 文档量 > 1 万 | 词表 384 不够用 | 拉 Phase 2,或显式扩大维度 |

#### 3.2.7 Phase 2 升级路径

**最小改动 = 把 `Embedder` 换成 sentence-transformers**:

```python
from sentence_transformers import SentenceTransformer

class Embedder:
    def __init__(self):
        # 384 维,跟现有 pgvector 列对齐,无需迁移
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    async def embed(self, texts):
        return self.model.encode(texts, normalize_embeddings=True).tolist()
```

一行替换,上面 6 条缺陷里 ①②③④⑥ 全部消失,⑤(词序)被大幅缓解(Transformer 看上下文)。代价:
- 第一次启动要下载 ~120 MB 模型
- embedding 速度从"瞬间"变成"每千字几十 ms"
- 内存占用增加约 200 MB

> 留这一节的核心目的:**让任何后来读这段代码的人立刻知道——我们的 TF-IDF 是 MVP 期占位实现,生产前必须替换**,而不是"看起来能跑就拿去上线"。

---


## 四、分块（Chunking）深度解析

### 4.1 为什么要分块？

**根本原因：Embedding 模型有输入长度限制。**

拿 all-MiniLM-L6-v2 举例——最大输入 256 个 token。一本 10 万字的小说直接塞进去？模型直接报错。必须切成小块。

**但即使模型支持无限长度（比如 text-embedding-3 支持 8192 token），也必须分块。原因：**

```
不分块（整本书一个向量）:
  "The moon colony..." + "量子力学原理..." + "食谱：红烧肉做法..."
  → 一个 384 维向量试图概括所有内容
  → 检索 "月球基地什么时候建立的？" 
  → 向量匹配：0.55（不高不低，因为向量里混了太多无关信息）
  → 拿整本书喂给 LLM → Token 超限

分块后（每段一个向量）:
  块 1: "Commander Elena stared at Luna-7..."       → 向量 A（科幻/月球相关）
  块 2: "The clockmaker fixed the silver watch..."   → 向量 B（温情/手工相关）
  块 3: "Dr. Tanaka's underwater farm..."            → 向量 C（科技/环保相关）
  
  检索 "月球基地" → 和向量 A 距离 0.02（极近！）→ 只返回块 1 → 精准
```

**分块 = 把一本书的"模糊印象"变成每一段的"精准定位"。**

### 4.2 分块策略对比

我们的实现支持两种策略：

**策略 A：固定大小分块（fixed_size）**
```python
chunk_size = 500   # 每 500 字符一刀
overlap = 100      # 相邻块重叠 100 字符

原文: "ABCDEFGHIJKLMNOPQRSTUVWXYZ" (26 chars)
块 1: "ABCDEFGHIJ"       (chars 0-10)
块 2:      "HIJKLMNOPQR" (chars 7-17, overlap 3)
块 3:            "OPQRSTUVWXYZ" (chars 14-26)

优点: 简单、快
缺点: 可能在句子中间切断 → "Alice works in" 和 "Engineering" 被分到两个块
```

**策略 B：递归分块（recursive）—— 我们的默认策略**
```python
# 分离器优先级: 段落 > 行 > 句子 > 字符
separators = ["\n\n", "\n", ". ", "! ", "? ", ".", "!", "?", " "]

原文:
"Alice works in Engineering.\n\nBob works in Marketing."

Step 1: 尝试用 "\n\n" 切分
  → ["Alice works in Engineering.", "Bob works in Marketing."]
  → 每段都 < chunk_size(1000) → 完美！不继续切

原文:
"Alice works in Engineering. Bob works in Marketing. Charlie works in Design." (太长了)

Step 2: "\n\n" 切不了（没有空行）→ 尝试 "\n" → 也没有 → 尝试 ". "
  → ["Alice works in Engineering", "Bob works in Marketing", "Charlie works in Design"]
  → 每段 < chunk_size → 完成

优点: 在自然边界切分，保持语义完整
缺点: 如果一段特别长（没有标点的纯文本），最终会退化到字符级切分
```

### 4.3 块大小如何确定？

**核心公式：chunk_size = f(模型限制, 检索精度, 上下文完整度)**

| 因素 | 影响 |
|------|------|
| **Embedding 模型 limit** | 硬上限。MiniLM=256 token, text-embedding-3=8192 token |
| **检索精度** | 小块 → 向量更"纯粹" → 匹配更精准 |
| **上下文完整度** | 大块 → 包含更多上下文 → LLM 理解更好 |
| **硬件/速度** | 几乎无关。384 维向量 100 字和 1000 字的计算量一样 |

**经验值（不是从硬件算出来的）：**

| 应用场景 | 推荐 chunk_size | 原因 |
|---------|----------------|------|
| FAQ / 问答对 | 200-500 | 每个 Q&A 就是一个自然块 |
| 技术文档 | 500-1000 | 一个段落讲一个概念 |
| 长篇文章 | 1000-2000 | 需要更多上下文 |
| 代码库 | 按函数/类 | 不应按字符数切分 |
| 对话记录 | 按轮次 | 一问一答是一个单元 |

**我们为什么选 1000 chars + 200 overlap？**
- 1000 字符 ≈ 250 个英文单词 ≈ 150-200 个中文词
- MiniLM 限制约 256 token，1000 chars 基本在安全范围内
- 200 overlap 保证相邻块的边界词不丢失
- 这是 **经验值**，不是计算出来的。可以通过评估检索准确率来调整

### 4.4 如何评估分块是否合理？

**方法：对比实验**
```python
# 测试不同的 chunk_size
for size in [300, 500, 800, 1000, 1500]:
    chunker = DocumentChunker(chunk_size=size)
    # 用同一个测试集跑检索
    accuracy = evaluate_retrieval(chunker, test_questions, ground_truth)
    print(f"chunk_size={size}: accuracy={accuracy}")
```

**好的分块 = 每个块包含一个完整语义单元**
```
✅ 好: "Alice works in Engineering. She earns 80000 per year."
❌ 差: "Alice works in" (句子被切断)
❌ 差: "Alice works in Engineering. She earns 80000 per year. 
        Bob works in Marketing. Charlie works in Design..." (太多无关信息)
```

### 4.5 分块策略全景(从笨到聪明)

RAG 检索质量的天花板,很大程度上由"切得好不好"决定——分块决定了**单次召回里塞了多少有用信息、多少噪声、上下文有没有被切断**。主流策略大致 7 类:

| # | 策略 | 做法 | 优点 | 缺点 | 何时选 |
|---|---|---|---|---|---|
| 1 | **Fixed-size** | 每 N char/token 切一刀,可加 overlap | 实现 10 行;最快;长度可控 | 无视语义,经常拦腰斩断句子/表格/代码 | 语料同质(纯日志)、性能优先、原型阶段 |
| 2 | **Recursive character** | 按分隔符**按优先级递归**切——先段落,不够再行→句→词 | 长度可控 + 尊重语义;零模型成本;通用 | 分隔符是启发式;跨语种/Markdown/代码需调 | **业界事实标准 baseline**——LangChain 默认就是这套 |
| 3 | **Sentence split** | NLTK / spaCy / 正则断句,再凑包到 chunk_size | 句子完整,语义最小单元保留 | 依赖断句库;中文/混语种翻车;凑包逻辑要自己写 | 文本是规范散文,且能接受额外依赖 |
| 4 | **Markdown / Code-aware** | 按 `#` 标题层级 / 函数定义 / 代码块切 | 保留原文结构,chunk 可带"标题路径"metadata | 格式特化,纯文本失效 | 文档库是技术文档、API 文档、代码仓库时几乎必选 |
| 5 | **Token-aware** | 用 embedding 模型的 tokenizer 算长度 | 严格匹配模型上限,不被截断 | 慢一截;实现复杂 | embedding 模型上下文小(如 512 token)、或严格按 token 计费 |
| 6 | **Semantic split** | 相邻句子做 embedding,**相似度突降处切**(LlamaIndex `SemanticSplitterNodeParser`) | 边界对齐"话题转折",chunk 内主题最集中 | 贵 + 慢;阈值难调 | 长文/论文/小说;检索质量比建索引成本更重要 |
| 7 | **LLM-based / Agentic** | 让 LLM 读全文输出边界 / 主题摘要 + 原文片段 | 上限最高;可让每个 chunk 自带摘要 | 成本爆炸;不可重现;不可规模化 | 少量高价值文档、离线一次性建库 |

#### 进阶组合(实际项目里常用)

- **Parent-document retrieval** —— 小 chunk 用于检索,命中后返回**所在的大 parent chunk** 给 LLM(检索精度 + 上下文完整度双赢)
- **Hierarchical chunking** —— 同一文档切 2-3 个粒度(段/页/章),按需召回
- **Window-based context expansion** —— 命中 chunk i,补 i-1 / i+1 给 LLM
- **Late chunking** (2024 新思路) —— 先对全文做 embedding,再按位置切,避免句子级 embedding 丢上下文

#### 我们的选择路径

```
fixed_size  ──→  recursive  ──→  (Phase 2) semantic  ──→  parent-doc / hierarchical
   ↑                ↑                    ↑                          ↑
 兜底实现        默认策略             代码已留接口             未来扩展方向
```

`chunker.py` 同时实现了 1 和 2:`_fixed_size_split` 作为兜底(纯文本无任何分隔符时会回落到它),`_recursive_split` 是默认 strategy。Phase 2 再上 semantic。

### 4.6 为什么我们的 separators 长这样

```python
separators = ["\n\n", "\n", ". ", "! ", "? ", ".", "!", "?", " "]
```

这是**递归切分**策略的核心配置——9 个分隔符**按从粗到细的优先级**排列。`_recursive_chunk` 的逻辑是:**用第一个分隔符切,如果切出来的某一块仍 > chunk_size,对那一块用第二个分隔符再切**,以此递归;最坏情况落回 `_fixed_size_split` 硬切。

#### 排列顺序背后的"语言层级"假设

| 层级 | 分隔符 | 语言单位 | 切到这一层意味着 |
|---|---|---|---|
| 1 | `\n\n` | **段落** | 最理想——一段话讲一件事 |
| 2 | `\n` | **行** | 段落太长时退到行(列表项、单行 heading) |
| 3 | `. ` `! ` `? ` | **英文句子**(标点 + 空格) | 行还是太长,退到句子级 |
| 4 | `.` `!` `?` | **无空格标点** | 兜底:句末没跟空格(常见于中文/紧凑英文) |
| 5 | ` ` | **单词** | 最后退路,词边界——总比把单词砍断好 |

#### 4 条关键设计权衡

##### ① 优先保留语义单元的完整性

最重要的设计目标:**chunk 内是一段完整意思,不是半句话**。原因:

- **embedding 质量** —— 向量表征的是"一段话的语义",半句话的向量是有偏的
- **检索后的 LLM 可读性** —— LLM 拿到半句话很难推理
- **引用准确性** —— `Chunk.source / page` 这些 metadata 才能精准定位

段落 (`\n\n`) 几乎一定是完整意思,所以排第一。

##### ② 标点 + 空格优先于裸标点(反误切小心机)

`". "` 排在 `"."` 之前——这是为了**防止把 `e.g.` / `3.14` / `Mr.` 这种缩写和小数点切碎**:

- `". "`(句号+空格)几乎只出现在真正的句末,误切率低
- 只有当 `". "` 都切不动(整段没有规范断句),才退到裸标点容忍误切

这一手在英文文档里特别有用。中文因为习惯不同(用 `。` 且不跟空格),效果会弱一些——所以**这套 separators 偏向英文优化**,处理纯中文语料应该加入 `。 / ! / ? / ;`(见 §4.7 调整指南)。

##### ③ 兜底到空格而非字符

最后一档是 `" "`(空格)而不是字符级。原因:

- **不会撕裂单词** —— `"transformer"` 切成 `"transfor"` + `"mer"` 在 embedding 空间几乎是噪声
- **空格切完仍是"词序列"**,语义还在
- 真到了连空格都没有(长 token / 中文长段)才走 `_fixed_size_split` 硬切

##### ④ 递归 + 贪心合并,而非"切完就用"

`_recursive_chunk` 里有个关键模式:**切完小片之后,再贪心地把小片往回拼,凑到接近 chunk_size 才发出去**:

```python
for part in splits:
    candidate = (current + sep + part).strip() if current else part
    if len(candidate) <= self.chunk_size:
        current = candidate              # 继续攒
    else:
        chunks.append(Chunk(content=current, ...))   # 放出来
        current = part                   # 开新桶
```

为什么要这样:

- **避免 chunk 过小** —— 按 `\n\n` 切完可能每段就 50 字,直接当 chunk 浪费 embedding 算力,且检索时上下文太碎
- **逼近 chunk_size 上限** —— 单 chunk 信息密度最大化,提升检索命中后的 LLM 推理质量
- **但绝不超 chunk_size** —— 保证不超 embedding 模型上下文

这个"先切碎再合并"的设计,正是 LangChain `RecursiveCharacterTextSplitter` 的标志性思想——也是这套 separators 能 work 的前提。

#### 为什么不选别的策略

| 备选 | 为什么没选 |
|---|---|
| **fixed_size** | 太粗暴,经常切坏。保留它做兜底,但默认不用 |
| **sentence(spaCy)** | 引入重依赖;中文断句效果一般;`. ! ?` 三个分隔符已经覆盖大部分场景 |
| **markdown-aware** | 当前 RAG 语料未必都是 Markdown;通用 recursive 已能处理段落 |
| **token-based** | embedding 模型上下文够大,按 char 撑得住;少一层 tokenizer 调用更快 |
| **semantic** | 注释里已标 Phase 2——离线建库时模型成本可接受,但 MVP 阶段先用 recursive |
| **LLM-based** | 成本和延迟无法接受 |

### 4.7 什么时候要调整这套 separators

| 场景 | 调整方向 |
|---|---|
| **语料以中文为主** | 加入中文标点:`["\n\n", "\n", "。 ", "! ", "? ", "。", "!", "?", " "]`;甚至换成 `["\n\n", "\n", "。", "!", "?", ";", "、", " "]` |
| **处理 Markdown 文档** | 把 `["\n# ", "\n## ", "\n### ", "\n\n", ...]` 放最前,先按标题切;chunk 还能挂"标题路径"做 metadata |
| **处理代码** | 换 `["\nclass ", "\ndef ", "\n\n", "\n", " "]` 这种代码感知的;或直接换 `PythonCodeTextSplitter` |
| **chunk_size 显著变小(< 200)** | 段落往往大于 chunk_size,`\n\n` 几乎触发不了——要把 `\n` 提到更前;或考虑是否真的需要这么小的块 |
| **想引入 token 精确控制** | 把 `len(text)` 换成 `len(tokenizer.encode(text))`,其余逻辑不变 |
| **检索质量瓶颈在"主题切断"** | 升级到 semantic split,或加 parent-document retrieval |
| **检索质量瓶颈在"上下文不全"** | 不改分块,加 window expansion(命中 i,补 i±1) |

### 4.8 一句话总结(可背)

> 这套 `separators` 的意图就一条:**在不引入模型成本的前提下,按"段落 → 句子 → 词"的语言层级递降切分,配合"贪心合并到 chunk_size 上限"的策略,在 chunk 大小可控和语义完整性之间取得最佳折中**。它是 RAG 领域的事实标准 baseline,适合 MVP 阶段;后续升级优先方向是 **markdown-aware**(如果文档结构强)或 **semantic split**(如果检索质量到了瓶颈)。

---

## 五、向量是如何存储的？

### 5.1 数据库表结构

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

### 5.2 实际存储的数据

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

## 六、检索时如何匹配？

### 6.1 余弦相似度

两个向量的夹角越小 → 方向越一致 → 语义越相似。

```
余弦相似度 = (A · B) / (|A| × |B|)

A = [0.8, 0.1, 0.9]     问题 "who works in Engineering?"
B = [0.7, 0.15, 0.85]   文本 "Alice, Engineering, 80000"
C = [0.1, 0.8, 0.05]    文本 "2 + 2 = 4"

A · B = 0.8×0.7 + 0.1×0.15 + 0.9×0.85 = 1.34  ← 点积大 = 夹角小 = 相似
A · C = 0.8×0.1 + 0.1×0.8 + 0.9×0.05 = 0.21  ← 点积小 = 夹角大 = 不相似
```

### 6.2 pgvector 的 `<=>` 运算符

```sql
-- pgvector 内置的余弦距离运算符
-- 返回值 0 = 完全相同（夹角 0°），1 = 完全不同（夹角 90°）
SELECT LEFT(content, 60) AS content,
       ROUND((embedding <=> question_vector)::numeric, 4) AS distance
FROM document_chunks
ORDER BY embedding <=> question_vector  -- 按距离升序
LIMIT 5;
```

### 6.3 为什么极快？

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

## 七、完整检索 SQL 示例

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

## 八、关键代码路径

| 步骤 | 文件 | 类/方法 |
|------|------|---------|
| 解析 | `parsers/csv_parser.py` | `CsvParser.parse()` |
| 分块 | `chunker.py` | `DocumentChunker.split()` |
| 向量化 | `embedder.py` | `Embedder.embed()` |
| 存储 | `pipeline.py` | `RAGPipeline.ingest_file()` |
| 检索 | `retriever.py` | `HybridRetriever.search()` |
| 查询 | `pipeline.py` | `RAGPipeline.query()` |

---

## 九、Phase 2 升级路线

| 环节 | Phase 1 (当前) | Phase 2 |
|------|---------------|---------|
| Embedding | TF-IDF 384-dim（词频统计） | all-MiniLM-L6-v2（语义理解） |
| 检索 | 纯向量余弦搜索 | 混合检索：向量 + BM25 + RRF 融合 |
| 索引 | 无（数据少） | IVFFlat / HNSW 索引 |
| 分块 | 固定大小 + 递归 | 语义分块 + 重叠窗口 |
| 召回 | Top-K | Rerank（召回 20 → 精排 Top-5） |

---

## 十、面试题汇总

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

> 详见 [第四节：分块深度解析](#四分块chunking深度解析)

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
