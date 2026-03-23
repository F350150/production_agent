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
- **MCP 多种传输协议**：支持 stdio 和 HTTP/JSON-RPC 两种传输模式，无缝连接 FastMCP 服务。
- **77 个工具 + 8 项技能**：涵盖视觉感知、浏览器自动化、Git、数据库、Docker、通知推送等全方位能力矩阵。
- **Computer Use 能力**：截图、OCR、鼠标键盘操控、屏幕录制，实现 Anthropic Computer Use 范式。

---

## 🏗️ 核心技术栈 (Modern AI Stack)

本项目依托现代 AI 开发标准构建，是深入掌握以下技术的绝佳起点：

| 技术 | 说明 |
|------|------|
| **LangChain 1.0** | 统一的 LLM 抽象层，集成了丰富的工具库与内存模型 |
| **LangGraph Swarm** | 使用 `StateGraph` 实现多角色编排。支持 `summarizer` 节点自动压缩上下文 |
| **MCP 传输协议** | 支持 stdio 和 HTTP/JSON-RPC 两种传输模式 |
| **语义分块 RAG** | 基于 AST 的语义分块 + BM25 关键词索引 + 混合搜索 |
| **自诊断与自愈** | 内置 `diagnoser` 节点，自动分析错误并建议修复方案 |
| **弹性工具治理** | Docker 沙盒未启动时自动回退到本地执行 |
| **LoRA 微调支持** | 轨迹收集器 + 一键导出 Alpaca 格式训练数据 |
| **Computer Use** | 屏幕截图、OCR 识别、鼠标键盘操控、屏幕录制 GIF |
| **77 工具矩阵** | 视觉 ×11 + 浏览器 ×16 + Git ×7 + DB ×4 + Docker ×8 + 通知 ×4 + 基础工具 |

---

## ✨ 最新特性 (Latest Features)

### 🖥️ 全能 Computer Use（77 个工具）

Agent 具备完整的计算机操控与自动化能力：

| 能力层 | 工具 | 数量 |
|--------|------|------|
| **视觉感知** | 全屏/区域截图、OCR 文字识别、GIF 录屏 | 4 |
| **鼠标操控** | 移动、单击、双击、拖拽、滚轮 | 5 |
| **键盘操控** | 文本输入、快捷键组合 (`cmd+c`, `ctrl+shift+f`) | 2 |
| **浏览器自动化** | 打开/截图/点击/输入/滚动/多标签/表单填充/Cookie/PDF | 16 |
| **Git 版本控制** | status/diff/log/blame/commit/branch/PR | 7 |
| **数据库操作** | connect/query/schema/explain (SQLAlchemy 多库) | 4 |
| **Docker 管理** | ps/logs/exec/start/stop/compose up-down/images | 8 |
| **通知推送** | macOS 通知、邮件、Webhook(Slack/Discord)、语音播报 | 4 |

### MCP HTTP 传输支持
- ✅ `HttpMCPClient` - 支持 FastMCP HTTP/JSON-RPC 协议
- ✅ YAML 配置 - 支持 `config/mcp_servers.yaml` 配置 MCP 服务器
- ✅ 混合传输 - 同时支持 stdio 和 HTTP 两种 MCP 服务器

### 开发者技能 (8 个技能)
| 技能 | 功能 |
|------|------|
| `debug_explain` | 解析错误堆栈，提供修复建议 |
| `generate_test` | 根据函数代码生成 pytest 测试用例 |
| `api_design_review` | 评估 API 设计质量，检查命名和文档 |
| `dependency_analysis` | 分析导入/调用图，检测循环依赖 |
| `code_migration` | Flask→FastAPI、requests→httpx 等代码迁移 |
| `web_research` | 多关键词自动搜索并汇总报告 |
| `code_review` | 代码质量审查与建议 |
| `narcissistic_numbers` | 数学演示技能（自恋数计算） |

### RAG 增强
| 功能 | 说明 |
|------|------|
| **语义分块** | 基于 AST 按函数/类边界切分，保留语义完整性 |
| **BM25 索引** | 关键词索引，提升精确匹配能力 |
| **混合搜索** | 向量相似度 + BM25 融合，提高召回率 |


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
- Windows 平台默认可能没有 `readline`：CLI 可正常运行，但命令历史与 Tab 补全会自动降级禁用。

