# Swarm 拓扑与编排设计 (Swarm Topology)

在 **Production Agent** 中，我们并没有采用简单的“一个智能体打天下”模式，而是实现了一套**分布式的多智能体协同系统**（Figure-Eight Multi-Agent Swarm）。这种架构的核心在于“分治”与“专业化”。

---

## 🎨 协同范式：中心化编排 (Orchestration)

智能体协同通常分为两种模式：
-   **舞蹈模式 (Choreography)**：Agent 之间互相发送消息，由被动触发决定下一步。
-   **编排模式 (Orchestration)**：存在一个中心协调器（Orchestrator）来决定当前谁握有主控权。

本项目选择了**编排模式**，通过 `SwarmOrchestrator` 管理各个角色。这种模式在工程上具备更高的可预测性和可调试性。

---

## 🤝 控制权转移机制 (Handover Logic)

控制权转移是 Swarm 灵活性体现的核心。在本项目中，它通过一个特殊的**逻辑钩子**实现：

### 1. 技术实现原理
-   我们向所有智能体注入了一个名为 `handover_to` 的工具。
-   当 Agent 执行该工具时，会向系统总线投送一个携带 `__HANDOVER_SIGNAL__` 前缀的字符串。
-   `SwarmOrchestrator` 会在工具执行结果中识别该特殊信号，并立即触发环境切换。

### 2. 上下文 (Context) 的继承与隔离
-   **继承**：新接管的智能体会继承之前的对话摘要，确保不会丢失用户的主要目标。
-   **隔离**：每个智能体节点都有独立的 `Instructions`（系统提示词）和专用工具集。例如，`ProductManager` 无法直接调用 `write_file`，从而防止了它因权限过大而产生的输出偏移（Hallucination）。

---

## 🧬 典型的动态角色拓扑

以下是一个标准的“需求到代码”任务在 Swarm 中的流转过程：

1.  **ProductManager (PM)**：
    -   *职能*：理解用户模糊输入，拆解为 `Task`。
    -   *动作*：创建任务后，调用 `handover_to("Architect")`。
2.  **Architect (架构师)**：
    -   *职能*：分析项目依赖，决定文件目录结构。
    -   *动作*：制定方案后，调用 `handover_to("Engineer")`。
3.  **Engineer (工程师)**：
    -   *职能*：通过 `skills` 或 `base_tools` 完成具体代码逻辑。
    -   *动作*：完成后将任务状态置为 `completed`。

---

## 🚀 垂直化子智能体 (Nested Sub-agents)

除了横向的控制权转移，我们还支持**纵向的智能体调用**。
-   **场景**：当 `Lead Agent` 正在专注于编写代码，但突然需要去互联网检索一个特定的 API 时。
-   **实现**：它会调用 `run_subagent`。这是一个**阻塞式调用**，父智能体会启动一个临时的子智能体去执行任务并返回结果，而主逻辑不发生 Handover。

---

## 💡 开发提示：如何扩展 Swarm 节点

要将此系统扩展到企业级环境（如增加一个 `SecurityAuditor`），你只需：
1.  在 `core/swarm.py` 的 `agent_configs` 中新增一个 key。
2.  定义高度受限的 `instructions`。
3.  在原有 Agent 的 Prompt 中加入“什么时候该移交给 SecurityAuditor”的判别逻辑。

> [!TIP]
> **设计经验**：Swarm 的精髓在于**动态限制 (Dynamic Constraint)**。通过 Handover，我们在每一时刻都只给模型提供最精准的 5-8 个工具，这比给它 50 个工具的成功率要高出数倍。
