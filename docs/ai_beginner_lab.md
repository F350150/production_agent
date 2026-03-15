# 🎓 AI Beginner Lab: 动手实践现代 Agent 架构

欢迎来到这个实战实验室！如果你具有一定的 Python 基础，并想深入了解 **LangChain 1.0** 和 **LangGraph** 是如何落地为生产级系统的，那么你来对地方了。

## 🚩 前置要求 (Prerequisites)
- 熟悉 Python 基础语法（函数、装饰器、异步 `async/await`）。
- 了解大模型的基础概念（Prompt, Token, Tool Calling）。

## 🧪 实验 1：观察 Swarm 节点流转
**目标**：理解 Agent 如何通过“分工协同”解决复杂问题。

1. **启动程序**：运行 `python main.py`。
2. **下达指令**：输入 `帮我写一个简单的 Flask 后端，并让 QA 审核代码`。
3. **观察控制台**：
   - 看到 `➔ Active Agent: ProductManager` 正在分析需求。
   - 看到它发出 `transfer_to_coder` 指令。
   - 看到 `➔ Active Agent: Coder` 开始编写代码。
   - 最终看到 `QA_Reviewer` 介入并进行代码分析。
4. **💡 深度思考**：在 `core/swarm.py` 中，查看 `ROLE_PROMPTS`。每个角色都有独立的 System Prompt，这就像给不同的人戴上了不同的“职能帽子”。分工不仅能减少幻觉，还能让某些角色（如 Coder）携带更多的专业工具。

## 🧪 实验 2：体验精准 HITL (人工在环)
**目标**：理解安全防御边界。

1. **下达指令**：输入 `在当前目录创建一个名为 test_lab.py 的文件`。
2. **触发拦截**：你会看到红色警告 `❗ Security Stop: Agent is attempting dangerous operation: write_file`。
3. **对比实验**：输入 `搜索一下目前 GitHub 上最火的 AI 智能体框架`。
   - 注意：Agent 会直接输出结果，**不会弹出审批请求**。
4. **💡 学习点**：打开 `core/swarm.py` 的 `run_swarm_loop` 函数。找到 `is_dangerous` 的判断逻辑。我们利用 LangGraph 的 `interrupt_after` 特性，在 Agent 想要执行危险工具（如 `run_bash`, `write_file`）之前将其挂起，等待你的命令行输入 `y`。

## 🧪 实验 3：探索异步断点续传
**目标**：理解 Agent 如何拥有“持久记忆”。

1. **制造上下文**：跟 Agent 聊到一个复杂话题（比如正在拆解某个 PRD）。
2. **强行退出**：按下 `q` 退出程序。
3. **重新进入**：再次运行 `python main.py`。
4. **恢复对话**：输入 `刚才我们聊到哪了？`。
5. **💡 深度探究**：系统会自动加载上次的 `thread_id`。所有的消息历史都存储在 SQLite 中。你可以尝试修改 `main.py` 中的 `thread_id`，观察 Agent 是否会丢失之前的记忆。

## 🧪 实验 4：角色性格定制 (Customization)
**目标**：亲手修改 Agent 的行为模式。

1. **修改源码**：打开 `core/swarm.py`，找到 `ROLE_PROMPTS["ProductManager"]`。
2. **注入要求**：在 Prompt 中加入一句：“在每次回答用户之前，先用一个相关的颜文字开头”。
3. **重启验证**：重新运行 `python main.py` 并提问，观察 PM 的回复是否发生了变化。
4. **学习点**：Prompt Engineering 是驱动 Agent 行为的核心。通过修改 `core` 层，你可以定制属于自己的专业团队。

## 🧩 核心源码导读（建议阅读顺序）
1. `core/llm.py`: 了解如何通过 Callback 统计 Token 成本。
2. `tools/registry.py`: 了解如何用 `@tool` 装饰器定义 Agent 的能力，以及如何实现角色权限控制（RBAC）。
3. `core/swarm.py`: **本项目的“心脏”**。重点看 `_build_swarm` 是如何链接不同角色的，以及 `run_swarm_loop` 是如何处理流式输出和中断的。
4. `managers/tasks.py`: 学习 Agent 如何自我管理任务清单，避免迷失在大目标中。

---
希望这些实验能帮你快速撕开 Agent 技术的面纱！如有疑问，欢迎在社区讨论。
