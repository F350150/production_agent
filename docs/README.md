# 开发者指南索引 (Documentation Index) 📚

欢迎进入 **Production Agent** 的技术核心。这套文档专为具备工程实践经验、希望深入学习 AI Agent 背景架构与实现的开发者设计。

---

## 🗺 知识地图 (Documentation Map)

> [!IMPORTANT]
> **[🚀 核心学习路线图 (Master Learning Path)](./learning_path.md)**：**推荐首读**。从宏观视角理解 Agent 技术的演进、本质及本项目的设计哲学。

### 🟢 第一阶段：夯实基础 (Foundations)
| 指南名称 | 核心内容 | 推荐人群 |
| :--- | :--- | :--- |
| [🎓 AI Beginner Lab](./ai_beginner_lab.md) | **手把手实战实验室**：三个核心实验带你快速上手。 | *必读：初学者首选* |
| [🏗 架构设计概览](./architecture_overview.md) | LangGraph 编排范式、Swarm 角色转场与自愈。 | *必读：理解系统的全局观* |
| [🚦 环境与调试指南](./getting_started_dev.md) | 工程化环境搭建、Docker 容灾回退及调试技巧。 | *必读：快速跑通首个指令* |

### 🔵 第二阶段：核心逻辑 (Core Logic)
| 指南名称 | 核心内容 | 推荐人群 |
| :--- | :--- | :--- |
| [🎭 Swarm 拓扑编排](./swarm_topology.md) | 节点流转、Summarizer 上下文压缩及 Diagnoser 自愈。 | *关注：多智能体复杂协同* |
| [🛠 技能开发实战](./skill_development.md) | 从传统函数到语义化工具的思维演进与 Schema 设计。 | *关注：业务逻辑原子化* |
| [🗄 数据库一致性](./database_schema.md) | SQLite 持久化设计、RLock 与 WAL 并发控制。 | *关注：底层数据安全与状态* |

### 🟣 第三阶段：进阶能力 (Advanced Features)
| 指南名称 | 核心内容 | 推荐人群 |
| :--- | :--- | :--- |
| [📡 MCP 深度开发](./mcp_development.md) | 模型上下文协议揭秘、非阻塞 I/O 模型与 Stdio 通信。 | *关注：能力扩展与插件开发* |
| [📊 可观测性链路追踪](./observability.md) | LangSmith 探针集成、执行链路透明化与调试。 | *关注：生产监控与质量分析* |
| [🖥️ 可视化管理后台](./web_ui.md) | Streamlit 实战：如何运行 Web 端 Swarm 控制台。 | *关注：交互体验与图化展示* |
| [🧬 LoRA 微调指南](./lora_finetuning.md) | 轨迹收集、数据清洗及专家模型训练实战。 | *关注：模型进化与专家角色* |

---

## 🎓 推荐学习路径

1.  **第一步**：自测实验 **[AI Beginner Lab](./ai_beginner_lab.md)**。不要急着看理论，先进终端跑两个实验，直观感受 Agent 的流态。
2.  **第二步**：阅读 **[架构设计概览](./architecture_overview.md)**。在动手写代码前，先理解智能体是如何“思考”和“路由”的。
3.  **第三步**：对照 **[环境与调试指南](./getting_started_dev.md)** 配置好 `.env`，让程序在本地跑起自己的业务。
4.  **第四步**：查阅 **[技能开发实战](./skill_development.md)**，尝试编写一个简单的 factorial 技能，观察它如何并入智能体的工具集。
5.  **第五步**：学习 **[MCP 深度开发](./mcp_development.md)**，了解如何连接外部已有的庞大生态能力。

---

> [!TIP]
> **关于可维护性**：
> 这一系列文档是由智能体辅助生成的。如果你在后续开发中修改了核心组件（例如更改了数据库表结构），可以随时指令智能体：“请根据最新代码同步更新数据库架构文档”。
