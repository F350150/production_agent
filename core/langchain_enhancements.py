"""
LangChain 增强模块 (LangChain Enhancements)

提供 LangChain/LangGraph 高级功能：
1. LCEL 链式调用
2. 工具自动绑定 (bind_tools)
3. 增强记忆管理
4. RAG RetrievalQA 集成
5. 多种 Agent 类型
6. 流式输出
7. LangSmith 评估支持

注意: LangChain 1.0 重构了 API，本模块已适配新结构。
"""

import os
import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)

LANGCHAIN_CORE_AVAILABLE = False
LANGCHAIN_AGENTS_AVAILABLE = False
LANGCHAIN_CHAINS_AVAILABLE = False
LANGCHAIN_MEMORY_AVAILABLE = False
LANGCHAIN_TEXT_SPLITTERS_AVAILABLE = False
LANGSMITH_AVAILABLE = False

if TYPE_CHECKING:
    from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
    from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
    from langchain_core.runnables import RunnableSequence
    from langchain_core.language_models import BaseChatModel

try:
    from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
    from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
    from langchain_core.runnables import RunnablePassthrough, RunnableLambda, RunnableSequence, chain
    from langchain_core.language_models import BaseChatModel
    from langchain_core.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
    from langchain_core.callbacks.manager import CallbackManager
    LANGCHAIN_CORE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"langchain_core not installed: {e}")

try:
    from langgraph.prebuilt import create_react_agent
    from langgraph.graph import StateGraph, END, MessagesState
    LANGCHAIN_AGENTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"langgraph not installed (agents moved here in langchain 1.0): {e}")

try:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import RunnableSequence
    LANGCHAIN_CHAINS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"langchain_core not installed for chains: {e}")

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    LANGCHAIN_TEXT_SPLITTERS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"langchain_text_splitters not installed: {e}")

try:
    from langchain_community.chat_message_histories import ChatMessageHistory
    from langchain_core.messages import BaseMessage
    LANGCHAIN_MEMORY_AVAILABLE = True
except ImportError as e:
    logger.warning(f"langchain_community.chat_message_histories not installed: {e}")
    LANGCHAIN_MEMORY_AVAILABLE = False

try:
    from langsmith import Client as LangSmithClient
    LANGSMITH_AVAILABLE = True
except ImportError as e:
    logger.warning(f"langsmith not installed: {e}")


class LCELChainBuilder:
    """
    LCEL (LangChain Expression Language) 链构建器
    
    使用示例:
        builder = LCELChainBuilder(llm)
        chain = builder.create_qa_chain(prompt_template, output_parser)
        result = chain.invoke({"question": "..."})
    """
    
    def __init__(self, llm: "BaseChatModel"):
        self.llm = llm
        self._chain: Optional["RunnableSequence"] = None
    
    def create_qa_chain(
        self,
        system_prompt: str,
        output_parser: Optional[Any] = None
    ) -> "RunnableSequence":
        """
        创建问答链：prompt -> llm -> output_parser
        
        Args:
            system_prompt: 系统提示模板
            output_parser: 输出解析器 (默认 StrOutputParser)
        
        Returns:
            RunnableSequence 链
        """
        if not LANGCHAIN_CORE_AVAILABLE:
            raise ImportError("langchain_core is required")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{question}")
        ])
        
        parser = output_parser or StrOutputParser()
        
        self._chain = prompt | self.llm | parser
        return self._chain
    
    def create_conversation_chain(
        self,
        system_prompt: str = "You are a helpful AI assistant."
    ) -> "RunnableSequence":
        """
        创建对话链，支持多轮对话
        
        Returns:
            RunnableSequence 链
        """
        if not LANGCHAIN_CORE_AVAILABLE:
            raise ImportError("langchain_core is required")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
            ("assistant", "{agent_scratchpad}")
        ])
        
        self._chain = prompt | self.llm | StrOutputParser()
        return self._chain
    
    def pipe(self, *functions: Callable) -> "RunnableSequence":
        """
        管道方式组合多个函数
        
        Example:
            chain = builder.pipe(func1, func2, func3)
        """
        return RunnablePassthrough() | RunnableLambda(lambda x: x)
    
    @property
    def chain(self) -> Optional["RunnableSequence"]:
        return self._chain


