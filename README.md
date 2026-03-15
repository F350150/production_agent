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
- **LangGraph Swarm**: 使用 `StateGraph` 实现多角色编排。支持 `summarizer` 节点自动压缩上下文，显著降低 Token 成本。
- **自主错误修复 (Self-Healing)**: 内置 `diagnoser` 诊断节点。当工具执行报错时，Agent 会利用 LLM 自动分析错误原因并输出补救指令（如自动安装缺失依赖），实现故障自愈。
- **稳健工具治理 (Tool Resilience)**: 针对生产环境设计的工具容灾机制。即使 Docker 沙盒未启动，系统也能平滑回退到本地执行并给出警报，确保核心流程不中断。
- **关系感知 RAG (Graph RAG)**: 结合 Tree-sitter 语法树解析，在向量搜索基础上增加了类继承关系权重。
- **LoRA 微调基础设施**: 内置轨迹收集器（Trajectory Collector），自动记录高质量对话并一键导出为 Alpaca 格式。支持通过 Unsloth 快速训练本地专家模型。
- **SQLite 异步持久化**: 集成 `AsyncSqliteSaver`，支持会话状态的断点续传。

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
- （推荐）Docker Desktop：用于启用原生沙盒环境 `sandbox_bash` 功能。

### 2. 安装依赖库
```bash
# 安装核心依赖
pip install langchain langchain-anthropic langgraph langgraph-checkpoint-sqlite aiosqlite python-dotenv rich nest_asyncio

# 安装进阶感知功能（推荐）
pip install playwright pyautogui mss beautifulsoup4 duckduckgo-search docker chromadb sentence-transformers tree-sitter
```
*(注：架构内部存在平滑降级机制。如果 Docker 未开启或某项依赖缺失，系统会优先尝试本地兜底或提示安装，**而不会让整个程序直接崩溃**。)*

### 3. 设置环境变量
项目根目录下创建一个 `.env` 文件，填入你的大模型凭据：
```env
# 核心通信密钥（必填）
ANTHROPIC_AUTH_TOKEN=your_claude_api_key_here

# 指定调用的模型版本（默认：claude-3-5-sonnet-20241022）
MODEL_ID=claude-3-5-sonnet-20241022
```

---

## 🚀 启动与使用 (Usage)

请在你的工程根目录执行以下命令，唤起 REPL（Read-Eval-Print-Loop）命令交互面板：

### 1. 终端模式 (CLI Mode)
```bash
python main.py
```

### 2. 网页管理模式 (Web UI Mode)
```bash
streamlit run streamlit_app.py
```

### 终端内连指令 (Built-in Commands)
除了用自然语言对 Agent 下达指令外，你还能使用以下系统级热键：

- **`/cost`** —— 💳 打印目前的 token 消耗报表与美元成本估计。
- **`/history`** —— 📜 查看本次会话的输入指令历史。
- **`/clear`** —— 🗑️ 抹除当前 Session 的缓存状态。
- **`q` 或 `exit`** —— 🛑 安全中止运行并落盘状态。

---

## 📝 更新日志 (Changelog)

### [2026-03-15] - Phase 7: LoRA Fine-Tuning Integration
- **[轨迹收集]**: 新增 `TrajectoryCollector` 模块，自动捕获每一轮对话轨迹用于模型持续进化。
- **[微调脚本]**: 提供 `train_lora.py` 标准模版，支持在消费级显卡上快速微调 Llama/Qwen 等专家模型。
- **[多后端架构]**: `core/llm.py` 现在支持动态加载 LoRA 适配器，并能在云端与本地模型间无缝切换。

### [2026-03-15] - Phase 6: Tool Resilience & Stability
- **[弹性自愈]**: 完善了 `diagnoser` 节点逻辑，支持自动分析 stderr 并尝试补救措施。
- **[工具防崩溃]**: `run_bash` 现在能自动感知 Docker 环境。若未开启，会自动执行“本地紧急回退”方案并给用户报警。
- **[智能路径补全]**: `read_file` 增加了对目录的识别。当 Agent 对目录执行读取时，会自动提示“请使用 `list_files`”。
- **[关系感知 RAG]**: 正式合并 `ASTTools` 与 `RAGTools` 的联动逻辑，现在 RAG 搜索结果包含代码继承关系。

### [2026-03-15] - Phase 5: Observability & Web UI
- **[新内核能力]**: `SwarmOrchestrator` 支持实时事件回调，解耦引擎与 UI。
- **[可视化前台]**: 新增基于 Streamlit 的可视化界面，实时展示 LangGraph 节点流转。

---

### 💡 Phase 6: 企业级扩展
- **多租户权限控制 (RBAC)**: 为不同用户分配不同的工具执行权限与 API 配额。
- **分布式 Agent 节点**: 支持将子 Agent 调度到不同的远程算力节点执行高并发任务。

### 📊 Phase 5: 进阶可观察性 (Completed) ✅
- **自定义看板**: 未来将引入更多业务维度的监控（如子任务成功率分布）。