### 2. 安装依赖库
```bash
# 安装核心依赖
pip install langchain langchain-anthropic langgraph langgraph-checkpoint-sqlite aiosqlite python-dotenv rich nest_asyncio

# 安装进阶感知功能（推荐）
pip install playwright pyautogui Pillow pytesseract beautifulsoup4 duckduckgo-search docker chromadb sentence-transformers tree-sitter sqlalchemy requests

# Playwright 浏览器引擎
playwright install chromium

# 安装 LangChain 增强组件（可选）
pip install langgraph langsmith langchain-text-splitters
```
*(注：架构内部存在平滑降级机制。如果 Docker 未开启或某项依赖缺失，系统会优先尝试本地兜底或提示安装，**而不会让整个程序直接崩溃**。)*
*(注：部分 langchain 组件在新版本中已重构，如 `langchain.agents` 已并入 `langgraph`，`langchain.chains` 已移入 `langchain-core`。)*

### 3. 设置环境变量
项目根目录下创建一个 `.env` 文件，填入你的大模型凭据：
```env
# 核心通信密钥（必填）
ANTHROPIC_API_KEY=your_claude_api_key_here

# 指定调用的模型版本（默认：claude-3-5-sonnet-20241022）
MODEL_ID=claude-3-5-sonnet-20241022

# 可选：使用本地模型
USE_LOCAL_LLM=false
LOCAL_BASE_URL=http://localhost:8000/v1
LOCAL_MODEL_ID=qwen-7b-lora
```

### 4. MCP 服务器配置
支持两种方式配置 MCP 服务器：

**方式一：环境变量（JSON 数组）**
```env
MCP_SERVERS='[{"name":"filesystem","transport":"stdio","command":["npx","-y","@modelcontextprotocol/server-filesystem","./"]}]'
```

**方式二：YAML 配置文件**
```yaml
# config/mcp_servers.yaml
mcp_servers:
  - name: filesystem
    transport: stdio
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "./"]

  - name: fastapi_service
    transport: http
    url: http://localhost:8000/mcp
    timeout: 60

skills:
  builtin_path: skills/builtin
  custom_path: ~/my_skills
```

---

## 🚀 启动与使用 (Usage)

### 1. 终端模式 (CLI Mode)
```bash
python main.py
```

### 2. 网页管理模式 (Web UI Mode)
```bash
streamlit run streamlit_app.py
```

### 3. 交互指令
- **`/cost`** —— 💳 打印目前的 token 消耗报表与美元成本估计。
- **`/history`** —— 📜 查看本次会话的输入指令历史。
- **`/clear`** —— 🗑️ 抹除当前 Session 的缓存状态。
- **`q` 或 `exit`** —— 🛑 安全中止运行并落盘状态。

---

## 🧪 测试 (Testing)

### 运行测试
```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_skills.py -v
python -m pytest tests/test_rag_enhanced.py -v
```

### 测试覆盖
| 测试文件 | 测试数量 | 说明 |
|----------|----------|------|
| `test_skills.py` | 23 | 5 个新技能测试 |
| `test_http_mcp_client.py` | 9 | HTTP MCP 和 YAML 配置测试 |
| `test_mcp_client.py` | 11 | MCP 客户端核心测试 |
| `test_rag_enhanced.py` | 16 | RAG 增强功能测试 |
| **总计** | **59+** | |

### 集成测试场景
详细集成测试场景请参考：[IT Test Scenarios](./docs/it_test_scenarios.md)

---

## 📝 更新日志 (Changelog)

### [2026-03-22] - Phase 9: Full Feature Expansion (77 Tools)
- **[视觉感知增强]**: 区域截图、OCR 文字识别、GIF 屏幕录制、双击/拖拽/滚轮/快捷键组合
- **[浏览器增强]**: 多标签管理、表单填充、Cookie 保持、PDF 提取、文件下载、全页截图
- **[Git 深度集成]**: status/diff/log/blame/commit/branch/PR 全流程工具
- **[数据库操作]**: SQLAlchemy 多库支持（SQLite/PostgreSQL/MySQL）
- **[Docker 管理]**: 容器生命周期管理 + docker-compose 服务编排
- **[通知推送]**: macOS 通知、邮件、Webhook、语音播报
- **[RBAC 增强]**: 新工具权限分配 + 危险操作 HITL 审批
- **[路由优化]**: ProductManager 路由规则扩展至 6 类请求分类

