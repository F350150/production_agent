import json
import time
from managers.database import get_db_conn, DB_LOCK
from rich.console import Console

console = Console()

# 预定义的合法消息类型，防止随意广播导致解析崩溃
VALID_MSG_TYPES = {"message", "task_assignment", "plan_review_request", "plan_approval_response", "shutdown_request", "shutdown", "handover"}

class MessageBus:
    """
    消息事件总线 (Event/Message Bus)
    """
    def send(self, sender: str, recipient: str, content: str, msg_type: str = "message", metadata: dict = None) -> str:
        if msg_type not in VALID_MSG_TYPES:
            return f"Error: Invalid message type '{msg_type}'"
        
        meta_str = json.dumps(metadata or {})
        with DB_LOCK:
            get_db_conn().execute(
                "INSERT INTO inbox (sender, recipient, content, msg_type, metadata, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (sender, recipient, content, msg_type, meta_str, time.time())
            )
            get_db_conn().commit()
            
        console.print(f"\n[bold blue]📬 [MessageBus] Sender '{sender}' sent a '{msg_type}' message to '{recipient}'.[/bold blue]")
        return f"Message sent to {recipient}."

    def broadcast(self, sender: str, content: str, recipient_list: list) -> str:
        """群发消息 API：主管通知全员时使用"""
        for r in recipient_list:
            self.send(sender, r, content, "message")
        console.print(f"\n[bold blue]📢 [MessageBus] Sender '{sender}' broadcasted to {len(recipient_list)} agents.[/bold blue]")
        return f"Broadcasted to {len(recipient_list)} agents."

    def read_inbox(self, recipient: str) -> list:
        """
        读取并排出 (Pop) 邮箱中的信息。
        """
        with DB_LOCK:
            rows = get_db_conn().execute("SELECT * FROM inbox WHERE recipient = ? ORDER BY timestamp ASC", (recipient,)).fetchall()
            if not rows:
                return []
            
            msgs = []
            for r in rows:
                msgs.append({
                    "id": r["id"],
                    "from": r["sender"],
                    "content": r["content"],
                    "type": r["msg_type"],
                    "metadata": json.loads(r["metadata"]),
                    "timestamp": r["timestamp"]
                })
            
            get_db_conn().execute("DELETE FROM inbox WHERE recipient = ?", (recipient,))
            get_db_conn().commit()
            return msgs
