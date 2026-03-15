"""
MCP 动态工具注册引擎 (MCP Dynamic Tool Registry)

【设计意图】
读取 `MCP_SERVERS` 环境变量（JSON 数组），自动连接并发现所有 MCP 服务的工具，
然后将它们转换为 Anthropic Tool Schema 格式并合并进全局工具集。

工作流程：
    1. 解析 MCP_SERVERS 配置（支持 stdio 和 SSE 两种传输）
    2. 对每个 MCP 服务调用 list_tools() 获取工具清单
    3. 将 inputSchema 字段转换为 Anthropic 格式的 input_schema
    4. 注册对应 handler：当 LLM 调用该工具时，路由到正确的 MCP 客户端

MCP_SERVERS 环境变量格式示例：
    [
        {
            "name": "filesystem",
            "transport": "stdio",
            "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        },
        {
            "name": "remote_db",
            "transport": "sse",
            "url": "http://localhost:3001/sse"
        }
    ]
"""

import json
import logging
import os
import threading
from typing import Callable, Optional

from tools.mcp_client import MCPClientBase, create_mcp_client

logger = logging.getLogger(__name__)

# 全局：工具名 -> MCP 服务名 的路由表（用于 handler 分发）
_tool_to_server: dict[str, str] = {}


def _load_mcp_servers() -> list[dict]:
    """
    从 MCP_SERVERS 环境变量加载 MCP 服务配置列表。
    若未配置则返回空列表（静默降级，不影响 Agent 正常运行）。
    """
    raw = os.getenv("MCP_SERVERS", "").strip()
    if not raw:
        return []
    try:
        servers = json.loads(raw)
        if not isinstance(servers, list):
            logger.warning("[MCPRegistry] MCP_SERVERS 应为 JSON 数组，已忽略")
            return []
        return servers
    except json.JSONDecodeError as e:
        logger.error(f"[MCPRegistry] 解析 MCP_SERVERS 失败: {e}")
        return []


def _anthropic_schema(mcp_tool: dict) -> dict:
    """
    将 MCP 的工具定义转换为 Anthropic Tool Schema 格式。

    MCP 格式：
        {"name": "read_file", "description": "...", "inputSchema": {"type": "object", ...}}

    Anthropic 格式：
        {"name": "read_file", "description": "...", "input_schema": {"type": "object", ...}}
    """
    return {
        "name": mcp_tool["name"],
        "description": mcp_tool.get("description", ""),
        # MCP 用 inputSchema，Anthropic 用 input_schema（下划线风格）
        "input_schema": mcp_tool.get("inputSchema", {"type": "object", "properties": {}, "required": []}),
    }


class MCPRegistry:
    """
    MCP 工具注册中心（单例模式）。

    由 ToolRegistry 在初始化阶段调用，完成：
    - 连接所有 MCP 服务
    - 发现并注册工具 Schema
    - 构建 Handler 映射表

    之后 ToolRegistry 通过 get_mcp_tools_schema() 和 get_mcp_handlers()
    将 MCP 工具无缝并入原有的工具集，对 LLM 透明。
    """

    _instance: Optional["MCPRegistry"] = None
    _mcp_clients: dict[str, MCPClientBase] = {}
    _mcp_schemas: list[dict] = []
    _initialized: bool = False
    _init_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> "MCPRegistry":
        """
        连接所有已配置的 MCP 服务，并收集工具定义（采用线程池并行提速）。
        """
        with self._init_lock:
            if self._initialized:
                return self

            configs = _load_mcp_servers()
            if not configs:
                logger.info("[MCPRegistry] No MCP_SERVERS configured.")
                self._initialized = True
                return self

            from concurrent.futures import ThreadPoolExecutor, as_completed

            def _connect_single_server(cfg):
                server_name = cfg.get("name", "unnamed")
                try:
                    client = create_mcp_client(name=server_name, config=cfg)
                    raw_tools = client.list_tools()
                    return server_name, client, raw_tools, None
                except Exception as e:
                    return server_name, None, [], e

            # 限制最大线程数为 10，避免过多进程爆炸
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_server = {executor.submit(_connect_single_server, cfg): cfg for cfg in configs}
                
                for future in as_completed(future_to_server):
                    sname, client, rtools, err = future.result()
                    if err:
                        logger.error(f"[MCPRegistry] Failed to connect '{sname}': {err}")
                        print(f"\033[33m[MCPRegistry] Warning: '{sname}' unavailable — {err}\033[0m")
                        continue

                    # 注册到实例缓存
                    self._mcp_clients[sname] = client
                    for raw_tool in rtools:
                        schema = _anthropic_schema(raw_tool)
                        qualified_name = f"mcp__{sname}__{raw_tool['name']}"
                        schema["name"] = qualified_name
                        schema["description"] = f"[MCP:{sname}] {schema['description']}"
                        self._mcp_schemas.append(schema)
                        _tool_to_server[qualified_name] = sname

                    logger.info(f"[MCPRegistry] Connected: '{sname}' ({len(rtools)} tools)")
                    print(f"\033[32m[MCPRegistry] Connected '{sname}': {len(rtools)} tool(s) loaded\033[0m")

            self._initialized = True
        return self

    # ──────────────────────────────────────────────
    # 对外接口（供 ToolRegistry 调用）
    # ──────────────────────────────────────────────

    def get_mcp_tools_schema(self) -> list[dict]:
        """返回所有 MCP 工具的 Anthropic Schema 列表（可能为空列表）。"""
        return list(self._mcp_schemas)

    def get_mcp_handlers(self) -> dict[str, Callable]:
        """
        返回所有 MCP 工具的 Handler 映射表。
        key = 工具名（qualified_name），value = callable(**kwargs) -> str
        """
        handlers = {}
        for qualified_name, server_name in _tool_to_server.items():
            client = self._mcp_clients.get(server_name)
            if client is None:
                continue
            # 恢复原始工具名（去掉 mcp__serverName__ 前缀）
            prefix = f"mcp__{server_name}__"
            original_name = qualified_name.removeprefix(prefix)

            # 闭包捕获变量（注意 Python 闭包的晚绑定陷阱，用默认参数固定）
            def _make_handler(c: MCPClientBase, tname: str) -> Callable:
                return lambda **kwargs: c.call_tool(tname, kwargs)

            handlers[qualified_name] = _make_handler(client, original_name)

        return handlers

    def shutdown(self):
        """优雅关闭所有 MCP 客户端（在 Agent 退出时调用）"""
        for name, client in self._mcp_clients.items():
            try:
                client.close()
                logger.info(f"[MCPRegistry] Closed '{name}'")
            except Exception as e:
                logger.warning(f"[MCPRegistry] Error closing '{name}': {e}")
        self._mcp_clients.clear()
        _tool_to_server.clear()
        self._mcp_schemas.clear()
        self._initialized = False


# 全局单例访问点
mcp_registry = MCPRegistry()
