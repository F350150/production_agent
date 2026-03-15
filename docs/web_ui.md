# 可视化管理后台 (Web UI with Streamlit) 🖥️

虽然 `main.py` 提供了极客感十足的 CLI 交互界面，但在处理复杂的 **Swarm (多智能体集群)** 协同任务时，网页端的可视化展现能提供更清晰的视角。

---

## 🌟 核心功能

### 1. 实时 Swarm 日志流
不同于 CLI 的顺序滚动，Web UI 通过侧边栏和动态状态栏展现：
- **节点状态**：实时高亮当前处于控制权地位的 Agent (ProductManager, Architect, Coder, QA)。
- **工具调用详情**：通过可折叠的消息框（JSON Viewer）展示 Agent 调用的每一个工具及其精细参数。

### 2. 增强型聊天交互
- 使用 `st.chat_message` 模拟现代 AI App 的对话体验。
- 支持 Markdown 内容的完美渲染，包括表格、代码块等。

### 3. 会话管理
- **一键清空**：侧边栏 `Clear Session` 按钮可瞬间重置 SQLite 数据库中的 `swarm_modular` 状态，开启全新任务。
- **观测集成**：直连 LangSmith 观测大盘，实现链路追踪。

---

## 🚀 启动指南

1. **安装必要依赖**：
   ```bash
   pip install streamlit
   ```

2. **运行 Web 应用**：
   在工程根目录下执行：
   ```bash
   streamlit run production_agent/streamlit_app.py
   ```

3. **访问地址**：
   默认情况下，应用将在 `http://localhost:8501` 启动。

---

## 🛠️ 技术实现原理 (Event Callbacks)

为了让 Web UI 能够监听到 `core/swarm.py` 内部的引擎状态，我们重构了 Swarm 调度逻辑，引入了 **回传机制 (Callback Mechanism)**：

```python
# Swarm 引擎内部触发
def run_swarm_loop(self, starting_role, callback=None):
    # ...
    if callback:
        callback("tool_use", {"name": block.name, "input": block.input})
```

这种设计实现了 **UI 与 引擎逻辑的彻底解耦**。不论是终端、Web 还是未来的集成桌面端，都可以通过传递不同的 `callback` 函数来实现自定义的状态呈现。

---

> [!TIP]
> **推荐用法**：
> 建议在第二台显示器上全屏运行 Web UI。它非常适合用来展示复杂的软件工程自动化过程（例如让 Agent 自动写一个完整的项目），因为它能清晰地展现不同专家角色之间的“接力棒”传递。
