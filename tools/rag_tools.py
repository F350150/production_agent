import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 由于 ChromaDB 包很大且在精简系统上可能未安装，做容灾回退处理
try:
    import chromadb
    import chromadb.utils.embedding_functions as embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

class RAGTools:
    """
    检索增强生成工具 (RAG Vector Database Tools)
    
    【设计意图】
    长期记忆中枢。尽管 AST 给出了签名图，但这依然不足以寻找潜藏在底层模块里的特定逻辑片段。
    RAG 将代码通过分块（Chunking）并送入模型提取嵌入向量（Embedding Dense Array），
    由此允许 Agent 使用人类自然语言（例如：“这里在哪里验证了用户登录？”）执行强大的语义搜索。
    """
    _chroma_client = None
    _collection = None
    
    @classmethod
    def _init_db(cls, workdir: Path):
        if not CHROMA_AVAILABLE:
            return False
            
        # 设置持久化缓存避免每次都重算浪费资源
        persist_dir = str(workdir / ".team" / "chroma_db")
        os.makedirs(persist_dir, exist_ok=True)
        
        if cls._chroma_client is None:
            # 为了免除对 OpenAI key 的依赖，利用本地开源计算模型默认跑 Sentence-Transformers 
            # 它是无服务器化（Severless/Local）的
            cls._chroma_client = chromadb.PersistentClient(path=persist_dir)
            emb_fn = embedding_functions.DefaultEmbeddingFunction()
            cls._collection = cls._chroma_client.get_or_create_collection(
                name="codebase_index", 
                embedding_function=emb_fn
            )
        return True

    @classmethod
    def index_codebase(cls, path: str, workdir: Path) -> str:
        """
        全量扫描指定路径，建立密集向量索引数据库。
        这可能需要花费几分钟，但这是 RAG 的必经前置步骤。
        """
        logger.info(f"Tool index_codebase: {path}")
        if not cls._init_db(workdir):
            return "Error: ChromaDB not installed. Run: pip install chromadb sentence-transformers"
            
        target_dir = workdir / path
        if not target_dir.is_dir():
            return f"Error: {path} is not a directory."
            
        documents = []
        metadatas = []
        ids = []
        
        for idx, f in enumerate(target_dir.rglob("*.*")):
            if f.suffix not in [".py", ".cpp", ".h", ".js", ".ts", ".md"]:
                continue
            if ".venv" in str(f) or "node_modules" in str(f) or ".team" in str(f):
                continue
                
            try:
                content = f.read_text(encoding="utf-8")
                
                # 提取关系上下文 (Enhanced Graph RAG)
                from .ast_tools import ASTTools
                rel_context = ASTTools.get_relational_context(content) if f.suffix == ".py" else ""

                # 简单分块：按每 100 行代码进行粗切分 (Chunking)
                lines = content.split('\n')
                chunk_size = 100
                for i in range(0, len(lines), chunk_size):
                    chunk_text = "\n".join(lines[i:i+chunk_size])
                    if len(chunk_text.strip()) < 10:
                        continue
                    
                    # 组合增强版文档内容
                    enriched_doc = f"{rel_context}File: {f.relative_to(workdir)}\n{chunk_text}"
                    
                    chunk_id = f"{f.relative_to(workdir)}_{i}"
                    documents.append(enriched_doc)
                    metadatas.append({"file": str(f.relative_to(workdir)), "start_line": i})
                    ids.append(chunk_id)
            except Exception as e:
                logger.error(f"Failed to read {f}: {e}")
                
        if not documents:
            return "No processable files found to index."
            
        batch_size = 100
        total_chunks = len(documents)
        try:
            # 分批 upsert 以免撑死内存
            for i in range(0, total_chunks, batch_size):
                cls._collection.upsert(
                    documents=documents[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size],
                    ids=ids[i:i+batch_size]
                )
            return f"Successfully indexed {total_chunks} chunks from `{path}` into VectorDB."
        except Exception as e:
            logger.error(f"Failed to index: {e}")
            return f"Failed to index VectorDB: {e}"

    @classmethod
    def semantic_search_code(cls, query: str, n_results: int = 5, workdir: Path = None) -> str:
        """利用自然语言通过向量距离匹配相关代码片段"""
        logger.info(f"Tool semantic_search_code: '{query}'")
        if not cls._init_db(workdir):
            return "Error: ChromaDB not installed. Run: pip install chromadb sentence-transformers"
            
        try:
            results = cls._collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            if not results["documents"][0]:
                return "No semantic matches found in VectorDB. Have you run `index_codebase`?"
                
            out = [f"Semantic Search Results for: '{query}'\n"]
            for i in range(len(results["documents"][0])):
                doc = results["documents"][0][i]
                meta = results["metadatas"][0][i]
                dist = results["distances"][0][i] if "distances" in results and results["distances"] else 0
                
                out.append(f"--- File: {meta['file']} (Line {meta['start_line']}) Distance: {dist:.4f} ---")
                out.append(doc)
                out.append("\n")
                
            # Token Limit 防护卡扣
            return "\n".join(out)[:50000]
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return f"Semantic search failed: {e}"
