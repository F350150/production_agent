from managers.database import get_db_conn, DB_LOCK
from rich.console import Console

console = Console()

class TaskManager:
    """
    任务管理器 (TaskManager)

    【设计意图】
    支持复杂工程的"分治策略"。普通的 LLM 在一个 prompt 中无法解决庞大的需求。
    TaskManager 允许 Lead Agent 将复杂问题拆解为多个子任务（Task），
    并能定义阻塞关系（Blocked By / Blocks）形成有向无环图 (DAG)。

    所有操作均直接落盘至 SQLite 的 `tasks` 表，保证跨线程、跨 Agent 读取状态的一致性。

    【角色关联系统】
    - 创建任务时可指定期望的角色（required_role）
    - 角色只能认领与自己职责相关的任务
    - 支持按角色筛选任务列表
    """
    def __init__(self):
        pass

    def create(self, subject: str, description: str = "", required_role: str = None) -> str:
        """
        创建一个全新的根任务，并初始化其状态为 pending (待认领)

        参数：
        - subject: 任务标题
        - description: 任务描述
        - required_role: 期望执行此任务的角色（ProductManager, Architect, Coder, QA_Reviewer）
        """
        with DB_LOCK:
            cursor = get_db_conn().cursor()
            cursor.execute(
                "INSERT INTO tasks (subject, description, status, blocked_by, blocks, assigned_to) VALUES (?, ?, ?, ?, ?, ?)",
                (subject, description, "pending", "[]", "[]", None)
            )
            task_id = cursor.lastrowid

            # 如果指定了 required_role，记录到元数据中
            if required_role:
                get_db_conn().execute(
                    "UPDATE tasks SET assigned_to = ? WHERE id = ?",
                    (f"required:{required_role}", task_id)
                )
                get_db_conn().commit()

            msg = f"Task {task_id} created: {subject}" + (f" (required: {required_role})" if required_role else "")
            console.print(f"\n[bold green]✅ [TaskManager] {msg}[/bold green]")
            return msg

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
            msg = f"Task {task_id} updated (status: {new_status})."
            console.print(f"\n[bold green]✅ [TaskManager] {msg}[/bold green]")
            return msg

    def claim(self, task_id: int, agent_name: str, agent_role: str = None) -> str:
        """
        认领任务机制（带角色验证）

        因为系统可能存在多个并发的 Sub-Agent，此锁保证任务只能被一个人领走。

        参数：
        - task_id: 任务 ID
        - agent_name: Agent 名称
        - agent_role: Agent 角色（用于验证是否可以认领此任务）

        【角色验证规则】
        - 如果任务有 required_role，只有匹配的 Agent 可以认领
        - ProductManager 只能认领 required_role 为 ProductManager 或 None 的任务
        - Architect 只能认领 required_role 为 Architect 的任务
        - Coder 只能认领 required_role 为 Coder 的任务
        - QA_Reviewer 只能认领 required_role 为 QA_Reviewer 的任务
        """
        with DB_LOCK:
            row = get_db_conn().execute("SELECT status, assigned_to FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return f"Task {task_id} not found."
            if row['status'] != "pending":
                return f"Task {task_id} is {row['status']} (assigned to {row['assigned_to']})"

            # 角色验证
            if agent_role and row['assigned_to']:
                # 检查 required_role 是否匹配
                assigned_to = row['assigned_to']
                if assigned_to.startswith('required:'):
                    required_role = assigned_to.split(':')[1]
                    role_permission = {
                        "ProductManager": ["ProductManager", None],
                        "Architect": ["Architect"],
                        "Coder": ["Coder"],
                        "QA_Reviewer": ["QA_Reviewer"]
                    }
                    allowed_roles = role_permission.get(agent_role, [])
                    if required_role not in allowed_roles:
                        return f"Task {task_id} requires role '{required_role}' but you are '{agent_role}'. Permission denied."

            get_db_conn().execute("UPDATE tasks SET status = 'in_progress', assigned_to = ? WHERE id = ?", (agent_name, task_id))
            get_db_conn().commit()
            msg = f"Task {task_id} claimed by {agent_name}."
            console.print(f"\n[bold green]✅ [TaskManager] {msg}[/bold green]")
            return msg

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
            if not rows:
                return "No tasks."
            lines = ["Tasks:"]
            for r in rows:
                assigned = r['assigned_to'] or 'unassigned'
                # 解析 required_role
                role_display = ""
                if assigned.startswith('required:'):
                    role_display = f"[requires: {assigned.split(':')[1]}]"
                lines.append(f"[{r['id']}] {r['subject']} ({r['status']}) -> {assigned} {role_display} (deps: {r['blocked_by']})")
            return "\n".join(lines)

    def list_by_role(self, agent_role: str) -> str:
        """
        列出指定角色可以处理的任务

        参数：
        - agent_role: Agent 角色（ProductManager, Architect, Coder, QA_Reviewer）

        返回：
        - 该角色可以认领的任务列表（根据 required_role 过滤）
        """
        with DB_LOCK:
            rows = get_db_conn().execute("SELECT * FROM tasks").fetchall()
            if not rows:
                return "No tasks."

            # 角色权限映射
            role_permission = {
                "ProductManager": ["ProductManager", None],
                "Architect": ["Architect"],
                "Coder": ["Coder"],
                "QA_Reviewer": ["QA_Reviewer"]
            }

            allowed_required_roles = role_permission.get(agent_role, [])
            lines = [f"Tasks available for {agent_role}:"]

            for r in rows:
                # 检查此任务是否可以由该角色处理
                assigned = r['assigned_to']
                if assigned:
                    # 如果已分配且不是 assigned_to 当前角色，跳过
                    if not assigned.startswith('required:') or assigned != f"required:{agent_role}":
                        continue

                    # 检查 required_role 是否在允许列表中
                    if assigned.startswith('required:'):
                        required_role = assigned.split(':')[1]
                        if required_role not in allowed_required_roles:
                            continue

                lines.append(f"[{r['id']}] {r['subject']} ({r['status']}) -> {assigned or 'unassigned'} (deps: {r['blocked_by']})")

            if len(lines) == 1:  # 只有标题行
                return f"No tasks available for {agent_role}."
            return "\n".join(lines)
