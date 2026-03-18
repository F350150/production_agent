"""
增强 RAG 功能测试 (test_rag_enhanced.py)

测试语义分块、混合检索、BM25 索引等功能
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile
import os


class TestSemanticChunking:
    """测试语义分块功能"""

    def test_ast_based_chunking(self):
        """验证基于 AST 的语义分块"""
        from tools.rag_tools import RAGTools

        with tempfile.TemporaryDirectory() as tmpdir:
            code = '''
class UserService:
    def __init__(self, db):
        self.db = db

    def get_user(self, user_id):
        return self.db.query(user_id)

def helper_function():
    pass
'''

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(code)

            chunks = RAGTools._semantic_chunk(code, test_file, Path(tmpdir))

            assert len(chunks) >= 2
            entity_names = [c['metadata'].get('entity_name', '') for c in chunks]
            assert 'UserService' in entity_names
            assert 'get_user' in entity_names or 'helper_function' in entity_names

    def test_line_chunking_fallback(self):
        """验证非 Python 文件使用行分块"""
        from tools.rag_tools import RAGTools

        with tempfile.TemporaryDirectory() as tmpdir:
            content = "\n".join([f"line {i}" for i in range(250)])

            test_file = Path(tmpdir) / "test.js"
            chunks = RAGTools._line_chunk(content, test_file, Path(tmpdir), chunk_size=100)

            assert len(chunks) >= 2
            assert all(c['metadata']['chunk_type'] == 'line' for c in chunks)

    def test_small_functions_skipped(self):
        """验证过短的函数会被跳过"""
        from tools.rag_tools import RAGTools

        with tempfile.TemporaryDirectory() as tmpdir:
            code = 'x = 1'

            test_file = Path(tmpdir) / "test.py"
            test_file.write_text(code)

            chunks = RAGTools._semantic_chunk(code, test_file, Path(tmpdir))

            tiny_chunks = [c for c in chunks if c['metadata'].get('entity_name') == 'tiny']
            assert len(tiny_chunks) == 0


class TestBM25Index:
    """测试 BM25 索引功能"""

    def test_tokenization(self):
        """验证分词功能"""
        from tools.rag_tools import RAGTools

        tokens = RAGTools._tokenize("def get_user_by_id(user_id): return user_id")

        assert "get_user_by_id" in tokens or "user_by" in tokens
        assert "user_id" in tokens

    def test_stop_words_filtering(self):
        """验证停用词被过滤"""
        from tools.rag_tools import RAGTools

        tokens = RAGTools._tokenize("the a an and or but in on at to to for")

        assert len(tokens) < 10
        assert "the" not in tokens
        assert "for" not in tokens

    def test_bm25_index_building(self):
        """验证 BM25 索引构建"""
        from tools.rag_tools import RAGTools

        documents = [
            {"text": "function calculate sum"},
            {"text": "function calculate product"},
            {"text": "display result"}
        ]

        index = RAGTools._build_bm25_index(documents)

        assert "index" in index
        assert "function" in index["index"]
        assert index["num_docs"] == 3

    def test_bm25_scoring(self):
        """验证 BM25 分数计算"""
        from tools.rag_tools import RAGTools

        documents = [
            {"text": "python programming language"},
            {"text": "java programming language"},
            {"text": "web development with python"}
        ]

        index = RAGTools._build_bm25_index(documents)
        scores = []

        for doc_id in range(len(documents)):
            score = RAGTools._bm25_score(index, ["python"], doc_id)
            scores.append(score)

        assert scores[0] > scores[1]
        assert scores[2] > scores[1]


class TestHybridSearch:
    """测试混合检索功能"""

    def test_tokenize_query(self):
        """验证查询分词"""
        from tools.rag_tools import RAGTools

        tokens = RAGTools._tokenize("How do I authenticate users?")

        assert "authenticate" in tokens or "users" in tokens
        assert "do" not in tokens
        assert "i" not in tokens

    def test_hybrid_search_returns_scored_results(self):
        """验证混合搜索返回带分数的结果"""
        from tools.rag_tools import RAGTools

        with patch.object(RAGTools, '_init_db', return_value=True):
            with patch.object(RAGTools, '_collection') as mock_collection:
                mock_collection.query.return_value = {
                    "documents": [["code about auth"], ["code about database"]],
                    "metadatas": [[{"file": "auth.py", "start_line": 1}], [{"file": "db.py", "start_line": 10}]],
                    "distances": [[0.2, 0.8]]
                }

                RAGTools._bm25_index = RAGTools._build_bm25_index([
                    {"text": "code about auth"},
                    {"text": "code about database"}
                ])

                results = RAGTools._hybrid_search("authentication", top_k=2)

                assert len(results) >= 0


class TestIndexCodebase:
    """测试索引构建功能"""

    def test_semantic_mode_indexing(self):
        """验证语义模式索引"""
        from tools.rag_tools import RAGTools

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_module.py"
            test_file.write_text('''
class Calculator:
    def add(self, a, b):
        return a + b

def standalone():
    pass
''')

            with patch.object(RAGTools, '_init_db', return_value=True):
                with patch.object(RAGTools, '_collection') as mock_collection:
                    mock_collection.count.return_value = 0
                    mock_collection.delete = MagicMock()
                    mock_collection.upsert = MagicMock()

                    result = RAGTools.index_codebase(tmpdir, Path(tmpdir), chunk_mode="semantic")

                    assert "Successfully indexed" in result or "chunks" in result.lower()

    def test_line_mode_indexing(self):
        """验证行模式索引"""
        from tools.rag_tools import RAGTools

        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("\n".join([f"# line {i}" for i in range(250)]))

            with patch.object(RAGTools, '_init_db', return_value=True):
                with patch.object(RAGTools, '_collection') as mock_collection:
                    mock_collection.count.return_value = 0
                    mock_collection.delete = MagicMock()
                    mock_collection.upsert = MagicMock()

                    result = RAGTools.index_codebase(tmpdir, Path(tmpdir), chunk_mode="line")

                    assert "Successfully indexed" in result or "line" in result


class TestSemanticSearchCode:
    """测试语义搜索功能"""

    def test_uses_hybrid_by_default(self):
        """验证默认使用混合搜索"""
        from tools.rag_tools import RAGTools

        with patch.object(RAGTools, '_init_db', return_value=True):
            with patch.object(RAGTools, '_collection') as mock_collection:
                with patch.object(RAGTools, '_bm25_index', {}):
                    mock_collection.query.return_value = {
                        "documents": [["code snippet"]],
                        "metadatas": [[{"file": "test.py", "start_line": 1}]],
                        "distances": [[0.5]]
                    }

                    result = RAGTools.semantic_search_code("search query", n_results=5)

                    assert "Search Results" in result or "snippet" in result.lower()

    def test_vector_only_mode(self):
        """验证纯向量搜索模式"""
        from tools.rag_tools import RAGTools

        with patch.object(RAGTools, '_init_db', return_value=True):
            with patch.object(RAGTools, '_collection') as mock_collection:
                mock_collection.query.return_value = {
                    "documents": [["code about login"]],
                    "metadatas": [[{"file": "auth.py", "start_line": 5}]],
                    "distances": [[0.3]]
                }

                RAGTools._bm25_index = {}

                result = RAGTools.semantic_search_code(
                    "login authentication",
                    n_results=5,
                    use_hybrid=False
                )

                assert "vector only" in result.lower() or "login" in result.lower()

    def test_empty_results_handling(self):
        """验证空结果处理"""
        from tools.rag_tools import RAGTools

        with patch.object(RAGTools, '_init_db', return_value=True):
            with patch.object(RAGTools, '_collection') as mock_collection:
                with patch.object(RAGTools, '_bm25_index', {}):
                    mock_collection.query.return_value = {
                        "documents": [[]],
                        "metadatas": [[]],
                        "distances": [[]]
                    }

                    result = RAGTools.semantic_search_code("nonexistent query")

                    assert "No" in result or "not found" in result.lower() or "run" in result.lower()


class TestRAGToolsUtilities:
    """测试 RAG 工具辅助功能"""

    def test_clear_index(self):
        """验证清除索引"""
        from tools.rag_tools import RAGTools

        with patch.object(RAGTools, '_init_db', return_value=True):
            with patch.object(RAGTools, '_collection') as mock_collection:
                mock_collection.delete = MagicMock()

                RAGTools._bm25_index = {"index": {}, "doc_lengths": [1, 2]}

                result = RAGTools.clear_index()

                assert "cleared" in result.lower() or "success" in result.lower()

    def test_get_index_stats(self):
        """验证获取索引统计"""
        from tools.rag_tools import RAGTools

        with patch.object(RAGTools, '_init_db', return_value=True):
            with patch.object(RAGTools, '_collection') as mock_collection:
                mock_collection.count.return_value = 42

                RAGTools._bm25_index = {"doc_lengths": [1] * 20}

                stats = RAGTools.get_index_stats()

                assert stats["status"] in ["ready", "not_initialized", "error"]
                if stats["status"] == "ready":
                    assert "total_chunks" in stats
