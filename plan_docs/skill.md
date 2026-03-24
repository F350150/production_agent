# LLM Skill (专家技能体系) 深度探索与系统设计

## 1. 概念溯源：功能型工具 vs. 智能型技能
在 Agent 生态中，很多人将 **Tools (工具)** 和 **Skills (技能)** 混为一谈。
- **Tool (工具/API)**：是纯计算机确定性层面的能力（如：`read_file()`, `calculate_sum()`, `run_sql()`）。
- **Skill (技能/能力配置)**：是利用 LLM 的不确定性和推理能力包装出来的一种复合能力（如：`Code_Reviewer`, `Creative_Translator`，它们内部其实可能调用了好几个 Tool，同时带有浓厚的领域专家提示词）。

## 2. 声明式技能 (Declarative Skills) 的演进
随着系统复杂化，如果把所有的专家级 prompt 都硬编码写进 Python 脚本，项目将不可维护。
因此，业界衍生出将 Skill 提取为 **声明式文件 (YAML / JSON / Markdown)** 的范式：
- **组成部分**：
  1. **元信息**：技能名称、描述、作者、适用模型版本。
  2. **输入约束 (Input Schema)**：定义该技能接收什么参数（利用 JSON Schema 描述强类型校验）。
  3. **工具依赖**：声明要想使用这门技能，Agent 需要被授权哪些 Tools。
  4. **System Prompt / Persona**：角色的思维链逻辑 (CoT)。
  5. **Few-Shot Examples (小样本学习)**：举反例和正例，这是 Skill 效果好坏的决定性因素。

## 3. 技能系统的架构设计模式 (Architecture Patterns)
### 3.1 动态挂载与热插拔 (Hot Plugin System)
- 企业级架构不仅限于把 prompt 存进数据库，还需要能在外部存储（如 S3、内部配置中心）拉取最新的 Skill 清单并在运行时刷新。
- 当用户触发意图时，Routing Engine 能够根据用户的语言进行 Semantic Search（语义搜索），在成百上千的技能海中找到最吻合的一门 Skill 加载入内存。

### 3.2 OpenAI Custom GPTs 与 Coze 插件背后的逻辑
各大平台的“搭建智能体”本质上就是在填一张巨大的 Skill 配置表：
- 它们将你的提示词与 OpenAPI 规范封装，底层利用其核心模型的 function-calling 能力动态解析这段元数据，以此在物理层模拟出了千万个完全不同的 Agent 实例。

## 4. 高阶：思考链 (Chain of Thought, CoT) 的工程化封装
一个优秀的 Skill，不在于指令多长，而在于如何引导 LLM“分步思考 (Let's think step by step)”：
- 写 Skill 的最佳实践是，在 Prompt 中强制要求 LLM 输出一个 `<thinking>` 或 `<analysis>` 标签并在内部进行长篇推理，然后再在最后一个包含结果的 XML 标签中输出最终答案。这种“隐式强制多步推理”往往能把弱模型的表现拉升一个台阶。

## 5. 挑战任务与进阶路线图 (Your Roadmap)
- **挑战 1：零代码抽象**。尝试用 Pydantic 或 JSON Schema，定下一个能同时被前台 UI 渲染成动态表单，又能被后台大模型看懂的通用 Skill Schema。
- **挑战 2：Few-shot 模板引擎**。实现一套可以在 Skill 内嵌入 Jinja2 逻辑语法的解析器，允许根据用户不同的输入参数，动态切换 Few-shot 里的例子（如输入参数要求翻译成西班牙语，就去挂载带西语样本的提示词）。
- **挑战 3：Skill 评测管道**。由于每次修改 Skill Prompt 都会带来模型产出概率漂移。你需要编写一个基于 `pyest` + `LLM-as-a-Judge` 的测试跑道。每改一个词，用另一个强模型打分，验证你这套 Skill 重构是否发生了能力倒退（Regression）。
