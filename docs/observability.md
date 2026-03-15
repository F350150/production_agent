# 可观测性链路追踪 (Observability with LangSmith) 📊

在复杂的自主智能体（Autonomous Agent）系统中，“黑盒”问题是开发者面临的最大挑战。Agent 为什么这么思考？它调用了哪些工具？中间步骤耗时多久？

为了解决这些问题，我们集成了 **LangSmith** 探针，将 Agent 的“内心世界”透明化。

---

## 🚀 核心架构

本项目通过装饰器模式，在 `core/llm.py` 的底层驱动层注入了 LangSmith 追踪点：

- **自动捕捉**：所有通过 `safe_llm_call` 发起的大模型请求都会被捕捉。
- **上下文关联**：自动关联 System Prompt、User Messages 以及 Tool Call 结果。
- **性能分析**：记录每一轮思考的 Latency（延迟）和 Token 消耗。

---

## ⚙️ 如何启用

1. **获取 API Key**：
   前往 [LangChain Smith](https://smith.langchain.com/) 注册并生成你的 `LANGSMITH_API_KEY`。

2. **配置环境变量**：
   在 `production_agent/.env` (或系统环境变量) 中设置：
   ```env
   LANGSMITH_TRACING=true
   LANGSMITH_ENDPOINT="https://api.smith.langchain.com"
   LANGSMITH_API_KEY="ls__your_key_here"
   LANGSMITH_PROJECT="production-agent"
   ```

3. **运行程序**：
   正常启动 `python main.py` 或 `streamlit run streamlit_app.py`。

---

## 🔍 观测点说明

### 1. 执行链路 (Trace Tree)
在 LangSmith 后台，你可以看到一个树状结构。每一层代表一次推理或工具执行：
- `ChatAnthropic` (or other models): 展示实际发送给 AI 的原始内容。
- `Tool Calls`: 记录 Agent 想要执行的函数名及参数。
- `Tool Results`: 记录工具执行后的返回值。

### 2. 成本监控
每条 Trace 都会自动解析模型返回的 `usage` 字段，统计 Input 和 Output Token，方便进行财务审计。

### 3. 集成 Web UI
在专用的 **Streamlit 管理后台** 中，侧边栏直接提供了跳转到 LangSmith 当日项目的快捷链接，实现“开发-观测”的无缝切换。

---

> [!NOTE]
> **关于网络隐私**：
> 开启追踪后，所有的对话内容都会上传至 LangSmith 平台。如果你在处理极度敏感的数据，建议将 `LANGSMITH_TRACING` 设置为 `false` 以保障数据不出本地。
