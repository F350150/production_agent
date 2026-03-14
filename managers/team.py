from managers.database import get_db_conn, DB_LOCK

class TeammateManager:
    """
    后台团队成员管理器 (TeammateManager)
    
    【设计意图】
    Lead Agent 面临复杂问题时可能会分身乏术。
    通过这个类，主管可以“招募”多个打工 Agent 在独立的线程（或容器）中并行 work。
    这个管理器主要负责维护这些后台打工机器人的生命周期和当前状态字典。
    """
    def __init__(self, bus, task_mgr):
        from managers.messages import MessageBus
        from managers.tasks import TaskManager
        self.bus = bus
        self.task_mgr = task_mgr
        
    def _set_status(self, name: str, status: str):
        """原子级状态更新：防止状态幻读"""
        with DB_LOCK:
            get_db_conn().execute("UPDATE teammates SET status = ? WHERE name = ?", (status, name))
            get_db_conn().commit()

    def spawn(self, name: str, role: str, prompt: str) -> str:
        """
        唤起一个新的后台常驻打工节点。
        """
        with DB_LOCK:
            row = get_db_conn().execute("SELECT * FROM teammates WHERE name = ?", (name,)).fetchone()
            if row:
                return f"Teammate {name} already exists."
            get_db_conn().execute(
                "INSERT INTO teammates (name, role, status) VALUES (?, ?, ?)",
                (name, role, "starting")
            )
            get_db_conn().commit()
            
        self._set_status(name, "working")
        return f"Teammate {name} ({role}) spawned."

    def list_all(self) -> str:
        """获取整个团队的工位快照表"""
        with DB_LOCK:
            rows = get_db_conn().execute("SELECT * FROM teammates").fetchall()
        if not rows: return "No teammates."
        lines = [f"Team: default"]
        for m in rows:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list:
        with DB_LOCK:
            rows = get_db_conn().execute("SELECT name FROM teammates").fetchall()
        return [m["name"] for m in rows]
