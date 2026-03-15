import pytest
import json
from unittest.mock import MagicMock, patch
from core.swarm import SwarmOrchestrator, _serialize_content

def test_serialize_content_handles_various_blocks():
    """测试 _serialize_content 对不同 Block 类型的转换"""
    # 字符串直接返回
    assert _serialize_content("hello") == "hello"
    
    # 模拟 Anthropic Block 对象
    b1 = MagicMock(type="text")
    b1.text = "mocked text"
    
    b2 = MagicMock(type="tool_use")
    b2.id = "t1"
    b2.name = "search"
    b2.input = {"q": "test"}
    
    b3 = MagicMock(type="tool_result")
    b3.tool_use_id = "t1"
    b3.content = "result"
    
    blocks = [
        {"type": "text", "text": "plain dict"},
        b1, b2, b3
    ]
    
    result = _serialize_content(blocks)
    assert len(result) == 4
    assert result[0] == {"type": "text", "text": "plain dict"}
    assert result[1] == {"type": "text", "text": "mocked text"}
    assert result[2] == {"type": "tool_use", "id": "t1", "name": "search", "input": {"q": "test"}}
    assert result[3] == {"type": "tool_result", "tool_use_id": "t1", "content": "result"}

class TestSwarmOrchestrator:
    """测试 SwarmOrchestrator 编排逻辑"""

    @pytest.fixture
    def mock_deps(self):
        bus = MagicMock()
        todo = MagicMock()
        todo.list_all.return_value = "No tasks."
        return bus, todo

    @patch("core.swarm.LLMProvider.safe_llm_call")
    @patch("core.swarm.ToolRegistry.get_role_tools")
    @patch("core.swarm.console")
    def test_run_swarm_loop_handover_logic(self, mock_console, mock_get_tools, mock_llm, mock_deps):
        """测试 Agent 之间的 Handover 交接逻辑"""
        bus, todo = mock_deps
        orch = SwarmOrchestrator(bus, todo)
        
        # 1. 模拟 ProductManager 调用 handover_to
        mock_response = MagicMock()
        mock_response.stop_reason = "tool_use"
        t_block = MagicMock()
        t_block.type = "tool_use"
        t_block.id = "call_1"
        t_block.name = "handover_to"
        t_block.input = {"role": "Architect", "msg": "PRD ready"}
        mock_response.content = [t_block]
        
        # 2. 模拟切换到 Architect 后的第二次调用直接结束
        mock_response_2 = MagicMock()
        mock_response_2.stop_reason = "end_turn"
        t2 = MagicMock()
        t2.type = "text"
        t2.text = "Finished"
        mock_response_2.content = [t2]
        
        mock_llm.side_effect = [mock_response, mock_response_2]
        mock_get_tools.return_value = [{"name": "handover_to"}]
        
        # 定义 handover handler
        def handover_handler(role, msg):
            return f"__HANDOVER_SIGNAL__::{role}::{msg}"
        orch.handlers = {"handover_to": handover_handler}
        
        orch.inject_user_message("ProductManager", "Start")
        final_role = orch.run_swarm_loop("ProductManager")
        
        # 应该发生了交接，最终停在 Architect
        assert final_role == "Architect"
        bus.send.assert_called_once_with(sender="ProductManager", recipient="Architect", content="PRD ready", msg_type="handover")

    @patch("core.swarm.LLMProvider.safe_llm_call")
    @patch("core.swarm.console")
    def test_run_swarm_loop_safety_guard_denied(self, mock_console, mock_llm, mock_deps):
        """测试破坏性工具被用户拒绝执行"""
        bus, todo = mock_deps
        orch = SwarmOrchestrator(bus, todo)
        
        with patch("core.swarm.ToolRegistry.get_role_tools") as mock_get_tools:
            mock_get_tools.return_value = [{"name": "rm_rf", "is_destructive": True}]
            orch.handlers = {"rm_rf": MagicMock()}
            
            mock_response = MagicMock()
            mock_response.stop_reason = "tool_use"
            t_block = MagicMock()
            t_block.type = "tool_use"
            t_block.id = "c1"
            t_block.name = "rm_rf"
            t_block.input = {}
            mock_response.content = [t_block]
            
            # 第二轮结束
            m2 = MagicMock()
            m2.type = "text"
            m2.text = "ok"
            mock_response_2 = MagicMock(stop_reason="stop", content=[m2])
            mock_llm.side_effect = [mock_response, mock_response_2]
            
            mock_console.input.return_value = "n"
            
            # 使用 ProductManager，它不会触发 Coder/Architect 的环境注入（环境注入会覆盖 tool_result）
            orch.inject_user_message("ProductManager", "Delete")
            orch.run_swarm_loop("ProductManager")
            
            orch.handlers["rm_rf"].assert_not_called()
            # 验证历史记录最后一条（通常是 tool_result 发回给模型的消息）
            history = orch.agent_contexts["ProductManager"]
            content_str = str([msg.get("content", "") for msg in history])
            assert "denied" in content_str.lower()

    @patch("core.swarm.LLMProvider.safe_llm_call")
    @patch("core.swarm.ToolRegistry.get_role_tools")
    @patch("core.swarm.console")
    @patch("tools.system_tools.SystemTools.list_files")
    def test_run_swarm_loop_env_injection_no_overwrite(self, mock_list_files, mock_console, mock_get_tools, mock_llm, mock_deps):
        """测试环境信息注入不会覆盖已有的 tool_result"""
        bus, todo = mock_deps
        orch = SwarmOrchestrator(bus, todo)
        
        # 模拟 Coder 角色以便触发环境注入
        mock_get_tools.return_value = [{"name": "read_file"}]
        orch.handlers = {"read_file": lambda path: "file content"}
        mock_list_files.return_value = "tree output"
        todo.list_all.return_value = "task list"

        # 第一回：调用 read_file
        t_block = MagicMock()
        t_block.type = "tool_use"
        t_block.id = "c1"
        t_block.name = "read_file"
        t_block.input = {"path": "test.txt"}
        mock_response = MagicMock(stop_reason="tool_use", content=[t_block])
        
        # 第二回：结束
        mock_response_2 = MagicMock(stop_reason="end_turn", content=[MagicMock(type="text", text="done")])
        mock_llm.side_effect = [mock_response, mock_response_2]

        # 注入初始消息
        orch.inject_user_message("Coder", "Read it")
        orch.run_swarm_loop("Coder")

        # 检查上下文
        history = orch.agent_contexts["Coder"]
        
        # 找到包含 tool_result 的消息
        tool_result_msg = next(m for m in history if isinstance(m.get("content"), list) and any(b.get("type") == "tool_result" for b in m["content"]))
        
        # 验证 tool_result 还在
        assert any(b.get("type") == "tool_result" and "file content" in b.get("content") for b in tool_result_msg["content"])
        # 验证 env info 也在
        assert any(b.get("type") == "text" and "task list" in b.get("text") for b in tool_result_msg["content"])
        assert any(b.get("type") == "text" and "tree output" in b.get("text") for b in tool_result_msg["content"])
