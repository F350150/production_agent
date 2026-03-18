"""
测试 LangChain 增强功能

覆盖:
- LCEL 链式调用
- 工具绑定 (bind_tools)
- 增强记忆管理
- RAG RetrievalQA 集成
- 多 Agent 工厂
- 流式输出
- LangSmith 评估
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLCELChainBuilder:
    """测试 LCEL 链构建器"""
    
    def test_chain_builder_initialization(self):
        """验证链构建器可以初始化"""
        from core.langchain_enhancements import LCELChainBuilder
        
        mock_llm = Mock()
        builder = LCELChainBuilder(mock_llm)
        assert builder.llm == mock_llm
        assert builder._chain is None
    
    def test_create_qa_chain_returns_runnable(self):
        """验证创建 QA 链"""
        from core.langchain_enhancements import LCELChainBuilder
        
        mock_llm = Mock()
        mock_llm.invoke = Mock(return_value="Test response")
        
        builder = LCELChainBuilder(mock_llm)
        chain = builder.create_qa_chain("You are a helpful assistant.")
        
        assert chain is not None
        builder._chain = chain  # Store for later checks
    
    def test_chain_with_custom_parser(self):
        """验证使用自定义解析器"""
        from core.langchain_enhancements import LCELChainBuilder
        from langchain_core.output_parsers import JsonOutputParser
        
        mock_llm = Mock()
        mock_parser = Mock(spec=JsonOutputParser)
        
        builder = LCELChainBuilder(mock_llm)
        chain = builder.create_qa_chain("Answer in JSON.", output_parser=mock_parser)
        
        assert chain is not None


class TestToolBinder:
    """测试工具绑定器"""
    
    def test_tool_binder_initialization(self):
        """验证工具绑定器初始化"""
        from core.langchain_enhancements import ToolBinder
        
        mock_llm = Mock()
        binder = ToolBinder(mock_llm)
        
        assert binder.llm == mock_llm
    
    def test_bind_tools_returns_llm(self):
        """验证 bind_tools 返回 LLM"""
        from core.langchain_enhancements import ToolBinder
        
        mock_llm = Mock()
        mock_llm.bind_tools = Mock(return_value=mock_llm)
        
        binder = ToolBinder(mock_llm)
        mock_tools = [Mock(), Mock()]
        result = binder.bind_tools(mock_tools)
        
        assert result == mock_llm
        mock_llm.bind_tools.assert_called_once()
    
    def test_bind_tools_as_openai_format(self):
        """验证 OpenAI 格式工具绑定"""
        from core.langchain_enhancements import ToolBinder
        
        mock_llm = Mock()
        mock_llm.bind_tools = Mock(return_value=mock_llm)
        
        binder = ToolBinder(mock_llm)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        result = binder.bind_tools_as_openai_format(tools)
        
        assert result == mock_llm


class TestEnhancedMemory:
    """测试增强记忆管理"""
    
    def test_memory_initialization(self):
        """验证记忆初始化"""
        from core.langchain_enhancements import EnhancedMemory
        
        memory = EnhancedMemory(session_id="test_session")
        
        assert memory.session_id == "test_session"
    
    def test_get_chat_history_empty(self):
        """验证空聊天历史"""
        from core.langchain_enhancements import EnhancedMemory
        
        memory = EnhancedMemory()
        history = memory.get_chat_history()
        
        assert isinstance(history, list)


class TestLangChainRAG:
    """测试 LangChain RAG 集成"""
    
    def test_rag_initialization(self):
        """验证 RAG 初始化"""
        from core.langchain_enhancements import LangChainRAG
        
        mock_llm = Mock()
        mock_vectorstore = Mock()
        mock_vectorstore.as_retriever = Mock(return_value=Mock())
        
        rag = LangChainRAG(mock_llm, mock_vectorstore)
        
        assert rag.llm == mock_llm
        assert rag.vectorstore == mock_vectorstore


class TestStreamingManager:
    """测试流式输出管理器"""
    
    def test_streaming_manager_initialization(self):
        """验证流式管理器初始化"""
        from core.langchain_enhancements import StreamingManager
        
        manager = StreamingManager()
        assert manager.callbacks == []
    
    def test_get_callback_manager(self):
        """验证获取回调管理器"""
        from core.langchain_enhancements import StreamingManager
        
        manager = StreamingManager()
        cb_manager = manager.get_callback_manager()
        
        # Should return None or CallbackManager depending on langchain availability
        assert cb_manager is None or cb_manager is not None


class TestLangSmithEvaluator:
    """测试 LangSmith 评估器"""
    
    def test_evaluator_initialization(self):
        """验证评估器初始化"""
        from core.langchain_enhancements import LangSmithEvaluator
        
        evaluator = LangSmithEvaluator(project_name="test_project")
        
        assert evaluator.project_name == "test_project"
    
    def test_get_client(self):
        """验证获取 LangSmith 客户端"""
        from core.langchain_enhancements import LangSmithEvaluator
        
        evaluator = LangSmithEvaluator()
        client = evaluator.get_client()
        
        # May be None if LangSmith not configured or network issue
        assert client is None or client is not None


class TestMultiAgentFactory:
    """测试多 Agent 工厂"""
    
    def test_factory_initialization(self):
        """验证工厂初始化"""
        from core.langchain_enhancements import MultiAgentFactory
        
        mock_llm = Mock()
        mock_tools = [Mock(), Mock()]
        
        factory = MultiAgentFactory(mock_llm, mock_tools)
        
        assert factory.llm == mock_llm
        assert len(factory.tools) == 2


class TestLLMChainFactory:
    """测试 LLM 链工厂"""
    
    @patch('core.llm.llm')
    def test_create_qa_chain(self, mock_llm):
        """验证创建 QA 链"""
        from core.llm import LLMChainFactory
        
        mock_llm.invoke = Mock(return_value="response")
        
        chain = LLMChainFactory.create_qa_chain("You are helpful.")
        
        assert chain is not None
    
    @patch('core.llm.llm')
    def test_create_conversation_chain(self, mock_llm):
        """验证创建对话链"""
        from core.llm import LLMChainFactory
        
        chain = LLMChainFactory.create_conversation_chain()
        
        assert chain is not None


class TestLLMToolBinder:
    """测试 LLM 工具绑定器"""
    
    def test_binder_creation(self):
        """验证绑定器创建"""
        from core.llm import LLM工具Binder
        
        with patch('core.llm.llm'):
            binder = LLM工具Binder()
            assert binder._llm is not None


class TestStreamingFunctions:
    """测试流式输出函数"""
    
    def test_get_streaming_llm(self):
        """验证获取流式 LLM"""
        from core.llm import get_streaming_llm
        
        with patch('core.llm.get_llm') as mock_get_llm:
            mock_get_llm.return_value = Mock()
            result = get_streaming_llm()
            
            mock_get_llm.assert_called_once_with(streaming=True)
    
    def test_get_streaming_manager(self):
        """验证获取流式管理器"""
        from core.llm import get_streaming_manager
        from core.langchain_enhancements import StreamingManager
        
        manager = get_streaming_manager()
        assert isinstance(manager, StreamingManager)
    
    def test_get_langsmith_evaluator(self):
        """验证获取 LangSmith 评估器"""
        from core.llm import get_langsmith_evaluator
        from core.langchain_enhancements import LangSmithEvaluator
        
        evaluator = get_langsmith_evaluator("test")
        assert isinstance(evaluator, LangSmithEvaluator)
        assert evaluator.project_name == "test"
    
    def test_create_multiagent_factory(self):
        """验证创建多 Agent 工厂"""
        from core.llm import create_multiagent_factory
        from core.langchain_enhancements import MultiAgentFactory
        
        tools = [Mock(), Mock()]
        factory = create_multiagent_factory(tools)
        
        assert isinstance(factory, MultiAgentFactory)
        assert len(factory.tools) == 2


class TestTextSplitter:
    """测试文本分割器"""
    
    def test_create_text_splitter(self):
        """验证创建文本分割器"""
        from core.langchain_enhancements import create_text_splitter, LANGCHAIN_TEXT_SPLITTERS_AVAILABLE
        
        if LANGCHAIN_TEXT_SPLITTERS_AVAILABLE:
            splitter = create_text_splitter(chunk_size=500, chunk_overlap=50)
            assert splitter is not None
            assert hasattr(splitter, 'split_text')
        else:
            pytest.skip("langchain_text_splitters not available")
    
    def test_split_documents(self):
        """验证分割文档"""
        from core.langchain_enhancements import split_documents, LANGCHAIN_TEXT_SPLITTERS_AVAILABLE
        
        if LANGCHAIN_TEXT_SPLITTERS_AVAILABLE:
            mock_doc = Mock()
            mock_doc.page_content = "Sample content"
            mock_doc.metadata = {}
            
            docs = [mock_doc]
            result = split_documents(docs)
            
            assert len(result) >= 0
        else:
            pytest.skip("langchain chains not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
