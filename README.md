# Production Agent (生产级自主推理智能体)

这是一个高度模块化、具备生产环境高可用特性的 Autonomous Software Engineer Agent（自主软件工程师智能体）。它不仅是一个强大的代码生成与修改工具，更是作为一套**学习和研究现代 AI Agent 架构体系**的优秀教学级脚手架。整个项目的类和方法均包含了详尽的中文设计意图（Docstrings），深入浅出地拆解了 Agent 框架背后的核心实现逻辑。

---

## 📚 开发者指南 (Developer Guides)

我们为开发者准备了详尽的内部技术文档，旨在帮助你快速理解架构、调试代码并扩展 Agent 的能力：

👉 **[点击进入：开发者文档中心 (Docs Index)](./docs/README.md)**

---

## 🌟 核心特性 (Features)

1. **ReAct 核心调度引擎 (Core Loop)**
   - 具备思考、行动、反馈的核心循环能力。
   - **流式输出 (Streaming UX)**: 终端打字机效果呈现 Agent 的实时思考流。
   - **自动化记忆管家 (Context Management)**: 支持毫秒级 Micro 压缩、超过30回合时的历史 LLM 摘要抽提（Auto Compact）、以及强制洗脑重启（Manual Compress），避免因对话过长导致的 API 账单超支或上下文溢出崩溃。
   - **无限死循环熔断器 (Circuit Breaker Tracker)**: 当 Agent 陷入反复报错的死胡同（连续4次）时，自动暂停并向人类告警止损。

2. **状态与数据持久化 (SQLite Managers Layer)**
   - 彻底摒弃由于多线程频繁读写而容易损坏的 JSON 文件锁，拥抱 SQLite 实现持久化。
   - **任务拓扑 (TaskManager)**: 构建父子任务与依赖阻塞网状结构 (DAG)。
   - **异步事件总线 (MessageBus)**: 持久化并调度主从多 Agent 之间的通信队列。
   - **对话记忆断点续传 (Session Resume)**: 按下 Ctrl+C 退出后，下次启动可瞬间恢复当前工作进度。
   - **真实成本计算器 (Token Metrics Tracker)**: `metrics` 数据表拦截并永久累加计费 Token，提供终端实时核算。

3. **物理世界降维打击 (Tools Layer)**
   - **AST Repomap 语法树骨架扫描**: 能够迅速提取长达数十万行代码工程中所有的类与函数签名，不看实现只看接口，解决超大项目的上下文溢出问题。
   - **RAG Local Vector Database**: 内置离线的 ChromaDB 配合 Sentence-Transformers，Agent 可通过自然语言（Semantic Search）从海量代码仓库中大海捞针式定位核心模块。
   - **Runtime Sandbox (运行隔离环境)**: 直连宿主机的 Docker Daemon，Agent 决定执行高风险脚本时，秒级拉起一个丢弃式的 `python-slim` 虚拟容器执行，彻底保障您的 Mac/PC 安全。
   - **Human-in-the-Loop (HITL 审批)**: 对于 `rm -rf`, 覆盖敏感文件等危险操作，Agent 将让出控制权，将 CLI 挂起等待人类敲击 `Y/n` 进行确认。
   - **外界直连 (Web Browsing)**: 打通 `duckduckgo` 搜索与抓取网页脱水文本，使得 Agent 能够自主去网上查阅修复 Unknown Bug 或阅读最新开源库的官网文档。

---

## ⚙️ 环境要求与配置 (Configuration)

### 1. 基础要求
- Python 3.10+
- （可选）Docker Desktop：仅用于启用原生沙盒环境 `sandbox_bash` 功能。

### 2. 安装依赖库
我们使用了业界主流的最佳实践库，请在你的虚拟环境中安装它们：
```bash
pip install anthropic python-dotenv
```
如果需要开启进阶感知功能（推荐）：
```bash
# Web 搜索和 HTML 解析引擎
pip install duckduckgo-search requests beautifulsoup4

# Docker 守护进程操控 SDK
pip install docker

# 本地断网可用的 RAG 向量引擎
pip install chromadb sentence-transformers
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

```bash
python -m production_agent.main
```

### 终端内连指令 (Built-in Commands)
除了用自然语言对 Agent 下达例如 *“帮我用 React 写一个看板应用”* 或 *“查找一下目前代码里哪些地方涉及到了 login 函数，帮我加一下异常拦截日志”* 等指令外，你还能使用以下系统级热键：

- **`/cost`** —— 💳 打印目前的财务监控报表，查看在这台电脑上累计跑了多少 Input/Output Token，以及折合消耗了多少美元。
- **`/compact`** —— 🗜️ 告一段落后手动触发压缩机制。系统会将上文几千轮的历史扔给模型总结出一份几百字的摘要以重置 Context，极大降低你后续每一句话的请求延迟与金钱成本。
- **`/clear`** —— 🗑️ 抹除 `default_modular` Session 的脑容量，彻底开始崭新的工作。
- **`q` 或 `exit`** —— 🛑 安全中止运行，并落盘所有的对话状态，供下次执行断点续传。

---

## 🗺️ 未来更新计划 (Roadmap & Future Plans)

这个生产级 Agent 骨架目前已经达到了业界商用方案 70% 的基底能力，后续如果想将其扩展为完整无懈可击的企业级框架，我们制定了以下演进路线（Phase 3 & Phase 4）：

### 💡 Phase 3: 多模态感知与桌面级操控 (Multi-modal & Computer Use)
- **视觉能力接入 (Computer Use Tool)**: 引入 `pyautogui` 和 `mss` 等工具。允许 Agent 自动截取当前的 IDE 屏幕或网页渲染图，将图像数据直接通过大模型的 Vision 能力传入，让 Agent 真正做到“看见 UI 问题”，而不仅仅是在终端里阅读盲文。
- **自动化浏览器操控 (Playwright System)**: 将 `web_tools` 中简陋的 `requests` 爬虫替换为真实的无头浏览器 (Headless Playwright)。支持 Agent 自主登录网页、点击按钮、拦截验证码等复杂的网络交互动作。

### 🛠️ Phase 4: 多智能体图灵拓扑 (Multi-Agent Swarm Topology)
-目前的 `team.py` (TeammateManager) 还停留在初步的 Spawn/Worker 状态，未来将引入基于图论的 **Swarm 路由模型**。
- 将原本单一的 Lead Agent 打散为 `[ProductManager(提需求)] -> [Architect(画UML/图纸)] -> [Coder(写代码)] -> [QA_Reviewer(写单测发现找错)]` 四角流水线工作流，并通过 `messages` 表构建复杂的审批链网络，用群智结对编程大幅降低单一大模型的幻觉率。

### 📊 Phase 5: 可观测性与可视化前台 (Observability & Web UI)
- **LangSmith / DataDog 探针接入**: 替换目前简单的 `.agent_trace.log`，将所有大模型的中间思考步骤和耗时上传到云端 Tracing 系统。
- **Streamlit / Next.js 管理大盘**: 摒弃 CLI 终端的局限，提供一个网页可视化看板（Web GUI），人类可以在页面上拖拽管理 `[Tasks]` 有向无环图、查看团队每一个 `Teammate` 正在做的事、以及点击审核 HITL 危险命令弹窗。
