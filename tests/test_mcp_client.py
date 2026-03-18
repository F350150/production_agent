"""
MCP 客户端单元测试 (test_mcp_client.py)

测试策略：Mock subprocess 和 httpx，完全不需要真实 MCP 服务。

【关键设计】
MCP 客户端内部使用全局 _rpc_id_counter，跨测试递增。
因此测试中的 mock 不能依赖固定的 id（1, 2...），
而是需要一个"智能 mock"——捕获每次 stdin.write 中的实际 id，
并用该 id 作为响应的 id 返回，确保客户端的 id 匹配逻辑成功。
"""

import json
import pytest
import select
from unittest.mock import MagicMock, patch


class TestStdioMCPClient:
    """测试 StdioMCPClient 的 stdio 通信逻辑"""

    def _make_smart_mock_process(self, result_sequence: list):
        """
        创建一个智能 mock subprocess：
        - stdin.write() 被拦截，解析出每次请求的 id
        - stdout.readline() 根据请求 id 动态构造匹配响应（无需关心计数器绝对值）

        result_sequence: 每次 JSON-RPC 请求对应的 result 值列表
                         None 表示进程退出（readline 返回空字符串）
        """
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.flush = MagicMock()

        written_ids = []
        result_iter = iter(result_sequence)

        def capture_write(data):
            """拦截 stdin 写入，提取请求中的 id"""
            for line in data.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                    if "id" in req:
                        written_ids.append(req["id"])
                except (json.JSONDecodeError, KeyError):
                    pass

        mock_proc.stdin.write.side_effect = capture_write

        def smart_readline():
            """根据已捕获的 id 返回对应 result"""
            if not written_ids:
                return ""
            req_id = written_ids.pop(0)
            try:
                result = next(result_iter)
            except StopIteration:
                return ""
            if result is None:
                return ""  # 模拟进程退出
            resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
            return json.dumps(resp) + "\n"

        mock_proc.stdout = MagicMock()
        # 兼容 select.select: 需要 fileno() 返回整数
        mock_proc.stdout.fileno.return_value = 100 # Dummy fd
        mock_proc.stdout.readline.side_effect = lambda: smart_readline()
        return mock_proc

    @patch("select.select")
    @patch("tools.mcp_client.subprocess.Popen")
    def test_initialization_sends_handshake(self, mock_popen, mock_select):
        """验证创建客户端时会发送 initialize 握手请求"""
        mock_select.return_value = ([MagicMock(fileno=lambda: 100)], [], [])
        mock_proc = self._make_smart_mock_process([{"protocolVersion": "2024-11-05"}])
        mock_popen.return_value = mock_proc

        from tools.mcp_client import StdioMCPClient
        client = StdioMCPClient(name="test", command=["echo", "mock"])

        mock_popen.assert_called_once()
        mock_proc.stdin.write.assert_called()
        written_calls = [c.args[0] for c in mock_proc.stdin.write.call_args_list]
        all_written = "".join(written_calls)
        first_json_line = all_written.strip().split("\n")[0]
        payload = json.loads(first_json_line)
        assert payload["method"] == "initialize"

    @patch("select.select")
    @patch("tools.mcp_client.subprocess.Popen")
    def test_list_tools_parses_response(self, mock_popen, mock_select):
        """验证 list_tools() 正确解析 JSON-RPC 工具列表响应"""
        mock_select.return_value = ([MagicMock()], [], [])
        tools_result = {
            "tools": [
                {"name": "read_file", "description": "Reads a file", "inputSchema": {"type": "object"}}
            ]
        }
        # result_sequence[0]: handshake, result_sequence[1]: tools/list
        mock_proc = self._make_smart_mock_process([{}, tools_result])
        mock_popen.return_value = mock_proc

        from tools.mcp_client import StdioMCPClient
        client = StdioMCPClient(name="test", command=["echo"])
        tools = client.list_tools()

        assert len(tools) == 1
        assert tools[0]["name"] == "read_file"

    @patch("select.select")
    @patch("tools.mcp_client.subprocess.Popen")
    def test_call_tool_extracts_content_text(self, mock_popen, mock_select):
        """验证 call_tool() 正确提取 content block 中的文本"""
        mock_select.return_value = ([MagicMock()], [], [])
        call_result = {
            "content": [
                {"type": "text", "text": "Hello from MCP!"},
                {"type": "text", "text": "Second block."}
            ]
        }
        mock_proc = self._make_smart_mock_process([{}, call_result])
        mock_popen.return_value = mock_proc

        from tools.mcp_client import StdioMCPClient
        client = StdioMCPClient(name="test", command=["echo"])
        result = client.call_tool("read_file", {"path": "/tmp/hello.txt"})

        assert "Hello from MCP!" in result
        assert "Second block." in result

    @patch("select.select")
    @patch("tools.mcp_client.subprocess.Popen")
    def test_call_tool_on_failure_returns_error_string(self, mock_popen, mock_select):
        """验证当子进程意外退出时，call_tool 返回错误字符串而非抛出异常"""
        mock_select.return_value = ([MagicMock()], [], [])
        # result_sequence[0]: handshake ok, result_sequence[1]: None = 进程退出
        mock_proc = self._make_smart_mock_process([{}, None])
        mock_popen.return_value = mock_proc

        from tools.mcp_client import StdioMCPClient
        client = StdioMCPClient(name="test", command=["echo"])
        result = client.call_tool("some_tool", {})

        assert "Error" in result or "failed" in result.lower()

    @patch("select.select")
    @patch("tools.mcp_client.subprocess.Popen")
    def test_close_terminates_process(self, mock_popen, mock_select):
        """验证 close() 方法会终止子进程"""
        mock_select.return_value = ([MagicMock(fileno=lambda: 100)], [], [])
        mock_proc = self._make_smart_mock_process([{}])
        mock_popen.return_value = mock_proc

        from tools.mcp_client import StdioMCPClient
        client = StdioMCPClient(name="test", command=["echo"])
        client.close()

        mock_proc.terminate.assert_called_once()


