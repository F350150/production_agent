import ast
import logging
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

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
    长期记忆中枢，支持语义搜索和混合检索。

    增强功能：
    1. 语义分块（AST-based）：按函数/类边界切分，保留语义完整性
    2. 混合检索：向量相似度 + BM25 关键词融合
    3. 重排序：融合多来源结果，提高召回率
    """
    _chroma_client = None
    _collection = None
    _bm25_index: dict = {}

    @classmethod
    def _init_db(cls, workdir: Path):
        if not CHROMA_AVAILABLE:
            return False

        persist_dir = str(workdir / ".team" / "chroma_db")
        os.makedirs(persist_dir, exist_ok=True)

        if cls._chroma_client is None:
            cls._chroma_client = chromadb.PersistentClient(path=persist_dir)
            emb_fn = embedding_functions.DefaultEmbeddingFunction()
            cls._collection = cls._chroma_client.get_or_create_collection(
                name="codebase_index",
                embedding_function=emb_fn
            )
        return True

    @classmethod
    def _semantic_chunk(cls, content: str, file_path: Path, workdir: Path) -> list[dict]:
        """
        基于 AST 的语义分块：按函数/类边界切分，保留完整上下文。
        """
        chunks = []
        lines = content.split('\n')
        total_lines = len(lines)

        if file_path.suffix != ".py":
            return cls._line_chunk(content, file_path, workdir)

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return cls._line_chunk(content, file_path, workdir)

        from .ast_tools import ASTTools
        rel_context = ASTTools.get_relational_context(content)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_line = node.lineno
                end_line = node.end_lineno or start_line

                chunk_lines = content.split('\n')[start_line - 1:end_line]
                chunk_text = '\n'.join(chunk_lines)
                chunk_text = chunk_text.strip()

                if len(chunk_text) < 20:
                    continue

                entity_type = type(node).__name__
                entity_name = node.name

                enriched_doc = (
                    f"[{entity_type}] {entity_name}\n"
                    f"File: {file_path.relative_to(workdir)}\n"
                    f"{rel_context}\n"
                    f"{chunk_text}"
                )

                chunks.append({
                    'text': enriched_doc,
                    'metadata': {
                        'file': str(file_path.relative_to(workdir)),
                        'start_line': start_line,
                        'end_line': end_line,
                        'entity_type': entity_type,
                        'entity_name': entity_name,
                        'chunk_type': 'semantic'
                    }
                })

        if not chunks:
            return cls._line_chunk(content, file_path, workdir)

        return chunks

    @classmethod
    def _line_chunk(cls, content: str, file_path: Path, workdir: Path, chunk_size: int = 100) -> list[dict]:
        """
        传统行数分块：作为语义分块的兜底方案。
        """
        chunks = []
        lines = content.split('\n')
        total_lines = len(lines)

        for i in range(0, total_lines, chunk_size):
            chunk_text = '\n'.join(lines[i:i + chunk_size])
            if len(chunk_text.strip()) < 10:
                continue

            chunks.append({
                'text': f"File: {file_path.relative_to(workdir)}\n{chunk_text}",
                'metadata': {
                    'file': str(file_path.relative_to(workdir)),
                    'start_line': i,
                    'end_line': min(i + chunk_size, total_lines),
                    'chunk_type': 'line'
                }
            })

        return chunks

    @classmethod
    def _build_bm25_index(cls, documents: list[dict]) -> dict:
        """
        构建 BM25 倒排索引，用于关键词检索。
        """
        index = {}
        doc_lengths = []
        avg_doc_length = 0

        for doc in documents:
            text = doc['text'].lower()
            tokens = cls._tokenize(text)
            doc_length = len(tokens)
            doc_lengths.append(doc_length)

            for token in set(tokens):
                if token not in index:
                    index[token] = {'doc_freq': 0, 'postings': []}
                index[token]['doc_freq'] += 1
                index[token]['postings'].append({'doc_id': len(doc_lengths) - 1, 'tf': tokens.count(token)})

        if doc_lengths:
            avg_doc_length = sum(doc_lengths) / len(doc_lengths)

        return {
            'index': index,
            'doc_lengths': doc_lengths,
            'avg_doc_length': avg_doc_length,
            'num_docs': len(documents),
            'k1': 1.5,
            'b': 0.75
        }

    @classmethod
    def _tokenize(cls, text: str) -> list[str]:
        """
        简单分词：提取字母数字序列作为词项。
        """
        tokens = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text.lower())
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                      'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
                      'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                      'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this',
                      'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'}
        return [t for t in tokens if t not in stop_words and len(t) > 2]

    @classmethod
    def _bm25_score(cls, bm25_data: dict, query_tokens: list[str], doc_id: int) -> float:
        """
        计算单个文档的 BM25 分数。
        """
        score = 0.0
        index = bm25_data['index']
        doc_length = bm25_data['doc_lengths'][doc_id]
        avg_dl = bm25_data['avg_doc_length']
        k1 = bm25_data['k1']
        b = bm25_data['b']
        N = bm25_data['num_docs']

        for token in query_tokens:
            if token in index:
                df = index[token]['doc_freq']
                idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
                tf = 0
                for posting in index[token]['postings']:
                    if posting['doc_id'] == doc_id:
                        tf = posting['tf']
                        break
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * doc_length / avg_dl)
                score += idf * numerator / denominator

        return score

    @classmethod
    def _hybrid_search(cls, query: str, top_k: int = 20) -> list[tuple]:
        """
        混合检索：融合向量相似度和 BM25 关键词分数。
        """
        if cls._collection is None:
            return []

        try:
            vector_results = cls._collection.query(
                query_texts=[query],
                n_results=top_k * 2
            )
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            vector_results = {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        query_tokens = cls._tokenize(query.lower())
        if not query_tokens:
            return []

        vector_scores = []
        if vector_results["documents"] and vector_results["documents"][0]:
            for i, doc in enumerate(vector_results["documents"][0]):
                distance = vector_results["distances"][0][i] if i < len(vector_results["distances"][0]) else 1.0
                vector_sim = 1.0 - distance
                vector_scores.append((i, vector_sim, doc, vector_results["metadatas"][0][i]))

        bm25_scores = []
        if cls._bm25_index and 'index' in cls._bm25_index:
            for doc_id in range(len(cls._bm25_index['doc_lengths'])):
                bm25 = cls._bm25_score(cls._bm25_index, query_tokens, doc_id)
                if bm25 > 0:
                    bm25_scores.append((doc_id, bm25))

        bm25_scores.sort(key=lambda x: x[1], reverse=True)
        top_bm25 = bm25_scores[:top_k * 2]

        max_vector = max((vs[1] for vs in vector_scores), default=1.0)
        max_bm25 = max((bs[1] for bs in top_bm25), default=1.0)

        fused_scores = {}

        for rank, (doc_idx, sim, doc, meta) in enumerate(vector_scores):
            vector_weight = 0.6
            normalized_sim = sim / max_vector if max_vector > 0 else 0
            fused_scores[doc_idx] = fused_scores.get(doc_idx, 0) + vector_weight * normalized_sim * (1.0 / (rank + 1))

        for rank, (doc_id, bm25) in enumerate(top_bm25):
            bm25_weight = 0.4
            normalized_bm25 = bm25 / max_bm25 if max_bm25 > 0 else 0
            fused_scores[doc_id] = fused_scores.get(doc_id, 0) + bm25_weight * normalized_bm25 * (1.0 / (rank + 1))

        sorted_fused = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        seen_docs = set()
        for doc_idx, score in sorted_fused[:top_k]:
            if doc_idx < len(vector_scores):
                _, _, doc, meta = vector_scores[doc_idx]
                if doc not in seen_docs:
                    results.append((doc, meta, score))
                    seen_docs.add(doc)

        return results

    @classmethod
    def index_codebase(cls, path: str, workdir: Path, chunk_mode: str = "semantic") -> str:
        """
        全量扫描指定路径，建立密集向量索引数据库。

        Args:
            path: 要索引的目录路径
            workdir: 工作目录
            chunk_mode: 分块模式 ("semantic" | "line")
        """
        logger.info(f"Tool index_codebase: {path} (mode={chunk_mode})")
        if not cls._init_db(workdir):
            return "Error: ChromaDB not installed. Run: pip install chromadb sentence-transformers"

        target_dir = workdir / path
        if not target_dir.is_dir():
            return f"Error: {path} is not a directory."

        cls._bm25_index = {}
        documents = []
        metadatas = []
        ids = []

        for f in target_dir.rglob("*.*"):
            if f.suffix not in [".py", ".cpp", ".h", ".js", ".ts", ".md"]:
                continue
            if ".venv" in str(f) or "node_modules" in str(f) or ".team" in str(f):
                continue

            try:
                content = f.read_text(encoding="utf-8")
                rel_path = f.relative_to(workdir)

                if chunk_mode == "semantic":
                    chunks = cls._semantic_chunk(content, f, workdir)
                else:
                    chunks = cls._line_chunk(content, f, workdir)

                for chunk in chunks:
                    chunk_id = f"{rel_path}_{chunk['metadata']['start_line']}"
                    documents.append(chunk['text'])
                    metadatas.append(chunk['metadata'])
                    ids.append(chunk_id)

            except Exception as e:
                logger.error(f"Failed to process {f}: {e}")

        if not documents:
            return "No processable files found to index."

        if cls._collection:
            try:
                cls._collection.delete(where={})
            except Exception:
                pass

        batch_size = 100
        total_chunks = len(documents)
        try:
            for i in range(0, total_chunks, batch_size):
                if cls._collection:
                    cls._collection.upsert(
                        documents=documents[i:i + batch_size],
                        metadatas=metadatas[i:i + batch_size],
                        ids=ids[i:i + batch_size]
                    )

            cls._bm25_index = cls._build_bm25_index([{'text': d} for d in documents])

            return f"Successfully indexed {total_chunks} chunks from `{path}` into VectorDB (mode={chunk_mode})."
        except Exception as e:
            logger.error(f"Failed to index: {e}")
            return f"Failed to index VectorDB: {e}"

    @classmethod
    def semantic_search_code(
        cls,
        query: str,
        n_results: int = 5,
        workdir: Path = None,
        use_hybrid: bool = True
    ) -> str:
        """
        利用混合检索（向量 + BM25）通过自然语言匹配相关代码片段。

        Args:
            query: 自然语言查询
            n_results: 返回结果数量
            workdir: 工作目录
            use_hybrid: 是否使用混合检索（False 则只用向量）
        """
        logger.info(f"Tool semantic_search_code: '{query}' (hybrid={use_hybrid})")
        if not cls._init_db(workdir):
            return "Error: ChromaDB not installed. Run: pip install chromadb sentence-transformers"

        try:
            if use_hybrid and cls._bm25_index:
                results = cls._hybrid_search(query, n_results * 2)
                results = results[:n_results]
            else:
                results_raw = cls._collection.query(
                    query_texts=[query],
                    n_results=n_results
                )
                results = []
                if results_raw["documents"] and results_raw["documents"][0]:
                    for i, doc in enumerate(results_raw["documents"][0]):
                        meta = results_raw["metadatas"][0][i] if i < len(results_raw["metadatas"][0]) else {}
                        dist = results_raw["distances"][0][i] if i < len(results_raw["distances"][0]) else 0
                        results.append((doc, meta, 1.0 - dist))

            if not results:
                return "No semantic matches found in VectorDB. Have you run `index_codebase`?"

            out = [f"Hybrid Search Results for: '{query}'\n"]
            out.append(f"(Using {'vector + BM25 hybrid' if use_hybrid else 'vector only'} retrieval)\n")

            for i, (doc, meta, score) in enumerate(results, 1):
                chunk_type = meta.get('chunk_type', 'unknown')
                entity_info = ""
                if chunk_type == 'semantic':
                    entity_type = meta.get('entity_type', '')
                    entity_name = meta.get('entity_name', '')
                    entity_info = f" [{entity_type}] {entity_name}"

                file_path = meta.get('file', 'unknown')
                start_line = meta.get('start_line', 0)

                out.append(f"--- Result {i} | Score: {score:.4f} | {file_path}{entity_info} (Line {start_line}) ---")
                out.append(doc[:2000])
                out.append("\n")

            return "\n".join(out)[:50000]
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return f"Semantic search failed: {e}"

    @classmethod
    def clear_index(cls) -> str:
        """清除所有索引数据。"""
        if cls._collection:
            try:
                cls._collection.delete(where={})
                cls._bm25_index = {}
                return "VectorDB index cleared successfully."
            except Exception as e:
                return f"Failed to clear index: {e}"
        return "No active VectorDB connection."

    @classmethod
    def get_index_stats(cls) -> dict:
        """获取索引统计信息。"""
        if not cls._collection:
            return {"status": "not_initialized"}

        try:
            count = cls._collection.count()
            return {
                "status": "ready",
                "total_chunks": count,
                "bm25_indexed": len(cls._bm25_index.get('doc_lengths', [])),
                "hybrid_enabled": bool(cls._bm25_index)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
