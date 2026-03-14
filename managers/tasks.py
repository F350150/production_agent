from managers.database import get_db_conn, DB_LOCK

class TaskManager:
    """
    任务管理器 (TaskManager)
    
    【设计意图】
    支持复杂工程的“分治策略”。普通的 LLM 在一个 prompt 中无法解决庞大的需求。
    TaskManager 允许 Lead Agent 将复杂问题拆解为多个子任务（Task），
    并能定义阻塞关系（Blocked By / Blocks）形成有向无环图 (DAG)。
    
    所有操作均直接落盘至 SQLite 的 `tasks` 表，保证跨线程、跨 Agent 读取状态的一致性。
    """
    def __init__(self):
        pass

    def create(self, subject: str, description: str = "") -> str:
        """创建一个全新的根任务，并初始化其状态为 pending (待认领)"""
        with DB_LOCK:
            cursor = get_db_conn().cursor()
            cursor.execute(
                "INSERT INTO tasks (subject, description, status, blocked_by, blocks, assigned_to) VALUES (?, ?, ?, ?, ?, ?)",
                (subject, description, "pending", "[]", "[]", None)
            )
            get_db_conn().commit()
            return f"Task {cursor.lastrowid} created: {subject}"

    def update(self, task_id: int, status: str = None, add_blocked_by: list = None, add_blocks: list = None) -> str:
        """更新现存任务的状态或依赖树。常用于验证阶段（将 in_progress 标记为 completed）"""
        with DB_LOCK:
            row = get_db_conn().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return f"Task {task_id} not found."
            
            import json
            new_status = status or row['status']
            b_by = json.loads(row['blocked_by'])
            b_down = json.loads(row['blocks'])
            
            if add_blocked_by:
                b_by = list(set(b_by + add_blocked_by))
            if add_blocks:
                b_down = list(set(b_down + add_blocks))
                
            get_db_conn().execute(
                "UPDATE tasks SET status = ?, blocked_by = ?, blocks = ? WHERE id = ?",
                (new_status, json.dumps(b_by), json.dumps(b_down), task_id)
            )
            get_db_conn().commit()
            return f"Task {task_id} updated."

    def claim(self, task_id: int, agent_name: str) -> str:
        """
        认领任务机制。
        因为系统可能存在多个并发的 Sub-Agent，此锁保证任务只能被一个人领走。
        """
        with DB_LOCK:
            row = get_db_conn().execute("SELECT status, assigned_to FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row: return f"Task {task_id} not found."
            if row['status'] != "pending": return f"Task {task_id} is {row['status']} (assigned to {row['assigned_to']})"
            
            get_db_conn().execute("UPDATE tasks SET status = 'in_progress', assigned_to = ? WHERE id = ?", (agent_name, task_id))
            get_db_conn().commit()
            return f"Task {task_id} claimed by {agent_name}."

    def get(self, task_id: int) -> str:
        """精确获取单个任务的详细信息"""
        with DB_LOCK:
            row = get_db_conn().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row: return f"Task {task_id} not found."
            return f"Task {row['id']}: {row['subject']}\nStatus: {row['status']}\nAssigned: {row['assigned_to']}\nDepends on: {row['blocked_by']}\nBlocks: {row['blocks']}\nDesc: {row['description']}"

    def list_all(self) -> str:
        """列出全部任务（通常供 Lead Agent 掌握全局进度使用）"""
        with DB_LOCK:
            rows = get_db_conn().execute("SELECT * FROM tasks").fetchall()
            if not rows: return "No tasks."
            lines = ["Tasks:"]
            for r in rows:
                lines.append(f"[{r['id']}] {r['subject']} ({r['status']}) -> {r['assigned_to'] or 'unassigned'} (deps: {r['blocked_by']})")
            return "\n".join(lines)
