# 开发者指南索引 (Documentation Index) 📚

欢迎进入 **Production Agent** 的技术核心。这套文档专为具备工程实践经验、希望深入学习 AI Agent 背景架构与实现的开发者设计。

---

## 🗺 知识地图 (Documentation Map)

| 指南名称 | 核心内容 | 推荐人群 |
| :--- | :--- | :--- |
| [🏗 架构设计概览](./architecture_overview.md) | 深度拆解 ReAct 推理范式与 Swarm 编排逻辑。 | *必读：理解系统的全局观* |
| [🚦 环境与调试指南](./getting_started_dev.md) | 工程化环境搭建、Trace Log 分析及调试技巧。 | *必读：快速跑通首个指令* |
| [📡 MCP 深度开发](./mcp_development.md) | 模型上下文协议揭秘、非阻塞 I/O 模型与 Stdio 通信。 | *关注：能力扩展与插件开发* |
| [🎭 Swarm 拓扑编排](./swarm_topology.md) | 群智编排、Figure-Eight 拓扑及控制权转移机制。 | *关注：多智能体复杂协同* |
| [🛠 技能开发实战](./skill_development.md) | 从传统函数到语义化工具的思维演进与 Schema 设计。 | *关注：业务逻辑原子化* |
| [🗄 数据库一致性](./database_schema.md) | SQLite 持久化设计、RLock 与 WAL 并发控制。 | *关注：底层数据安全与状态* |

---

## 🎓 推荐学习路径

1.  **第一步**：阅读 **[架构设计概览](./architecture_overview.md)**。在动手写代码前，先理解智能体是如何“思考”和“路由”的。
2.  **第二步**：对照 **[环境与调试指南](./getting_started_dev.md)** 配置好 `.env`，让程序在本地跑起来。
3.  **第三步**：查阅 **[技能开发实战](./skill_development.md)**，尝试编写一个简单的 factorial 技能，观察它如何并入智能体的工具集。
4.  **第四步**：学习 **[MCP 深度开发](./mcp_development.md)**，了解如何连接外部已有的庞大生态能力。

---

> [!TIP]
> **关于可维护性**：
> 这一系列文档是由智能体辅助生成的。如果你在后续开发中修改了核心组件（例如更改了数据库表结构），可以随时指令智能体：“请根据最新代码同步更新数据库架构文档”。