### [2026-03-18] - Phase 8: LangChain Integration & Enhancements
- **[MCP HTTP 支持]**: 新增 `HttpMCPClient` 支持 FastMCP HTTP/JSON-RPC 协议
- **[MCP YAML 配置]**: 支持 `config/mcp_servers.yaml` 配置文件
- **[5 个新技能]**: `debug_explain`, `generate_test`, `api_design_review`, `dependency_analysis`, `code_migration`
- **[RAG 增强]**: 语义分块、BM25 索引、混合搜索

- **[单元测试]**: 80+ 测试用例，覆盖所有新功能

### [2026-03-15] - Phase 7: LoRA Fine-Tuning Integration
- **[轨迹收集]**: 新增 `TrajectoryCollector` 模块，自动捕获每一轮对话轨迹用于模型持续进化。
- **[微调脚本]**: 提供 `train_lora.py` 标准模版，支持在消费级显卡上快速微调 Llama/Qwen 等专家模型。
- **[多后端架构]**: `core/llm.py` 现在支持动态加载 LoRA 适配器，并能在云端与本地模型间无缝切换。

### [2026-03-15] - Phase 6: Tool Resilience & Stability
- **[弹性自愈]**: 完善了 `diagnoser` 节点逻辑，支持自动分析 stderr 并尝试补救措施。
- **[工具防崩溃]**: `run_bash` 现在能自动感知 Docker 环境。若未开启，会自动执行"本地紧急回退"方案并给用户报警。
- **[智能路径补全]**: `read_file` 增加了对目录的识别。当 Agent 对目录执行读取时，会自动提示"请使用 `list_files`"。
- **[关系感知 RAG]**: 正式合并 `ASTTools` 与 `RAGTools` 的联动逻辑，现在 RAG 搜索结果包含代码继承关系。

### [2026-03-15] - Phase 5: Observability & Web UI
- **[新内核能力]**: `SwarmOrchestrator` 支持实时事件回调，解耦引擎与 UI。
- **[可视化前台]**: 新增基于 Streamlit 的可视化界面，实时展示 LangGraph 节点流转。

---

## 📂 项目结构

```
production_agent/
├── core/                    # 核心模块
│   ├── llm.py              # LLM 接口封装
│   ├── swarm.py            # Swarm 多智能体编排
│   ├── context.py          # 上下文管理
│   └── prompts.py          # 提示词模板
├── tools/                   # 工具层 (77 个工具)
│   ├── registry.py          # 工具注册中心
│   ├── computer_tools.py    # Computer Use（截图/OCR/鼠标/键盘）
│   ├── playwright_tools.py  # 浏览器自动化（Playwright）
│   ├── git_tools.py         # Git 版本控制
│   ├── db_tools.py          # 数据库操作（SQLAlchemy）
│   ├── docker_manager.py    # Docker 容器管理
│   ├── notify_tools.py      # 通知推送（macOS/邮件/Webhook/TTS）
│   ├── mcp_client.py        # MCP 客户端 (stdio + http)
│   ├── mcp_registry.py      # MCP 注册表
│   ├── rag_tools.py         # RAG 工具
│   └── ...
├── skills/                   # 技能系统
│   ├── skill_registry.py     # 技能注册表
│   └── builtin/             # 内置技能
│       ├── debug_explain.py
│       ├── generate_test.py
│       ├── api_design_review.py
│       ├── dependency_analysis.py
│       └── code_migration.py
├── managers/                 # 管理器
│   ├── team.py              # 团队管理
│   ├── tasks.py             # 任务管理
│   └── database.py          # 数据库
├── config/                   # 配置文件
│   ├── governance.yaml       # RBAC 权限配置
│   └── mcp_servers.yaml      # MCP 服务器配置
├── tests/                    # 测试
│   ├── test_skills.py
│   ├── test_rag_enhanced.py
│   └── ...
├── docs/                     # 文档
│   ├── README.md
│   ├── it_test_scenarios.md
│   └── ...
└── main.py                   # 入口
```

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📄 许可证

本项目仅供学习和研究使用。
