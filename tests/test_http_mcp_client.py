"""
HTTP MCP Client 单元测试 (test_http_mcp_client.py)

测试策略：Mock httpx，完全不需要真实 MCP 服务。
"""

import json
import pytest
from unittest.mock import MagicMock, patch, Mock


class TestHttpMCPClient:
    """测试 HttpMCPClient 的 HTTP/JSON-RPC 通信逻辑"""

    def _make_mock_httpx_response(self, mock_data: list) -> Mock:
        """创建 Mock httpx 响应序列"""
        responses = iter(mock_data)

        mock_response = MagicMock()
        mock_response.json.side_effect = lambda: next(responses)
        mock_response.raise_for_status = MagicMock()
        return mock_response

    @patch("httpx.post")
    def test_initialization_sends_handshake(self, mock_post):
        """验证创建客户端时会发送 initialize 握手请求"""
        mock_post.return_value = self._make_mock_httpx_response([
            {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {"tools": {}}}},
        ])

        from tools.mcp_client import HttpMCPClient
        client = HttpMCPClient(name="test_http", url="http://localhost:8000/mcp")

        assert mock_post.call_count >= 2
        init_call = None
        for call in mock_post.call_args_list:
            args, kwargs = call
            json_payload = kwargs.get("json", {})
            if json_payload.get("method") == "initialize":
                init_call = json_payload
                break
        assert init_call is not None, "initialize method not found in calls"
        assert init_call["params"]["protocolVersion"] == "2024-11-05"

    @patch("httpx.post")
    def test_list_tools_parses_response(self, mock_post):
        """验证 list_tools() 正确解析 JSON-RPC 工具列表响应"""
        mock_post.return_value = self._make_mock_httpx_response([
            {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {"tools": {}}}},
            {"jsonrpc": "2.0", "id": 2, "result": {
                "tools": [
                    {"name": "query_db", "description": "Query database", "inputSchema": {"type": "object"}}
                ]
            }},
        ])

        from tools.mcp_client import HttpMCPClient
        client = HttpMCPClient(name="test_http", url="http://localhost:8000/mcp")
        tools = client.list_tools()

        assert len(tools) == 1
        assert tools[0]["name"] == "query_db"

    @patch("httpx.post")
    def test_call_tool_extracts_content_text(self, mock_post):
        """验证 call_tool() 正确提取 content block 中的文本"""
        mock_post.return_value = self._make_mock_httpx_response([
            {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {"tools": {}}}},
            {"jsonrpc": "2.0", "id": 2, "result": {
                "content": [
                    {"type": "text", "text": "Query result: 42 rows"},
                    {"type": "text", "text": "Second block."}
                ]
            }},
        ])

        from tools.mcp_client import HttpMCPClient
        client = HttpMCPClient(name="test_http", url="http://localhost:8000/mcp")
        result = client.call_tool("query_db", {"sql": "SELECT * FROM users"})

        assert "Query result: 42 rows" in result
        assert "Second block." in result

    @patch("httpx.post")
    def test_call_tool_on_error_returns_error_string(self, mock_post):
        """验证当 HTTP 请求失败时，call_tool 返回错误字符串而非抛出异常"""
        mock_post.return_value = self._make_mock_httpx_response([
            {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {"tools": {}}}},
        ])

        from tools.mcp_client import HttpMCPClient
        client = HttpMCPClient(name="test_http", url="http://localhost:8000/mcp")

        mock_post.side_effect = Exception("Connection refused")
        result = client.call_tool("some_tool", {})

        assert "Error" in result or "Connection refused" in result

    @patch("httpx.post")
    def test_close_sets_initialized_false(self, mock_post):
        """验证 close() 方法设置 _initialized 为 False"""
        mock_post.return_value = self._make_mock_httpx_response([
            {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {"tools": {}}}},
        ])

        from tools.mcp_client import HttpMCPClient
        client = HttpMCPClient(name="test_http", url="http://localhost:8000/mcp")
        assert client._initialized is True

        client.close()
        assert client._initialized is False


class TestCreateMCPClientHTTP:
    """测试工厂函数 create_mcp_client() 对 HTTP transport 的支持"""

    @patch("httpx.post")
    def test_creates_http_client(self, mock_post):
        """验证 transport=http 创建 HttpMCPClient"""
        mock_post.return_value = MagicMock()
        mock_post.return_value.json.return_value = {"jsonrpc": "2.0", "id": 1, "result": {"capabilities": {}}}
        mock_post.return_value.raise_for_status = MagicMock()

        from tools.mcp_client import create_mcp_client, HttpMCPClient
        client = create_mcp_client("http_server", {"transport": "http", "url": "http://localhost:8000/mcp"})
        assert isinstance(client, HttpMCPClient)

    def test_missing_url_raises_error(self):
        """验证 http 缺少 url 参数抛出 ValueError"""
        from tools.mcp_client import create_mcp_client
        with pytest.raises(ValueError, match="requires 'url'"):
            create_mcp_client("http_server", {"transport": "http"})

    def test_unknown_transport_raises_error(self):
        """验证未知 transport 类型抛出 ValueError"""
        from tools.mcp_client import create_mcp_client
        with pytest.raises(ValueError, match="Unknown MCP transport"):
            create_mcp_client("bad", {"transport": "websocket"})


class TestMCPRegistryYAML:
    """测试 MCPRegistry 从 YAML 配置加载的能力"""

    def setup_method(self):
        """重置 MCPRegistry 单例状态"""
        from tools.mcp_registry import MCPRegistry
        MCPRegistry._instance = None
        self.registry = MCPRegistry()
        self.registry._mcp_clients.clear()
        self.registry._mcp_schemas.clear()
        self.registry._initialized = False
        import tools.mcp_registry as mreg
        mreg._tool_to_server.clear()

    @patch("tools.mcp_registry.create_mcp_client")
    def test_yaml_config_loads_servers(self, mock_create):
        """验证 config/mcp_servers.yaml 中的服务器会被加载"""
        import os
        mock_client = MagicMock()
        mock_client.list_tools.return_value = [
            {"name": "search", "description": "Search files", "inputSchema": {"type": "object"}}
        ]
        mock_create.return_value = mock_client

        yaml_content = """
mcp_servers:
  - name: yaml_fs
    transport: stdio
    command: ["echo", "test"]
"""
        with patch("tools.mcp_registry.Path") as mock_path:
            mock_path.return_value.parent.__truediv__.return_value.exists.return_value = True
            mock_path.return_value.exists.return_value = True
            mock_path.return_value.read_text.return_value = yaml_content

            os.environ.pop("MCP_SERVERS", None)
            self.registry.initialize()

            if self.registry.get_mcp_tools_schema():
                schemas = self.registry.get_mcp_tools_schema()
                assert len(schemas) == 1
                assert schemas[0]["name"] == "mcp__yaml_fs__search"
