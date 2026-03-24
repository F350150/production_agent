# Retrieval-Augmented Generation (RAG) 进阶架构指南

## 1. 为什么大语言模型依然需要 RAG？
不论微调 (Fine-tuning) 和 Pre-training（预训练）如何强大，知识的时效性、极高频的更新以及企业私有数据的绝对保密性，注定了**外挂知识库 (RAG)** 才是解决幻觉并提供确切引用的最终架构基石。
- 微调就像是教给学生数学定理，他以后随时可以回忆出来。
- RAG 就像是在考试时允许学生随时翻开一本最新的开源课本 (Open-book Exam)。

## 2. 核心架构与挑战：这不是简单的相似度搜索
很多人以为 RAG ＝ 调用一个库去把 PDF 切断、存进 ChromaDB 就能完美运行。但生产环境的 RAG 是一个极端复杂的管道(Pipeline)。

### 2.1 数据摄取 (Ingestion) 与高级切片 (Advanced Chunking)
- **固定长度切片 (Fixed-size Chunking)**：极蠢且破坏语义，经常把一句话切断一半导致搜索无果。
- **递归拆分 (Recursive Character Text Splitter)**：以特殊界定符如 Paragraph `\n\n` -> Sentence `\n` -> Word 逐层尝试。
- **AST / 语法树级切片 (Semantic Parsing)**：专供于代码结构，使得每个代码函数的开头结尾甚至对应的类注释不丢失。这是当前大厂内核心业务代码搜索的首选。
- **Parent-Child Chunking**: 在切块中，让 Child 只保留几句话用来精准被向量索引搜索打分，但一旦命中，其实际返回给 LLM 的是它背后引用的那个包含全文的巨大 Parent Chunk，以此保证“检索颗粒度极细，且喂给模型的上下文极其完整”。

### 2.2 检索增强：混合搜索机制 (Hybrid Search)
单纯的密集向量库 (Dense Embedding，例如 OpenAI/BGE) 在面对大量同质化的“编号、专有名词、API 签名”时会陷入迷茫，它们擅长找“意思相近的句子”，不擅长找“极其特定的缩写或ID”。
- **BM25 / 词频逆文本频率倒排搜索**：传统的 Elasticsearch 所使用的技术，天然对专属短词有着无与伦比的“关键词硬匹配”能力。
- **融合排序层 (Cross-Encoder Reranking)**：引入 Cohere Rerank 或 BGE-Reranker 模型，将 BM25 结果混杂 Vector 结果一并塞进去让交叉注意力模型给每一对文本重新计算相关性打分并重新降序排列。

## 3. RAG 前沿范式创新 (Gen & Query Transformations)
### 3.1 提问重写 (Query Rewriting / HyDE)
当用户的输入是“帮我查一下那个什么认证”，如果你拿这句话直接去搜向量，极度低效。
真正的企业级 RAG 首先会做一轮 LLM 转换，叫做 Hypothetical Document Embeddings (HyDE)。即让模型针对这半句话“瞎编一段答案”，然后再把这段“看起来很专业的瞎编答案”做成 Embedding 丢进数据库查。往往召回率会暴增。

### 3.2 自我反思检索 (Self-RAG) 与 FLARE
由业界主流论文提出：模型不再是在最开始一次性去所有文档搜答案。
它会边生成边在背后打出特殊标记 `<retrieve>`，觉得没依据了，再返回知识库补充一段上下文，再接下茬说下去。这是 Agent 与传统 RAG 的重度融合产物。

## 4. RAG 的工业评测：RAGAS
- **忠实度 (Faithfulness)**: 生成的答案有完全脱离由于文摘导致的外溢幻觉吗？
- **答案相关度 (Answer Relevance)**: 废话多不多。
- **上下文精确度 (Context Precision / Recall)**: 捞出来的块里面有多少是没用的垃圾文本？这就是检索质量。

## 5. 挑战任务与进阶路线图
- **阶段 1：多路召回引擎搭建**。在现有的代码库外，编写一个只针对 `Markdown` 和 `JSON` 等半结构化文件的纯 Python 检索器。结合 `ChromaDB` (向量) 与库 `rank_bm25`，实现最基础的双路召回 + 取并集与重排(RRF 算法)。
- **阶段 2：AST 代码树提取实验**。借助 `Tree-sitter` (众多代码编辑器如 nvim 所依赖的底层增量解析库)，直接将开源仓库按类定义和函数体切割出几万个准确的、未损坏的 Python Nodes，作为你私人 Agent 的代码助手挂载上去。
- **阶段 3：Graph RAG 构建**。理解微软推出的 Graph RAG 技术。它不仅仅是对独立切块进行 Embedding，而是利用 LLM 先把切出来的内容提取成节点 `(Entity)` (譬如：CEO, 某API, 某部门) 并在它们图谱之中形成边 `(Relationship)` 后，再在复杂推理下针对性回答“全局拓扑依赖”。
