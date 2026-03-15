# Production Agent (生产级自主推理智能体)

这是一个高度模块化、具备生产环境高可用特性的 Autonomous Software Engineer Agent（自主软件工程师智能体）。它不仅是一个强大的代码生成与修改工具，更是作为一套**学习和研究现代 AI Agent 架构体系**的优秀教学级脚手架。整个项目的类和方法均包含了详尽的中文设计意图（Docstrings），深入浅出地拆解了 Agent 框架背后的核心实现逻辑。

---

## 📚 开发者指南 (Developer Guides)

我们为开发者准备了详尽的内部技术文档，旨在帮助你快速理解架构、调试代码并扩展 Agent 的能力：

👉 **[点击进入：开发者文档中心 (Docs Index)](./docs/README.md)**

---

## 🌟 为什么选择这个项目？ (Why This Project?)

对于开发者来说，这不仅仅是一个 Agent 演示，更是一个**生产级 AI 工程实践的教学范式**：
- **从传统 Loop 到图拓扑**：展示如何从繁琐的 `while True` 循环迁移到可预测、可观察的 LangGraph 状态机。
- **模块化设计**：工具发现 (MCP)、长短期记忆 (SQLite Persistence)、财务统计 (Cost Counter) 全部解耦成独立包。
- **真实生产环境考量**：内置 Docker 沙盒、安全审批钩子 (HITL) 和全量日志追踪。

---

## 🏗️ 核心技术栈 (Modern AI Stack)

本项目依托现代 AI 开发标准构建，是深入掌握以下技术的绝佳起点：

- **LangChain 1.0**: 统一的 LLM 抽象层，集成了丰富的工具库与内存模型。
- **LangGraph Swarm**: 使用 `StateGraph` 实现多角色编排。**PM -> Architect -> Coder -> QA** 的流转不再是硬编码，而是图计算。
- **Model Context Protocol (MCP)**: 革命性的能力发现协议。Agent 可以在运行时动态“学会”使用本地数据库或外部 API。
- **SQLite 异步持久化**: 集成 `AsyncSqliteSaver`，支持对话状态的长效保存与故障恢复，即刻拥有 production-ready 的记忆力。
- **精细化安全审核 (HITL)**: 自研工具拦截逻辑，自动通过低风险操作，强制拦截高危执行（如 Bash 写入）。

---

## 🎓 学习与实战 (For Beginners)

如果你是 AI 开发初学者，我们为你准备了循序渐进的实验室指南：

👉 **[点击开始：AI Beginner Lab 动手实验室](./docs/ai_beginner_lab.md)**

了解更多核心设计：
- [多智能体 Swarm 编排协议](./docs/swarm_topology.md)
- [状态管理与 SQLite 持久化](./docs/database_schema.md)
- [工具发现与 MCP 协议](./docs/mcp_development.md)

---

## ⚙️ 环境要求与配置 (Configuration)

### 1. 基础要求
- Python 3.10+
- （可选）Docker Desktop：仅用于启用原生沙盒环境 `sandbox_bash` 功能。

### 2. 安装依赖库
```bash
# 安装核心依赖
pip install langchain langchain-anthropic langgraph langgraph-checkpoint-sqlite aiosqlite python-dotenv rich nest_asyncio

# 安装进阶感知功能（推荐）
pip install playwright pyautogui mss beautifulsoup4 duckduckgo-search docker chromadb sentence-transformers
```
*(注：架构内部存在平滑降级机制，若未安装某项进阶库，相关的 Tool 会返回友好的警报让 Agent 指导您后续安装，**而不会让整个程序 Crash 罢工**。)*

### 3. 设置环境变量
项目根目录下创建一个 `.env` 文件，填入你的大模型凭据：
```env
# 核心通信密钥（必填）
ANTHROPIC_AUTH_TOKEN=your_claude_api_key_here

# 兼容第三方中转网关（可选）
ANTHROPIC_BASE_URL=https://api.anthropic.com

# 指定调用的模型版本（默认：claude-3-5-sonnet-20241022）
MODEL_ID=claude-3-5-sonnet-20241022
```

---

## 🚀 启动与使用 (Usage)

请在你的工程根目录执行以下命令，唤起 REPL（Read-Eval-Print-Loop）命令交互面板：

### 1. 终端模式 (CLI Mode)
```bash
python -m production_agent.main
```

### 2. 网页管理模式 (Web UI Mode)
```bash
streamlit run production_agent/streamlit_app.py
```

### 终端内连指令 (Built-in Commands)
除了用自然语言对 Agent 下达例如 *“帮我用 React 写一个看板应用”* 或 *“查找一下目前代码里哪些地方涉及到了 login 函数，帮我加一下异常拦截日志”* 等指令外，你还能使用以下系统级热键：

- **`/cost`** —— 💳 打印目前的财务监控报表，查看在这台电脑上累计跑了多少 Input/Output Token，以及折合消耗了多少美元。
- **`/compact`** —— 🗜️ 告一段落后手动触发压缩机制。系统会将上文几千轮的历史扔给模型总结出一份几百字的摘要以重置 Context，极大降低你后续每一句话的请求延迟与金钱成本。
- **`/clear`** —— 🗑️ 抹除 `default_modular` Session 的脑容量，彻底开始崭新的工作。
- **`q` 或 `exit`** —— 🛑 安全中止运行，并落盘所有的对话状态，供下次执行断点续传。

---

## 📝 更新日志 (Changelog)

### [2026-03-15] - Phase 5 Observability & Web UI
- **[新内核能力]**: `SwarmOrchestrator` 支持实时事件回调 (Callback Mechanism)，解耦引擎与 UI 展现。
- **[链路追踪]**: 集成 LangSmith 探针，由底层 `core/llm.py` 自动捕捉所有推理链路与 Token 成本。
- **[可视化前台]**: 新增基于 Streamlit 的 Web 用户界面 (`streamlit_app.py`)，支持实时观察多智能体节点流转。
- **[文档补全]**: 新增可观测性与 Web UI 专用技术指南。

---

### 💡 Phase 6: 企业级扩展
- **多租户权限控制 (RBAC)**: 为不同用户分配不同的工具执行权限与 API 配额。
- **分布式 Agent 节点**: 支持将子 Agent 调度到不同的远程算力节点执行高并发任务。

### 📊 Phase 5: 进阶可观察性 (Completed) ✅
- **自定义看板**: 未来将引入更多业务维度的监控（如子任务成功率分布）。
