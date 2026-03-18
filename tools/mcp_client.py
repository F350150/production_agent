"""
MCP 客户端传输层 (MCP Client Transport Layer)

【设计意图】
实现 Model Context Protocol (MCP) 的两种传输模式，
使 Agent 可以连接任意外部 MCP 服务并调用其提供的工具：

1. StdioMCPClient  — 启动本地子进程（如 `npx @modelcontextprotocol/server-filesystem`），
   通过标准输入/输出与之通信（JSON-RPC 2.0 over stdio）。
2. SSEMCPClient    — 连接已运行的 HTTP MCP 服务（通过 Server-Sent Events）。

两者均暴露统一接口：
    client.list_tools()           -> list[dict]  # 工具定义列表
    client.call_tool(name, args)  -> str          # 工具执行结果
"""

import json
import logging
import subprocess
import threading
import time
import sys
from abc import ABC, abstractmethod
from typing import Any, Optional
from rich.console import Console

logger = logging.getLogger(__name__)

# JSON-RPC 请求 ID 计数器（线程安全）
_rpc_id_lock = threading.Lock()
_rpc_id_counter = 0


def _next_rpc_id() -> int:
    global _rpc_id_counter
    with _rpc_id_lock:
        _rpc_id_counter += 1
        return _rpc_id_counter


