import pytest
import json
from unittest.mock import MagicMock, patch
from production_agent.core.loop import agent_loop, run_subagent

@pytest.fixture(autouse=True)
def mock_globals(monkeypatch):
    """Mock core.loop 中的全局变量"""
    mock_todo = MagicMock()
    mock_todo.list_all.return_value = "No tasks."
    mock_bus = MagicMock()
    mock_bg = MagicMock()
    mock_bg.drain.return_value = []
    
    monkeypatch.setattr("production_agent.core.loop.TODO", mock_todo)
    monkeypatch.setattr("production_agent.core.loop.BUS", mock_bus)
    monkeypatch.setattr("production_agent.core.loop.BG", mock_bg)
    
    # 修复源码中的 NameError Bug: TOOL_HANDLERS 未定义
    # 我们根据 get_loop_handlers(TODO) 的逻辑预先注入
    from production_agent.core.loop import get_loop_handlers
    monkeypatch.setattr("production_agent.core.loop.TOOL_HANDLERS", get_loop_handlers(mock_todo))
    
    return mock_todo, mock_bus, mock_bg

@patch("production_agent.core.loop.LLMProvider.safe_llm_call")
@patch("production_agent.core.loop.console")
def test_agent_loop_basic_exit(mock_console, mock_llm, mock_globals):
    """测试主循环：Agent 直接结束对话"""
    messages = [{"role": "user", "content": "hello"}]
    
    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"
    mock_response.content = [MagicMock(type="text", text="Hi there!")]
    mock_llm.return_value = mock_response
    
    agent_loop(messages)
    
    assert len(messages) == 2
    assert messages[1]["role"] == "assistant"
    # 验证是否调用了 LLM
    assert mock_llm.called

@patch("production_agent.core.loop.LLMProvider.safe_llm_call")
@patch("production_agent.core.loop.console")
def test_agent_loop_tool_use(mock_console, mock_llm, mock_globals):
    """测试主循环：Agent 调用工具"""
    mock_todo, mock_bus, mock_bg = mock_globals
    messages = [{"role": "user", "content": "Check tasks"}]
    
    # 第一回合：调用 compress
    resp1 = MagicMock()
    resp1.stop_reason = "tool_use"
    t1 = MagicMock()
    t1.type = "tool_use"
    t1.id = "c1"
    t1.name = "compress"
    t1.input = {}
    resp1.content = [t1]
    
    # 第二回合：结束
    resp2 = MagicMock()
    resp2.stop_reason = "end_turn"
    resp2.content = [MagicMock(type="text", text="Compressed")]
    
    mock_llm.side_effect = [resp1, resp2]
    
    agent_loop(messages)
    
    # 验证是否发生了压缩 (messages 会被清空并注入重启消息)
    assert len(messages) == 1
    assert "[SYSTEM RESTART]" in messages[0]["content"]

@patch("production_agent.core.loop.LLMProvider.safe_llm_call")
@patch("production_agent.core.loop.console")
def test_run_subagent_recursion(mock_console, mock_llm, mock_globals):
    """测试子 Agent 运行及其递归调用子任务"""
    mock_todo, _, _ = mock_globals
    
    # 模拟 LLM 第一次返回调用 task 工具，第二次返回文本
    resp1 = MagicMock(stop_reason="tool_use")
    t1 = MagicMock(type="tool_use", id="sub1", name="task")
    t1.input = {"prompt": "subtask", "agent_type": "Recursive"}
    resp1.content = [t1]
    
    resp2 = MagicMock(stop_reason="stop")
    resp2.content = [MagicMock(type="text", text="Done Sub")]
    
    # 为递归调用准备响应
    resp_recursive = MagicMock(stop_reason="stop")
    resp_recursive.content = [MagicMock(type="text", text="Recursive Result")]
    
    mock_llm.side_effect = [resp1, resp_recursive, resp2]
    
    result = run_subagent("Start prompt", "LeadSub")
    assert "LeadSub Agent Completed" in result
    assert "Done Sub" in result
