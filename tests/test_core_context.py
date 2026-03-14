import pytest
from production_agent.core.context import ContextManager

def test_context_manager_microcompact():
    """测试微压缩：跳过图像，合并连续角色消息"""
    # 构造待压缩消息
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": " world"},
        {"role": "assistant", "content": [{"type": "image", "source": "..."}]},
        {"role": "assistant", "content": "hi"}
    ]
    
    # ContextManager.microcompact 是静态方法，直接调用
    ContextManager.microcompact(messages)
    
    # 期望：
    # 1. user + user 合并为 "hello\n world"
    # 2. assistant 的 image 被移除，但助理消息不合并
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert "hello" in messages[0]["content"] and "world" in messages[0]["content"]
    assert messages[1]["role"] == "assistant"
    # 列表内容被过滤为空
    assert messages[1]["content"] == []
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "hi"

def test_context_manager_auto_compact():
    """测试达到阈值后的自动压缩"""
    # 模拟 31 条消息以触发压缩 (> 30)
    messages = [{"role": "user", "content": f"msg {i}"} for i in range(31)]
    
    # 模拟 LLM 回调
    mock_llm = MagicMock()
    mock_llm.return_value.content = [MagicMock(text="History summary")]
    
    ContextManager.auto_compact(messages, mock_llm)
    
    # 压缩后长度应显著减少 (1 + 1 + 8 = 10)
    assert len(messages) <= 10
    assert "History summary" in str(messages[1]["content"])

def test_perform_full_compression():
    """测试全量清理"""
    messages = [{"role": "user", "content": "test"}]
    ContextManager.perform_full_compression(messages, "Current tasks...")
    assert len(messages) == 1
    assert "[SYSTEM RESTART]" in messages[0]["content"]

from unittest.mock import MagicMock
