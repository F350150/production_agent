# Model Context Protocol (MCP) 标准剖析与高级应用

## 1. 为什么我们需要 MCP 协议？
以前，在让 LLM 访问各种内部系统（Jira, 数据库, Redis, S3）时，我们总要为主 Agent 开发大量具体的 Python 代码和 HTTP Client，使得 Agent 成为巨大的单体巨兽 (Monolith)。
Anthropic 联手重磅推出的 **Model Context Protocol (MCP)** 试图统一这一混乱局面，旨在像 **USB-C 接口**一样标准化：
- **一端连通 AI Agent 侧 (Client)**
- **一端连通企业数据与能力源侧 (Server)**
实现了“任何懂 MCP 客户端的大模型”都可以“即插即用，零开发接入全球海量后端系统”。

## 2. 协议架构深度解构
MCP 是基于 **JSON-RPC 2.0** 异步双向通信模型设计的，涵盖三大核心源泉：

### 2.1 资源 (Resources)
- **概念**：被动的数据输送管（例如：阅读特定的 GitHub 代码库树、拉取公司内部 Wiki 知识）。
- **特点**：URI 寻址。MCP Server 控制什么资源可以被探测和传输。客户端通过 `resources/list` 发起查询探测。

### 2.2 提示模板 (Prompts)
- **概念**：预制好的参数化提示词模板（即远端的 Skill）。
- **特点**：大模型可以通过 `prompts/get` 从后端拉取经过复杂打磨并填入占位符的 System Prompt，减轻客户端管理负担。

### 2.3 工具 (Tools)
- **概念**：主动让外界执行操作并产生物理状态改变的抓手。
- **交互流程**：Server 将自己具备的手册暴露给 Client 模型（带着 JSON Schema）。模型决策后发起 `tools/call` 的 JSON-RPC 请求；Server 收到后真实验证权限再执行，最终向模型流出执行结果。

## 3. 传输层双雄：Stdio 与 HTTP (SSE + POST)
### 3.1 Stdio Transport (标准输入输出管道)
- **场景**：完全可信的本地环境。
- **机制**：由主 Agent 负责通过类似于 `spawn('npx', ...)` 的方式拉起子进程守护，然后父子进程通过操作系统的 `stdin/stdout` 信道通过换行符 `\n` 切断 JSON 数据包互通有无。极度轻量，没有端口冲突。
  
### 3.2 HTTP with SSE Transport
- **场景**：跨设备、公有云暴露服务、微服务架构下。
- **机制**：
  - **下行通道**：Server 到 Client 通过 SSE (Server-Sent Events) 长连接推送。
  - **上行通道**：Client 到 Server 通过普通的 HTTP POST 到一个指定的 endpoint 来执行请求。

## 4. MCP 的微服务与安全治理 (Security & Governance)
随着全公司各个模块全上 MCP，安全隐患剧增：如何避免模型通过 MCP 工具调用 `Drop Database`？
- MCP Server 并不信任发来请求的模型，其内部应该带有强大的 RBAC (基于角色的权限控制) 中间件。
- 对于 `tools/call` 这个操作，必须要求在请求 `metadata` 内附带 JWT 或 API Token。

## 5. 挑战任务与进阶路线图 (Your Roadmap)
- **阶段 1：理解规范源码**。深入阅读 `@modelcontextprotocol/sdk` (Node) 或 Python `mcp` 官方 SDK 中对 `JSONRPCMessage` `Request` `Notification` 的 Pydantic/Zod 封装定义。
- **阶段 2：开发 FastMCP 服务器**。用 Python 圈最火的 FastMCP，自己手写一个能将本机的 SQLite DB 所有表暴露成为 `Resources` 供大模型理解的 MCP 服务暴露器。
- **阶段 3：MCP 反向代理网关**。写一个 MCP Gateway (类似于 Nginx)，当 Agent 的所有请求打上来时，你通过这个 Gateway 去鉴权审查，再把它分别路由转发到背后的 N 个不同语言写的微型 MCP server。探索一下负载均衡怎么设计。