class ToolBinder:
    """
    工具自动绑定器
    
    使用 bind_tools 自动将工具绑定到 LLM，支持:
    - 自动工具调用
    - 结构化输出
    - 多工具协调
    """
    
    def __init__(self, llm: "BaseChatModel"):
        self.llm = llm
        self._bound_llm = llm
    
    def bind_tools(self, tools: List[Any], **kwargs) -> "BaseChatModel":
        """
        绑定工具到 LLM
        
        Args:
            tools: LangChain Tool 对象列表
            **kwargs: 额外参数 (e.g., parallel_tool_calls=True)
        
        Returns:
            绑定后的 LLM
        """
        if not hasattr(self.llm, "bind_tools"):
            raise ValueError(f"LLM {type(self.llm)} does not support bind_tools")
        
        self._bound_llm = self.llm.bind_tools(tools, **kwargs)
        return self._bound_llm
    
    def bind_tools_as_openai_format(self, tools: List[Dict]) -> "BaseChatModel":
        """
        以 OpenAI 格式绑定工具 (function calling)
        
        Args:
            tools: OpenAI 格式的工具定义列表
        
        Returns:
            绑定后的 LLM
        """
        if not hasattr(self.llm, "bind_tools"):
            raise ValueError(f"LLM {type(self.llm)} does not support bind_tools")
        
        self._bound_llm = self.llm.bind_tools(tools=tools, tool_choice="auto")
        return self._bound_llm
    
    def get_bound_llm(self) -> "BaseChatModel":
        return self._bound_llm


class EnhancedMemory:
    """
    增强记忆管理
    
    支持:
    - 对话缓冲记忆
    - 向量存储记忆
    - 混合记忆模式
    """
    
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._memory: Optional[Any] = None
        self._chat_history: Optional[Any] = None
        
        if LANGCHAIN_MEMORY_AVAILABLE:
            self._chat_history = ChatMessageHistory()
    
    def create_buffer_memory(
        self,
        return_messages: bool = True,
        output_key: str = "response",
        input_key: str = "input"
    ) -> Any:
        """
        创建缓冲记忆
        """
        if not LANGCHAIN_MEMORY_AVAILABLE:
            raise ImportError("langchain_community.memory is required")
        
        try:
            from langchain_community.memory import ConversationBufferMemory
            self._memory = ConversationBufferMemory(
                chat_memory=self._chat_history,
                return_messages=return_messages,
                output_key=output_key,
                input_key=input_key
            )
            return self._memory
        except ImportError:
            logger.warning("ConversationBufferMemory not available in langchain_community")
            return None
    
    def save_context(self, inputs: Dict, outputs: Dict) -> None:
        """保存对话上下文"""
        if self._memory:
            self._memory.save_context(inputs, outputs)
    
    def load_memory_variables(self) -> Dict:
        """加载记忆变量"""
        if self._memory:
            return self._memory.load_memory_variables({})
        return {}
    
    def clear(self) -> None:
        """清除记忆"""
        if self._memory:
            self._memory.clear()
        if self._chat_history:
            self._chat_history.clear()
    
    def get_chat_history(self) -> List:
        """获取聊天历史"""
        if self._chat_history:
            return self._chat_history.messages
        return []


class LangChainRAG:
    """
    LangChain RAG 集成
    
    使用 LangChain 的 RetrievalQA 和 ConversationalRetrievalChain
    """
    
    def __init__(self, llm: "BaseChatModel", vectorstore: Any):
        self.llm = llm
        self.vectorstore = vectorstore
        self._qa_chain: Optional[Any] = None
        self._conversational_chain: Optional[Any] = None
    
    def create_retrieval_qa(
        self,
        chain_type: str = "stuff",
        return_source_documents: bool = True,
        verbose: bool = False
    ) -> Any:
        """
        创建 RetrievalQA 链
        """
        if not LANGCHAIN_CORE_AVAILABLE:
            raise ImportError("langchain_core is required for RetrievalQA")
        
        try:
            from langchain.chains import RetrievalQA
            self._qa_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type=chain_type,
                retriever=self.vectorstore.as_retriever(),
                return_source_documents=return_source_documents,
                verbose=verbose
            )
            return self._qa_chain
        except ImportError:
            logger.warning("RetrievalQA not available. Use vectorstore.as_retriever() directly.")
            return None
    
    def invoke(self, query: str, with_sources: bool = False) -> Dict[str, Any]:
        """执行检索问答"""
        if not self._qa_chain:
            self.create_retrieval_qa()
        
        if self._qa_chain:
            if with_sources:
                return self._qa_chain.with_sources()(query)
            return self._qa_chain(query)
        
        retriever = self.vectorstore.as_retriever()
        docs = retriever.invoke(query)
        return {"result": "\n".join([doc.page_content for doc in docs]), "source_documents": docs}


