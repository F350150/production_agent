# Production Agent 进阶实战指南：高阶学习任务 (Agent/MCP/RAG/LangGraph)

本指南旨在通过为 `production_agent` 项目添加新功能，帮助你边做边学，深入掌握 Agent 架构、MCP 通信、自建大模型 Skill、RAG 以及底层的 LangChain/LangGraph 技术。本项目为你准备了良好的底座，请尝试完成以下开发需求。

## 📍 任务 1：LangGraph - 扩展多智能体 Swarm 网络
**技术目标:** 深入理解有向无环图 (StateGraph)、动态路由以及多角色的状态流转控制机制。
**需求描述:** 
目前系统中有 `ProductManager`, `Architect`, `Coder`, `QA_Reviewer` 四个核心角色 (定义在 `core/swarm.py` 中)。请为团队引入一个新角色：**`Security_Auditor` (安全审计员)**。
- **任务目标:** 在代码完成开发并经过 QA 测试后，主动触发对代码库的安全检查（防止 SQL 注入、系统暴漏或硬编码秘钥等）。
- **行动指南:**
  1. 在 `core/swarm.py` 中定义并实例化 `Security_Auditor` 节点，并将其注册到 StateGraph 构建器中。
  2. 修改核心的 `_route_from_agent` 及 `_route_from_summarizer` 路由逻辑，使得整个状态流可以按照设定在特定条件下流向 `Security_Auditor`。
  3. 为审计员在 `core/prompts.py` (或你的 Prompt 管理模块) 中撰写其专用 System Prompt，赋予其安全合规排查的职责。
  4. 验证测试：在终端对系统下达修改登录模块逻辑的需求，观察系统是否在 Coder 完工后正确路由给安全审计网络节点。

## 📍 任务 2：LangChain - 自定义事件监听与统计系统
**技术目标:** 掌握 LangChain 的底座回掉系统（Callback System）以及流式事件捕获处理。
**需求描述:** 
当前系统利用了自带的机制进行了简单的开销计算或控制台打印。请实现一个底层的 **LLM 耗时与审计拦截器**。
- **任务目标:** 记录每次 LLM API 调用的真实耗时和详细响应，写入 SQLite 数据库以备后续分析调优。
- **行动指南:**
  1. 创建一个新的 Python 模块，继承 LangChain 的 `BaseCallbackHandler`，重点覆盖 `on_llm_start` 和 `on_llm_end` 等异步方法。
  2. 在计算出真实耗时后，调用 `managers/database.py` 中你新补充的插入逻辑。
  3. 将这个回调对象 (`callbacks=[YourCustomCallback()]`) 绑定到 `core/llm.py` 中初始化的 ChatOpenAI 或对应的 ChatModel 实例上。

## 📍 任务 3：MCP (Model Context Protocol) - 挂载并驱动外部定制服务
**技术目标:** 了解当今领先的 MCP 协议如何打通 Agent 与离岸内部系统的沙盒隔离。
**需求描述:** 
项目中 `tools/mcp_registry.py` 支持加载外部服务器暴露的工具。为了理解这个过程，你需要从零搭建一个独立的 Server 伪造某个外部系统。
- **任务目标:** 编写一个小型的 Python 脚本 `mcp_jira_server.py`，提供 `get_ticket(id)` 和 `update_ticket(id, status)` 工具。
- **行动指南:**
  1. 脱离主体框架，独立使用 `mcp` 官方 Python SDK 快速起一个 stdio 模式下的 Server，提供操作内部工单的函数。
  2. 在外网查阅或根据项目中的机制，将这个服务通过命令的形式挂载注册进 Agent。
  3. 启动 `main.py`，向 Agent 下达自然语言指令：“帮我查看一下 JIRA-1024 任务，并把它标为已完成”，体感 Agent 如何通过 MCP 标准传输 JSON-RPC 指令操控远端进程。

## 📍 任务 4：Skill 系统 - 构建声明式的企业级专家能力
**技术目标:** 利用解耦的声明式配置思想，封装复杂的思考链(Chain of Thought)，提高系统可维护性。
**需求描述:** 
项目内部封装了独特的 `SkillRegistry` 机制，可以在不写死代码的情境下载入外部技能文件。
- **任务目标:** 创建一个专门处理遗留代码升级的组件：**`python_to_rust_converter` 专家技能**。
- **行动指南:**
  1. 在 `skills/builtin/` 目录下新增一个带有 YAML 头信息的 Markdown 配置文档。
  2. 在该配置的 Front-matter 中，精确定义 input 参数（如 `source_file`, `target_lang`）和其所需的配套 Tools（如 `read_file`, `write_file` 等）。
  3. 在正文中手写包含丰富示例的 Few-Shot 提示，教会模型如何逐步转换。
  4. 指引 User 使用 `/use_skill` 机制触发你的新技能重构 `utils/` 中的某个小型普通函数。

## 📍 任务 5：复合 RAG - 将语义上下文检索引入代码解析
**技术目标:** 深化在复杂知识库场景下，向量检索（Vector Search）如何辅助大模型精准答复。
**需求描述:** 
你目前能通过 `ast_tools.py` 借由正则分析局部，但当遇到“在哪里修改登录加密算法”这种模糊需求时，基于确切关键词或树结构的搜索很难奏效。
- **任务目标:** 为项目接入轻量化的向量知识库（如 ChromaDB/FAISS），让系统实现真正的 "以意寻图"。
- **行动指南:**
  1. 引入对应的 LangChain Document Loader 及 Text Splitter，编写一个脚本将本项目下核心业务流程文件转换并分块。
  2. 使用嵌入模型（如 OpenAI Embeddings）将代码块信息向量化并离线落盘至本地数据库结构。
  3. 开发并注入一个原生 Tool `semantic_code_search(query)`，在工具内部实现向量比对检索(Similarity Search)。
  4. 促使 Agent 自己在面对大规模重构的抽象请求时，首先调用该语义检索器获得需要参考的文件片段，补全局部上下文。

## 📍 任务 6：动态外挂机制 - 支持从任意外部路径加载 Skill
**技术目标:** 理解插件化架构设计理念，实现真正的核心代码与知识能力解耦。
**需求描述:** 
目前系统只能识别并加载位于 `skills/builtin/` 目录下的内置 Skill 文件。为了让它具备像真实开源框架一样的扩展性，需要支持用户挂载(Mount)处于任何绝对或相对路径的个人 Skill。
- **任务目标:** 让系统支持读取 `config/mcp_servers.yaml` 中的 `skills.custom_path` 配置，并在系统启动时将其一同挂载到系统中。
- **行动指南:**
  1. 定位阅读 `skills/skill_registry.py`，观察当前框架自动搜寻解析 markdown 的方式。
  2. 扩展或重构其检索逻辑：读取配置项中的外部路径（例如 `~/my_skills/` 或某个指定的 URL repo）。
  3. 支持动态加载外挂 skill：当用户在终端下达“请挂载 /tmp/my_new_skill.md”等命令，或修改配置后，系统应该能将它纳入 `use_skill` 工具的可选列表中，允许 Agent 即时调用并赋予其所需工具权限。

---

> 💡 寄语：理论学习无法替代实践调试。建议你选定上述任意一个任务，基于现有的工程骨架独立拉取一个分支并敲下第一行代码！遇到报错就是你理解底层引擎流转原理的最佳契机。
