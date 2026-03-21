import pytest
from core.context import ContextManager
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

def test_context_manager_trim_context_fallback():
    """测试没有 llm 时的回退截断逻辑"""
    messages = [HumanMessage(content=f"msg {i}") for i in range(50)]
    system_msg = SystemMessage(content="You are a helpful assistant.")
    messages.insert(0, system_msg)
    
    trimmed = ContextManager.trim_context(messages)
    
    # 期望保留 system message 和最后 20 条
    assert len(trimmed) == 21
    assert isinstance(trimmed[0], SystemMessage)
    assert trimmed[0].content == "You are a helpful assistant."
    assert trimmed[1].content == "msg 30"
    assert trimmed[-1].content == "msg 49"

def test_perform_full_compression():
    """测试全量清理"""
    messages = [HumanMessage(content="test")]
    ContextManager.perform_full_compression(messages, "Current tasks...")
    assert len(messages) == 1
    assert isinstance(messages[0], HumanMessage)
    assert "[SYSTEM RESTART]" in messages[0].content

from unittest.mock import MagicMock
