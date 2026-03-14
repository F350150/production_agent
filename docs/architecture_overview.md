# Production Agent: 架构设计全景概览

欢迎使用 **Production Agent** 项目。本指南旨在为具有资深工程背景但初涉 AI 领域的开发者提供一套系统化的架构视角，深入解构自主智能体（Autonomous Agents）的底层原理。

---

## 🏗 核心设计范式：从“确定性编程”到“自主推理”

传统软件工程依赖于 if-else 等确定性逻辑，而本项目基于 **ReAct (Reasoning + Acting)** 范式。

### 什么是 ReAct？
在每一次交互中，智能体并非随机调用工具，而是遵循以下闭环逻辑：
1.  **Thought (推理)**：利用 LLM 的逻辑能力，分析当前任务现状与目标的差距。
2.  **Action (行动)**：根据推理结论，选择最合适的工具（Tool）。
3.  **Observation (观察)**：接收工具执行的结果（如读取的文件内容、报错等）。
4.  **Repeat (迭代)**：将观察结果纳入上下文，更新思维，开启下一轮推理。

---

## 🧩 系统逻辑分层

我们的架构通过解耦智能、资源和数据，实现了生产级的稳定性。

### 1. 编排层 (Orchestrator Layer) - `core/swarm.py`
采用了 **Figure-Eight (八字拓扑) 编排模型**：
-   **SwarmOrchestrator**：充当总线，负责在不同专家节点（Agent Nodes）之间切换控制权。
-   **Handover 机制**：通过 `__HANDOVER_SIGNAL__` 预定义信号实现。当 Lead Agent 发现任务涉及专业编码时，会自动将“控制手柄”移交给 Engineer Agent。

### 2. 执行引擎层 (Execution Engine) - `core/loop.py`
这是整个项目的“心脏”，负责将 LLM 的文本输出转化为系统指令：
-   **AgentLoop**：解析 LLM 响应中的 `tool_use` 字段。
-   **Context Manager**：根据 Token 限制动态压缩上下文（Context Window），防止超出模型处理上限。

### 3. 持久化与服务层 (Persistence & Services) - `managers/`
摆脱了传统的无状态模式，通过 SQLite 为智能体提供“长期记忆”：
-   **`database.py`**：利用 `RLock` 和 `WAL` 模式解决多 Agent 并发读写冲突。
-   **`tasks.py`**：将复杂的工程需求分解为由 DAG（有向无环图）组织的原子任务，确保逻辑不丢失。

### 4. 能力扩展层 (Capability Layer) - `tools/` & `skills/`
智能体通过这层与物理世界交互：
-   **ToolRegistry**：工具索引中心，聚合了静态代码工具和动态 MCP 工具。
-   **SkillRegistry**：支持动态热插拔的 Python 技能库，用于封装高复杂度业务逻辑。

---

## ⚙️ 系统时序图 (Data Flow)

以下展示了当用户输入一个指令时，系统内部的流转逻辑：

```mermaid
sequenceDiagram
    participant User
    participant Main as main.py (UI/REPL)
    participant Orchestrator as SwarmOrchestrator
    participant Loop as AgentLoop
    participant Registry as ToolRegistry

    User->>Main: 下达指令 (如: "重构数据库模块")
    Main->>Orchestrator: 初始化 Swarm 引擎
    Orchestrator->>Loop: 激活当前节点 (ProductManager)
    loop ReAct 循环
        Loop->>Loop: Thought (思考计划)
        Loop->>Registry: Action (调用文件读取工具)
        Registry-->>Loop: Observation (返回源代码内容)
    end
    Loop->>Orchestrator: 完成分析，Handover 给 Architect
    Orchestrator->>User: 返回最终重构方案
```

---

## 🚀 开发者自研建议

作为软件工程师，你可以通过以下切入点深度定制项目：
-   **扩展编排流**：在 `swarm.py` 中定义新的 Agent 角色（如：Security Auditor）。
-   **封装领域模型**：在 `managers/` 中添加新的业务 Manager（如：GitManager）。
-   **强化感知能力**：通过 `MCP` 接入公司内部的专有 API 或数据库。

> [!IMPORTANT]
> **设计哲学**：在智能体开发中，应尽可能将**复杂的确定性逻辑**（如数学计算、复杂字符串解析）封装为 **Python Tool**，而将**模糊的需求理解和决策控制**留给 **LLM**。
