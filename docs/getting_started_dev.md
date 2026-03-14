# 开发者快速上手与环境工程指南 (Getting Started)

本指南旨在帮助具备开发基础的新成员在本地快速搭建 **Production Agent** 的研发环境，并介绍如何在这个非确定性的系统中进行工程化调试。

---

## 🛠 开发环境搭建

### 1. 核心依赖
- **Python 3.10+**：我们大量使用了 `structural pattern matching` 以及增强型类型提示，请确保解释器版本。
- **Node.js (LTS)**：由于本项目依赖 MCP 实现在本地访问文件系统和执行 Web 检索，你需要安装 `npx` (Node 包运行器)。

### 2. 工程化初始化
克隆代码库后，建议通过以下方式安装，以启用“开发模式（Editable Mode）”：
```bash
# 进入项目根目录
pip install -e .
```

### 3. 配置秘密文件 (.env)
复制样板并填入大模型凭据。注意：如果你使用的是兼容 OpenAI/Anthropic 协议的网关（如智谱 AI、OpenRouter），请务必正确配置 `ANTHROPIC_BASE_URL`。

---

## 🚦 系统运行与状态确认

运行入口文件：
```bash
python main.py
```

### 启动时的关键观察点：
- **Lazy Loading (懒加载)**：你会注意到欢迎界面弹出极快。这是因为系统在第一条消息输入前，不会初始化昂贵的 Swarm 引擎。
- **Tool Discovery (工具发现)**：当输入第一句话后，控制台会详细列出当前已连接的 MCP 服务器及其加载的工具数量。请检查是否有 `Warning` 提示服务器连接失败。

---

## 🕵️‍♂️ 深度调试技巧 (Advanced Debugging)

智能体系统的调试与传统系统不同，其逻辑分散在 **代码** 和 **Prompt** 中。

### 1. 追踪思考链 (.agent_trace.log)
所有低级别的通信详情（包括完整的 API Request、MCP 服务器的错误堆栈、以及 Agent 每一轮的 Thought 原始文本）都会写入根目录下的 `.agent_trace.log`。
-   **技巧**：遇到 Agent 陷入死循环或回答文不对题时，先看 Trace Log。

### 2. 数据库状态监控
你可以使用任何 SQLite GUI 工具（如 DBeaver 或 DB Browser for SQLite）打开 `data/production_agent.db`。
-   查看 `sessions` 表可以分析为何 Agent 丢失了之前的记忆。
-   查看 `tasks` 表可以追踪任务 DAG 是否解析正确。

### 3. 热清理 (Reset State)
-   **软件层**：在 CLI 输入 `/clear`。这会重置当前对话，但保留数据库连接。
-   **物理层**：完全关闭进程并删除 `data/` 目录下的 `.db` 文件。这是处理各种奇葩死锁或状态污染的终极手段。

---

## 🧪 单元测试
项目包含针对核心组件（如 Registry、Client）的自动化测试：
```bash
pytest tests/
```

> [!WARNING]
> **资源占用说明**：某些 MCP 服务（如浏览器驱动）可能会非常消耗资源或保持进程常驻。如果发现系统响应变慢，请通过 `ps aux | grep node` 或 `ps aux | grep python` 检查是否有僵尸进程。