class StreamingManager:
    """
    流式输出管理器
    """
    
    def __init__(self):
        self.callbacks: List[Any] = []
        self._streaming_handler = None
        
        if LANGCHAIN_CORE_AVAILABLE:
            self._streaming_handler = StreamingStdOutCallbackHandler()
    
    def get_callback_manager(self) -> Optional[Any]:
        """获取回调管理器"""
        if not LANGCHAIN_CORE_AVAILABLE:
            return None
        
        return CallbackManager([self._streaming_handler])
    
    def add_callback(self, callback: Any) -> None:
        """添加自定义回调"""
        if LANGCHAIN_CORE_AVAILABLE:
            self.callbacks.append(CallbackManager([callback]))
    
    async def stream_async(self, chain: Any, input_data: Dict) -> str:
        """异步流式执行"""
        output = ""
        async for chunk in chain.astream(input_data):
            output += chunk
            print(chunk, end="", flush=True)
        return output
    
    def stream_sync(self, chain: Any, input_data: Dict) -> str:
        """同步流式执行"""
        output = ""
        for chunk in chain.stream(input_data):
            output += chunk
            print(chunk, end="", flush=True)
        return output


class LangSmithEvaluator:
    """
    LangSmith 评估器
    
    提供:
    - 跟踪记录
    - 数据集管理
    - 评估运行
    """
    
    def __init__(self, project_name: str = "production_agent"):
        self.project_name = project_name
        self._client = None
        
        if LANGSMITH_AVAILABLE:
            self._setup_langsmith()
    
    def _setup_langsmith(self) -> None:
        """设置 LangSmith"""
        os.environ["LANGCHAIN_TRACING_V2"] = os.environ.get("LANGCHAIN_TRACING_V2", "true")
        os.environ["LANGCHAIN_PROJECT"] = self.project_name
        os.environ["LANGCHAIN_ENDPOINT"] = os.environ.get("LANGCHAIN_ENDPOINT", "https://api.langsmith.com")
        os.environ["LANGCHAIN_API_KEY"] = os.environ.get("LANGCHAIN_API_KEY", "")
        
        try:
            self._client = LangSmithClient()
        except Exception as e:
            logger.warning(f"Failed to initialize LangSmith client: {e}")
    
    def get_client(self) -> Optional[Any]:
        """获取 LangSmith 客户端"""
        return self._client
    
    def create_dataset(
        self,
        name: str,
        description: str = "",
        data: Optional[List[Dict]] = None
    ) -> Optional[Any]:
        """
        创建数据集
        """
        if not self._client:
            logger.warning("LangSmith client not available, skipping dataset creation")
            return None
        
        try:
            dataset = self._client.create_dataset(
                dataset_name=name,
                description=description
            )
            
            if data:
                self._client.create_examples(
                    dataset_id=dataset.id,
                    inputs=data
                )
            
            return dataset
        except Exception as e:
            logger.error(f"Failed to create LangSmith dataset: {e}")
            return None


class MultiAgentFactory:
    """
    多 Agent 工厂
    
    使用 langgraph 创建不同类型的 Agent
    """
    
    def __init__(self, llm: "BaseChatModel", tools: List[Any]):
        self.llm = llm
        self.tools = tools
    
    def create_react_agent(
        self,
        system_message: Optional[str] = None,
        verbose: bool = True
    ) -> Any:
        """
        创建 ReAct Agent (使用 langgraph)
        
        推理+行动循环
        """
        if not LANGCHAIN_AGENTS_AVAILABLE:
            raise ImportError("langgraph is required for ReAct agent")
        
        return create_react_agent(
            self.llm,
            self.tools,
            state_schema=MessagesState,
            prompt=system_message
        )
    
    def create_state_graph_agent(
        self,
        nodes: Dict[str, Callable],
        edges: Dict[str, List[str]],
        initial_state: Optional[Dict] = None
    ) -> StateGraph:
        """
        创建自定义 StateGraph Agent
        
        Args:
            nodes: 节点名称到函数的映射
            edges: 节点到后续节点的映射
            initial_state: 初始状态
        """
        workflow = StateGraph(MessagesState)
        
        for name, node_func in nodes.items():
            workflow.add_node(name, node_func)
        
        for source, targets in edges.items():
            for target in targets:
                workflow.add_edge(source, target)
        
        workflow.set_entry_point(list(nodes.keys())[0])
        
        return workflow.compile()


def create_text_splitter(
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    separators: Optional[List[str]] = None
) -> Any:
    """
    创建文本分割器
    
    Args:
        chunk_size: 块大小
        chunk_overlap: 块重叠
        separators: 分隔符列表
    
    Returns:
        RecursiveCharacterTextSplitter
    """
    if not LANGCHAIN_TEXT_SPLITTERS_AVAILABLE:
        raise ImportError("langchain_text_splitters is required")
    
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators or ["\n\n", "\n", " ", ""]
    )


def split_documents(
    documents: List[Any],
    text_splitter: Optional[Any] = None
) -> List[Any]:
    """
    分割文档
    
    Args:
        documents: 文档列表
        text_splitter: 文本分割器
    
    Returns:
        分割后的文档列表
    """
    if text_splitter is None:
        text_splitter = create_text_splitter()
    
    return text_splitter.split_documents(documents)
