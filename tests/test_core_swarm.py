import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from core.swarm import SwarmOrchestrator
from utils.converters import serialize_message_content
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

def test_serialize_content_handles_various_blocks():
    """测试 serialize_message_content 对不同 Block 类型的转换"""
    # 字符串直接返回
    assert serialize_message_content("hello") == "hello"
    
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
    
    result = serialize_message_content(blocks)
    assert len(result) == 4
    assert result[0] == {"type": "text", "text": "plain dict"}
    assert result[1] == {"type": "text", "text": "mocked text"}
    assert result[2] == {"type": "tool_use", "id": "t1", "name": "search", "input": {"q": "test"}}
    assert result[3] == {"type": "tool_result", "tool_use_id": "t1", "content": "result"}

@pytest.mark.asyncio
class TestSwarmOrchestrator:
    """测试 SwarmOrchestrator 编排逻辑"""

    @pytest.fixture
    def mock_deps(self):
        bus = MagicMock()
        todo = MagicMock()
        todo.list_all.return_value = "No tasks."
        return bus, todo

    @pytest.fixture
    def mock_checkpointer(self):
        # mock AsyncSqliteSaver.from_conn_string
        mock_saver = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_saver
        mock_ctx.__aexit__.return_value = False
        return mock_ctx

    async def test_run_swarm_loop_handover_logic(self, mock_deps, mock_checkpointer):
        """测试 Agent 之间的 Handover 交接逻辑 (基于 astream_events)"""
        bus, todo = mock_deps
        orch = SwarmOrchestrator(bus, todo)
        
        mock_app = AsyncMock()
        
        # 模拟事件流，反映角色流转
        async def mock_astream_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "ProductManager"}
            yield {"event": "on_tool_start", "name": "transfer_to_Architect", "data": {"input": {"msg": "PRD ready"}}}
            yield {"event": "on_chain_start", "name": "Architect"}
            
        mock_app.astream_events = mock_astream_events
        
        # 模拟最终状态
        mock_state = AsyncMock()
        mock_state.next = []
        mock_state.values = {"messages": [AIMessage(content="Finished")]}
        mock_app.aget_state.return_value = mock_state
        
        with patch.object(orch._app_uncompiled, "compile", return_value=mock_app), \
             patch("core.swarm.AsyncSqliteSaver.from_conn_string", return_value=mock_checkpointer):
            
            final_role = await orch.run_swarm_loop("ProductManager", user_message="Start")
            
            # 由于 on_chain_start 触发了 Architect，最终角色应更新
            assert final_role == "Architect"

    @patch("core.swarm.asyncio.to_thread", new_callable=AsyncMock)
    @patch("core.swarm.GOVERNANCE", {"dangerous_tools": ["rm_rf"]})
    async def test_run_swarm_loop_safety_guard_denied(self, mock_to_thread, mock_deps, mock_checkpointer):
        """测试破坏性工具被用户拒绝执行 (Human-in-the-loop)"""
        bus, todo = mock_deps
        orch = SwarmOrchestrator(bus, todo)
        
        # 模拟用户拒绝
        mock_to_thread.return_value = "n"
        
        mock_app = AsyncMock()
        
        async def mock_astream_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "ProductManager"}
            
        mock_app.astream_events = mock_astream_events
        
        # 模拟中间状态：触发了危险工具被挂起
        mock_state_1 = MagicMock()
        mock_state_1.next = ["ProductManager"]
        mock_interrupt = MagicMock()
        mock_interrupt.value = {"tool": "rm_rf", "args": {}, "message": "Agent 请求执行危险操作: rm_rf"}
        mock_task = MagicMock()
        mock_task.interrupts = [mock_interrupt]
        mock_state_1.tasks = [mock_task]
        
        mock_state_2 = MagicMock()
        mock_state_2.next = []
        mock_state_2.tasks = []
        
        mock_app.aget_state.side_effect = [mock_state_1, mock_state_2, mock_state_2]
        
        with patch.object(orch._app_uncompiled, "compile", return_value=mock_app), \
             patch("core.swarm.AsyncSqliteSaver.from_conn_string", return_value=mock_checkpointer), \
             patch("core.swarm.console.print") as mock_print:
             
            final_role = await orch.run_swarm_loop("ProductManager", user_message="Delete")
            
            # 因为拒绝且挂起，外层代码退出并保留原角色
            assert final_role == "ProductManager"
            mock_to_thread.assert_awaited_once()
            mock_print.assert_any_call("[bold red]❌ Denied. Interaction ended.[/bold red]")

    async def test_run_swarm_loop_safety_guard_approved(self, mock_deps, mock_checkpointer):
        """测试破坏性工具被用户同意执行"""
        bus, todo = mock_deps
        orch = SwarmOrchestrator(bus, todo)
        
        mock_app = AsyncMock()
        
        async def mock_astream_events(*args, **kwargs):
            yield {"event": "on_chain_start", "name": "ProductManager"}
            
        mock_app.astream_events = mock_astream_events
        
        # 我们需要 aget_state 第一次返回有 next 的状态和 interrupt，第二次返回没有 next
        mock_state_1 = MagicMock()
        mock_state_1.next = ["ProductManager"]
        mock_interrupt = MagicMock()
        mock_interrupt.value = {"tool": "write_file", "args": {}, "message": "Agent 请求执行危险操作: write_file"}
        mock_task = MagicMock()
        mock_task.interrupts = [mock_interrupt]
        mock_state_1.tasks = [mock_task]
        
        mock_state_2 = MagicMock()
        mock_state_2.next = []
        mock_state_2.tasks = []
        mock_state_2.values = {"messages": [AIMessage(content="Done")]}
        
        mock_app.aget_state.side_effect = [mock_state_1, mock_state_2, mock_state_2]
        
        with patch.object(orch._app_uncompiled, "compile", return_value=mock_app), \
             patch("core.swarm.AsyncSqliteSaver.from_conn_string", return_value=mock_checkpointer), \
             patch("core.swarm.asyncio.to_thread", new_callable=AsyncMock, return_value="y"), \
             patch("core.swarm.GOVERNANCE", {"dangerous_tools": ["write_file"]}):
             
            final_role = await orch.run_swarm_loop("ProductManager", user_message="Write it")
            
            assert final_role == "ProductManager"
