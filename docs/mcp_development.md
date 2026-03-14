# MCP (Model Context Protocol) 深度开发指南

### 什么是 MCP？

**Model Context Protocol (MCP)** 是一种开放标准的 JSON-RPC 协议，旨在为大语言模型（LLM）提供一个安全、标准化的接口来访问物理世界中的工具和数据。

在本项目中，MCP 充当了“智能体插件系统”的角色。通过 MCP，你可以无需修改智能体核心代码，即可通过配置文件动态注入新的能力。

---

## 🔬 协议层解析：JSON-RPC 2.0 握手流

本项目实现了 MCP 基于 **Stdio (标准输入输出)** 的传输方式。以下是 `StdioMCPClient` 启动时的核心握手过程：

1.  **Initialize (初始化请求)**：客户端发送协议版本、功能声明（Capabilities）和客户端信息。
2.  **Initialized (确认)**：客户端发送一个通知（Notification）确认初始化完成。
3.  **Tool Discovery (工具发现)**：通过调用 `list_tools` 方法获取服务器端暴露的所有方法及其 JSON Schema。

---

## 🏗 本项目的高性能 I/O 设计

在处理 Stdio 进程通信时，最常见的陷阱是**管道阻塞**和**同步卡死**。我们在 `tools/mcp_client.py` 中实现了工程级的防御性设计：

### 1. 异步错误流清理 (Stderr Draining)
许多 MCP 服务器会通过 `stderr` 输出 debug 日志。如果主进程不持续读取并清空 `stderr` 的缓冲区，一旦达到系统限制（通常 64KB），子进程就会因为无法继续写入而陷入死锁。
-   **实现**：我们使用独立的后台 `Daemon Thread` 实时监听并消耗 `stderr`，确保主线程永远不因辅助流阻塞。

### 2. 非阻塞超时读取 (Select-based Read)
为了防止某个 MCP 服务器响应过慢导致整个智能体 UI 假死，我们引入了 `select.select` 机制：
-   **原理**：在读取 `stdout` 之前，先利用系统调用检查管道是否有数据。
-   **效果**：实现了真正的“硬超时”。即使服务器无响应，主进程也会根据配置的 `timeout`（默认 30s）抛出 `TimeoutError` 并优雅降级回执，而不是永久等待。

---

## 🛠 开发实战：接入自定义 MCP 服务器

### 配置环境变量
在 `.env` 中修改 `MCP_SERVERS` 字段。这是一个 JSON 数组：

```json
[
  {
    "name": "sqlite_explorer",
    "transport": "stdio",
    "command": ["python", "scripts/mcp_db_server.py", "--db-path", "./data.db"]
  }
]
```

### 工具动态路由
`MCPRegistry` 在初始化时会自动完成以下操作：
1.  **命名空间封装**：将工具名统一映射为 `mcp__[server_name]__[original_tool_name]`（如 `mcp__sqlite_explorer__query`）。
2.  **并行连接**：利用 `ThreadPoolExecutor` 并行启动所有 MCP 服务，显著缩短冷启动时间。
3.  **闭包分发**：利用 Python 偏函数动态生成调用 Handler，对上层 `ToolRegistry` 透明。

---

## 💡 开发者避坑指南

-   **幂等性要求**：MCP 工具本质上是 RPC 调用。建议开发者编写具有幂等性的工具，以便智能体在网络抖动或解析失败时能够安全重试。
-   **Schema 精简**：LLM 对工具描述的敏感度极高。请在服务器端提供简洁且语义准确的 `inputSchema`。
-   **资源生命周期**：确保在应用退出时调用 `mcp_registry.shutdown()`，否则可能会产生子进程僵尸进程。本项目已通过 `main.py` 的 `cleanup` 函数自动处理。

> [!TIP]
> **SSE 传输支持**：如果你的工具运行在云端或 K8s 集群中，可以将 `transport` 设置为 `sse` 并提供 `url`。项目内置的 `SSEMCPClient` 会自动处理 HTTP 事件流。