class TestCreateMCPClient:
    """测试工厂函数 create_mcp_client()"""

    @patch("select.select")
    @patch("tools.mcp_client.subprocess.Popen")
    def test_creates_stdio_client(self, mock_popen, mock_select):
        """验证 transport=stdio 创建 StdioMCPClient"""
        mock_select.return_value = ([MagicMock(fileno=lambda: 100)], [], [])
        mock_proc = MagicMock()
        mock_proc.pid = 1
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdin.flush = MagicMock()
        # 智能响应：每次读取都返回与写入 id 匹配的响应
        written_ids = []

        def cap_write(data):
            for line in data.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                    if "id" in req:
                        written_ids.append(req["id"])
                except Exception:
                    pass

        mock_proc.stdin.write.side_effect = cap_write
        result_seq = iter([{}])

        def smart_read():
            if not written_ids:
                return ""
            rid = written_ids.pop(0)
            try:
                r = next(result_seq)
            except StopIteration:
                return ""
            return json.dumps({"jsonrpc": "2.0", "id": rid, "result": r}) + "\n"

        mock_proc.stdout = MagicMock()
        mock_proc.stdout.readline.side_effect = lambda: smart_read()
        mock_popen.return_value = mock_proc

        from tools.mcp_client import create_mcp_client, StdioMCPClient
        client = create_mcp_client("fs", {"transport": "stdio", "command": ["echo"]})
        assert isinstance(client, StdioMCPClient)

    def test_unknown_transport_raises_error(self):
        """验证未知 transport 类型抛出 ValueError"""
        from tools.mcp_client import create_mcp_client
        with pytest.raises(ValueError, match="Unknown MCP transport"):
            create_mcp_client("bad", {"transport": "grpc"})

    def test_missing_command_raises_error(self):
        """验证 stdio 缺少 command 参数抛出 ValueError"""
        from tools.mcp_client import create_mcp_client
        with pytest.raises(ValueError, match="requires 'command'"):
            create_mcp_client("fs", {"transport": "stdio"})


class TestMCPRegistry:
    """测试 MCPRegistry 的配置读取和工具发现"""

    def setup_method(self):
        """重置 MCPRegistry 单例状态（保证测试间隔离）"""
        from tools.mcp_registry import MCPRegistry
        # 彻底清除单例状态
        MCPRegistry._instance = None
        # 重新实例化会走 __new__ 并得到一个新的净空实例（如果实现支持或手动清空）
        self.registry = MCPRegistry()
        self.registry._mcp_clients.clear()
        self.registry._mcp_schemas.clear()
        self.registry._initialized = False
        import tools.mcp_registry as mreg
        mreg._tool_to_server.clear()

    def test_no_mcp_config_loads_nothing(self):
        """验证没有 MCP 配置时，初始化后工具列表为空"""
        import os
        os.environ.pop("MCP_SERVERS", None)

        with patch("tools.mcp_registry.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            self.registry.initialize()
            assert self.registry.get_mcp_tools_schema() == []
            assert self.registry.get_mcp_handlers() == {}

    @patch("tools.mcp_registry.create_mcp_client")
    def test_env_var_connects_servers(self, mock_create):
        """验证 MCP_SERVERS 环境变量中的服务器会被连接"""
        import os
        mock_client = MagicMock()
        mock_client.list_tools.return_value = [
            {"name": "read", "description": "Read file", "inputSchema": {"type": "object"}}
        ]
        mock_create.return_value = mock_client

        os.environ["MCP_SERVERS"] = json.dumps([
            {"name": "testfs", "transport": "stdio", "command": ["echo"]}
        ])

        try:
            self.registry.initialize()
            schemas = self.registry.get_mcp_tools_schema()
            assert len(schemas) == 1
            assert schemas[0]["name"] == "mcp__testfs__read"
            assert "[MCP:testfs]" in schemas[0]["description"]
        finally:
            os.environ.pop("MCP_SERVERS", None)

    @patch("tools.mcp_registry.create_mcp_client")
    def test_handlers_route_to_correct_client(self, mock_create):
        """验证 Handler 会将调用路由到正确的 MCP 客户端"""
        import os
        mock_client = MagicMock()
        mock_client.list_tools.return_value = [
            {"name": "greet", "description": "Says hello", "inputSchema": {"type": "object"}}
        ]
        mock_client.call_tool.return_value = "Hello, World!"
        mock_create.return_value = mock_client

        os.environ["MCP_SERVERS"] = json.dumps([
            {"name": "greeter", "transport": "stdio", "command": ["echo"]}
        ])

        try:
            self.registry.initialize()
            handlers = self.registry.get_mcp_handlers()
            result = handlers["mcp__greeter__greet"](name="World")
            mock_client.call_tool.assert_called_once_with("greet", {"name": "World"})
            assert result == "Hello, World!"
        finally:
            os.environ.pop("MCP_SERVERS", None)
