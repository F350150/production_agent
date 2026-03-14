# 数据库架构与并发一致性指南 (Database Schema)

智能体的“记忆”与“状态”是其具备长程规划能力的基础。**Production Agent** 并没有采用脆弱的 JSON 文件存储，而是构建了一个基于 **SQLite** 的工业级持久化框架。

---

## 🗄 核心实体模型 (Schema)

数据库文件位于 `data/production_agent.db`。我们定义了四个核心表来支撑智能体的生命周期：

### 1. `sessions` (对话上下文)
这是智能体的“短期记忆快照”。
-   存储 LLM 所有的历史对话记录（JSON 数组）。
-   **设计意图**：实现“断点续传”。即使进程崩溃或被 Ctrl+C 中止，下次启动时也能通过 ID 瞬间恢复到上一秒的状态。

### 2. `tasks` (任务有向无环图 - DAG)
这是智能体的“待办事项清单”。
-   包含任务的优先级、当前执行者（Owner）及阻塞关系（Blocked By / Blocks）。
-   **设计意图**：支持复杂的异步工程。Lead Agent 不需要记住所有细节，只需查询数据库即可知道哪些子任务已完成。

### 3. `inbox` (异步事件总线)
Agent 之间的“信箱”。
-   **设计意图**：在 Swarm 拓扑中，不同节点通过在 `inbox` 中投送消息来解耦协作循环。

---

## 🔒 解决并发死锁：RLock 与 WAL 模式

在传统的 Web 开发中，数据库锁由 Server 处理。但在单机多线程智能体（Main、Orchestrator、Sub-agent 并发运行）中，必须显式处理 **Race Conditions**。

### 1. 为什么使用 `threading.RLock`？
-   **传统锁 (Lock) 的局限**：如果在同一个函数调用链中嵌套请求了同一个锁，普通锁会立即产生“自我死锁”。
-   **可重入锁 (RLock) 的优势**：它允许同一个线程多次获得锁。这对于 `load_session` 内部又调用 `get_db_conn`（两者都带锁）的复杂调用链路至关重要。

### 2. SQLite 高并发调优
我们在 `managers/database.py` 中强制开启了：
-   **WAL (Write-Ahead Logging)**：实现了“读不阻塞写，写不阻塞读”，极大地提高了多 Agent 同时操作数据库时的响应速度。
-   **Busy Timeout (30000ms)**：当数据库确实被某个重型操作完全锁定时，其他组件会自动挂起并轮询 30 秒，而不是直接闪退报错。

---

## 🛠 开发者扩展提示

如果你需要增加一个“性能基准测试记录”功能：
1.  **修改 `database.py`**：在 `_init_db` 中增加新的 `CREATE TABLE` 语句。
2.  **创建新的 Manager**：在 `managers/` 下新建 `metrics_manager.py`。
3.  **遵循规范**：所有的写操作必须包裹在 `with DB_LOCK:` 上下文中，确保原子性。

> [!CAUTION]
> **资源泄露预警**：在开发新 Manager 时，严禁在全局作用域开启不关闭的独立连接。请通过 `get_db_conn()` 共享单例池，系统会自动在 `main.py` 的 `cleanup` 函数中统一回收资源。