class MCPClientBase(ABC):
    """
    MCP 客户端抽象基类。
    所有传输实现必须继承此类并实现 list_tools / call_tool 方法。
    """

    def __init__(self, name: str):
        self.name = name  # 便于日志定位，如 "filesystem" / "browser"

    @abstractmethod
    def list_tools(self) -> list[dict]:
        """
        向 MCP 服务发起 tools/list 请求。
        返回格式：[{"name": ..., "description": ..., "inputSchema": {...}}, ...]
        """
        raise NotImplementedError

    @abstractmethod
    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        向 MCP 服务发起 tools/call 请求。
        返回工具执行的文本输出（如有多个 content block，拼接为一个字符串）。
        """
        raise NotImplementedError

    def close(self):
        """可选：主动关闭连接（stdio 关闭子进程，SSE 断开 session）"""
        pass


class StdioMCPClient(MCPClientBase):
    """
    stdio 传输的 MCP 客户端。

    典型用法：
        client = StdioMCPClient(
            name="filesystem",
            command=["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        )
        tools = client.list_tools()
        result = client.call_tool("read_file", {"path": "/tmp/hello.txt"})

    【工作原理】
    - 启动子进程，向其 stdin 写入 JSON-RPC 请求，从 stdout 读取响应。
    - 首先发送 initialize 握手，等待服务器返回 capabilities。
    - 每次 IO 都加锁，防止并发 write 乱序。
    """

    def __init__(self, name: str, command: list[str], timeout: int = 30):
        super().__init__(name)
        self.command = command
        self.timeout = timeout
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._initialized = False

        # 启动子进程
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,         # 行缓冲
                encoding="utf-8",
            )
            self._handshake()
            logger.info(f"[MCP-stdio] '{self.name}' started (pid={self._process.pid})")
        except FileNotFoundError as e:
            logger.error(f"[MCP-stdio] Failed to start '{self.name}': {e}")
            raise RuntimeError(f"MCP server '{self.name}' command not found: {command[0]}") from e

    # ──────────────────────────────────────────────
    # 内部 JSON-RPC 通信
    # ──────────────────────────────────────────────

    def _send(self, method: str, params: Optional[dict] = None) -> dict:
        """发送 JSON-RPC 请求并同步等待响应"""
        req_id = _next_rpc_id()
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            payload["params"] = params

        with self._lock:
            if not self._process or self._process.poll() is not None:
                raise ConnectionError(f"MCP '{self.name}' process is not running.")
            
            raw = json.dumps(payload) + "\n"
            self._process.stdin.write(raw)
            self._process.stdin.flush()

            # 阻塞读取下一行（对应该请求的响应）
            import select
            while True:
                deadline = time.time() + self.timeout
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"MCP '{self.name}' response timeout (method={method})")
                
                # 使用 select 检查 stdout 是否有数据可读，避免 readline() 永久阻塞
                r, _, _ = select.select([self._process.stdout], [], [], max(0, remaining))
                if not r:
                    raise TimeoutError(f"MCP '{self.name}' response timeout during select (method={method})")
                
                line = self._process.stdout.readline()
                if not line:
                    exit_code = self._process.poll()
                    raise ConnectionError(f"MCP '{self.name}' connection closed (ExitCode: {exit_code})")
                
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                    if resp.get("id") == req_id:
                        return resp
                    # id 不匹配则忽略（可能是通知消息），继续等待
                except json.JSONDecodeError:
                    logger.debug(f"[MCP-stdio] Non-JSON line: {line[:80]}")

    def _handshake(self):
        """发送 MCP initialize 请求完成握手"""
        # 启动一个后台线程专门消耗 stderr，防止管道撑爆导致进程死锁
        def _drain_stderr(pipe, name):
            try:
                for line in pipe:
                    if line.strip():
                        logger.warning(f"[MCP-stderr:{name}] {line.strip()}")
            except Exception:
                pass

        threading.Thread(target=_drain_stderr, args=(self._process.stderr, self.name), daemon=True).start()

        self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "production_agent", "version": "1.0"}
        })
        # 发送 initialized 通知（无需响应）
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._process.stdin.write(json.dumps(notif) + "\n")
        self._process.stdin.flush()
        self._initialized = True

    # ──────────────────────────────────────────────
    # 公开接口
    # ──────────────────────────────────────────────

    def list_tools(self) -> list[dict]:
        try:
            resp = self._send("tools/list")
            tools = resp.get("result", {}).get("tools", [])
            logger.info(f"[MCP-stdio] '{self.name}' listed {len(tools)} tools")
            return tools
        except Exception as e:
            logger.error(f"[MCP-stdio] list_tools failed for '{self.name}': {e}")
            return []

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        try:
            resp = self._send("tools/call", {"name": tool_name, "arguments": arguments})
            result = resp.get("result", {})
            # MCP 标准：结果在 content 数组中，每个 block 有 type 和 text
            content_blocks = result.get("content", [])
            parts = []
            for block in content_blocks:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("data") or str(block)
                    parts.append(text)
            return "\n".join(parts) if parts else str(result)
        except Exception as e:
            logger.error(f"[MCP-stdio] call_tool '{tool_name}' failed: {e}")
            return f"Error calling MCP tool '{tool_name}': {e}"

    def close(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            logger.info(f"[MCP-stdio] '{self.name}' process terminated")


class SSEMCPClient(MCPClientBase):
    """
    SSE (Server-Sent Events) 传输的 MCP 客户端。

    典型用法：
        client = SSEMCPClient(name="remote", url="http://localhost:3000/sse")
        tools = client.list_tools()
        result = client.call_tool("query_db", {"sql": "SELECT 1"})

    【依赖】：需要 httpx 库，已在大多数 Python 环境中可用。
    """

    def __init__(self, name: str, url: str, timeout: int = 30):
        super().__init__(name)
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._session_id: Optional[str] = None
        self._messages_url: Optional[str] = None
        self._connect()

    def _connect(self):
        """建立 SSE 连接，获取 session_id 和 messages endpoint"""
        try:
            import httpx
            # 读取初始 SSE 事件获取 endpoint
            with httpx.Client(timeout=self.timeout) as client:
                with client.stream("GET", self.url) as resp:
                    for line in resp.iter_lines():
                        if line.startswith("data:"):
                            data = json.loads(line[5:].strip())
                            self._messages_url = data.get("endpoint", f"{self.url}/messages")
                            break
            logger.info(f"[MCP-SSE] '{self.name}' connected: {self._messages_url}")
        except ImportError:
            raise RuntimeError("SSE MCP client requires 'httpx'. Run: pip install httpx")
        except Exception as e:
            logger.error(f"[MCP-SSE] Connection failed for '{self.name}': {e}")
            raise

    def _rpc(self, method: str, params: Optional[dict] = None) -> dict:
        """通过 POST 发送 JSON-RPC 请求到 MCP messages endpoint"""
        import httpx
        req_id = _next_rpc_id()
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            payload["params"] = params
        resp = httpx.post(self._messages_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def list_tools(self) -> list[dict]:
        try:
            resp = self._rpc("tools/list")
            tools = resp.get("result", {}).get("tools", [])
            logger.info(f"[MCP-SSE] '{self.name}' listed {len(tools)} tools")
            return tools
        except Exception as e:
            logger.error(f"[MCP-SSE] list_tools failed: {e}")
            return []

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        try:
            resp = self._rpc("tools/call", {"name": tool_name, "arguments": arguments})
            result = resp.get("result", {})
            content_blocks = result.get("content", [])
            parts = [b.get("text", str(b)) for b in content_blocks if isinstance(b, dict)]
            return "\n".join(parts) if parts else str(result)
        except Exception as e:
            logger.error(f"[MCP-SSE] call_tool '{tool_name}' failed: {e}")
            return f"Error calling MCP tool '{tool_name}': {e}"


class HttpMCPClient(MCPClientBase):
    """
    HTTP/JSON-RPC 传输的 MCP 客户端（用于连接 FastMCP 服务）。

    典型用法：
        client = HttpMCPClient(name="fastapi", url="http://localhost:8000/mcp")
        tools = client.list_tools()
        result = client.call_tool("query_db", {"sql": "SELECT 1"})

    【依赖】：需要 httpx 库。
    【特点】：与 FastMCP 兼容，支持同步 HTTP/JSON-RPC 调用。
    """

    def __init__(self, name: str, url: str, timeout: int = 30):
        super().__init__(name)
        base_url = url.rstrip("/")
        if not base_url.endswith("/mcp"):
            base_url += "/mcp"
        self.url = base_url
        self.timeout = timeout
        self._initialized = False
        self._capabilities: dict = {}
        self._connect()

    def _connect(self):
        import httpx
        try:
            resp = httpx.post(
                self.url,
                json={
                    "jsonrpc": "2.0",
                    "id": _next_rpc_id(),
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "clientInfo": {"name": "production_agent", "version": "1.0"}
                    }
                },
                timeout=self.timeout
            )
            resp.raise_for_status()
            result = resp.json()
            self._capabilities = result.get("capabilities", {})
            self._initialized = True
            httpx.post(
                self.url,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                timeout=5
            )
            logger.info(f"[MCP-HTTP] '{self.name}' initialized (capabilities: {self._capabilities})")
        except ImportError:
            raise RuntimeError("HTTP MCP client requires 'httpx'. Run: pip install httpx")
        except Exception as e:
            logger.error(f"[MCP-HTTP] Handshake failed for '{self.name}': {e}")
            raise RuntimeError(f"MCP-HTTP connection to '{self.name}' failed: {e}") from e

    def _rpc(self, method: str, params: Optional[dict] = None) -> dict:
        import httpx
        req_id = _next_rpc_id()
        payload: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            payload["params"] = params
        resp = httpx.post(self.url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def list_tools(self) -> list[dict]:
        try:
            resp = self._rpc("tools/list")
            tools = resp.get("result", {}).get("tools", [])
            logger.info(f"[MCP-HTTP] '{self.name}' listed {len(tools)} tools")
            return tools
        except Exception as e:
            logger.error(f"[MCP-HTTP] list_tools failed for '{self.name}': {e}")
            return []

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        try:
            resp = self._rpc("tools/call", {"name": tool_name, "arguments": arguments})
            result = resp.get("result", {})
            content_blocks = result.get("content", [])
            parts = []
            for block in content_blocks:
                if isinstance(block, dict):
                    text = block.get("text") or block.get("data") or str(block)
                    parts.append(text)
            return "\n".join(parts) if parts else str(result)
        except Exception as e:
            logger.error(f"[MCP-HTTP] call_tool '{tool_name}' failed: {e}")
            return f"Error calling MCP tool '{tool_name}': {e}"

    def close(self):
        self._initialized = False
        logger.info(f"[MCP-HTTP] '{self.name}' connection closed")


def create_mcp_client(name: str, config: dict) -> MCPClientBase:
    """
    工厂函数：根据配置字典创建对应的 MCP 客户端。

    config 示例（stdio）:
        {"transport": "stdio", "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]}

    config 示例（SSE）:
        {"transport": "sse", "url": "http://localhost:3001/sse"}

    config 示例（HTTP/FastMCP）:
        {"transport": "http", "url": "http://localhost:8000/mcp"}
    """
    transport = config.get("transport", "stdio").lower()
    if transport == "stdio":
        command = config.get("command")
        if not command:
            raise ValueError(f"MCP server '{name}' with stdio transport requires 'command'")
        return StdioMCPClient(name=name, command=command)
    elif transport == "sse":
        url = config.get("url")
        if not url:
            raise ValueError(f"MCP server '{name}' with sse transport requires 'url'")
        return SSEMCPClient(name=name, url=url)
    elif transport == "http":
        url = config.get("url")
        if not url:
            raise ValueError(f"MCP server '{name}' with http transport requires 'url'")
        return HttpMCPClient(name=name, url=url)
    else:
        raise ValueError(f"Unknown MCP transport: '{transport}'. Supported: stdio, sse, http")
