# 开发者快速上手与环境工程指南 (Getting Started)

本指南旨在帮助具备开发基础的新成员在本地快速搭建 **Production Agent** 的研发环境，并介绍如何在这个非确定性的系统中进行工程化调试。

---

## 🛠 开发环境搭建

### 1. 核心依赖
- **Python 3.10+**：我们大量使用了 `structural pattern matching` 以及增强型类型提示，请确保解释器版本。
- **Node.js (LTS)**：由于本项目依赖 MCP 实现在本地访问文件系统和执行 Web 检索，你需要安装 `npx` (Node 包运行器)。

### 2. 工程化初始化
克隆代码库后，建议通过以下方式安装：
```bash
# 1. 安装核心依赖
pip install -e .

# 2. 安装高级感知与 RAG 依赖 (推荐)
pip install docker chromadb tree-sitter playwright duckduckgo-search
```

### 3. 配置秘密文件 (.env)
复制样板并填入大模型凭据。
-   **MODEL_ID**: 建议使用 `claude-3-5-sonnet-20241022` 或更高性能模型以保证 Swarm 逻辑稳定。
-   **Docker 说明**：非强制。若未启动 Docker，系统会自动执行本地回退逻辑并报警。

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

### 4. 链路追踪与观测 (Observability)
-   如果你开启了 `LANGSMITH_TRACING=true`，所有的执行逻辑都会同步到云端。
-   在 `main.py` 报错时，除了看控制台，还可以直接去 LangSmith 后台定位具体是哪一轮对话出的问题。

---

## 🧪 单元测试与覆盖率
项目提供了自动化测试脚本，执行后会生成 HTML 覆盖率报告：
```bash
# 运行所有测试并获取报告路径
./scripts/run_tests.sh
```
该脚本会自动：
1. 设置 `PYTHONPATH` 环境变量。
2. 运行所有 pytest 测试用例。
3. 打印出 HTML 覆盖率报告的 **绝对路径**，方便你直接预览。

> [!WARNING]
> **资源占用说明**：某些 MCP 服务（如浏览器驱动）可能会非常消耗资源或保持进程常驻。如果发现系统响应变慢，请通过 `ps aux | grep node` 或 `ps aux | grep python` 检查是否有僵尸进程。
