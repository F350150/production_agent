import os
import sqlite3
import json
import time
from pathlib import Path
from filelock import FileLock

# ==============================================================================
# 核心数据层 (Data Layer) - SQLite 数据库管理模块
# 
# 【为什么需要这个模块？】
# 在多 Agent 并发执行时（例如 Lead Agent 正在思考，同时后台有 Explore 探路 Agent 在扫描文件），
# 如果它们同时向本地普通的 JSON 文件写入数据，极易发生“写入冲突”（Race Conditions）导致 JSON 文件损坏或清空。
#
# 引入 SQLite 作为所有状态（任务、消息、消费记录、团队状态、断点续传）的统一持久化中心，具有以下优势：
# 1. 事务安全性 (ACID)：保证每次写入完整，不会损坏。
# 2. 并发性控制：通过 threading.Lock 和 SQLite 自身的锁机制处理多线程读写。
# 3. 结构化查询：更易于实现如“统计 Token 消耗”、“精准提取特定任务”等复杂功能。
# ==============================================================================

from utils.paths import WORKSPACE_DIR, TEAM_DIR, DB_PATH, ensure_dirs

# 确保存放数据的目录存在
ensure_dirs()

# ------------------------------------------------------------------------------
# 数据库连接初始化与表定义
# ------------------------------------------------------------------------------
def get_db():
    """
    建立 sqlite3 数据库连接，并确保所需的数据表均已创建。
    启用了 check_same_thread=False 允许在不同的线程中共享。
    设置 timeout (busy_timeout) 防止锁等待死循环。
    """
    # 增加 timeout 到 30 秒，由于 user 运行了多个实例，这非常关键
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    # 设置返回行为字典 dict (通过列名访问数据而不是索引下标)
    conn.row_factory = sqlite3.Row
    
    # 启用 WAL 模式提高并发读写性能
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
        
    # 初始化表结构
    _init_db(conn)
    return conn

def _init_db(conn):
    """
    初始化数据库表结构。
    """
    with conn:
        # tasks 表: 保存 Agent 需要解决的具体任务，支持任务阻塞树（前置/后置条件）
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT,
                description TEXT,
                status TEXT,
                blocked_by TEXT,
                blocks TEXT,
                assigned_to TEXT
            )
        ''')
        # inbox 表: 消息总线，处理不同子系统/Agent 以及人类用户之间的信息投递
        conn.execute('''
            CREATE TABLE IF NOT EXISTS inbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                recipient TEXT,
                content TEXT,
                msg_type TEXT,
                metadata TEXT,
                timestamp REAL
            )
        ''')
        # teammates 表: 记录被动态生成的后台打工子 Agent 的状态
        conn.execute('''
            CREATE TABLE IF NOT EXISTS teammates (
                name TEXT PRIMARY KEY,
                role TEXT,
                status TEXT
            )
        ''')
        # sessions 表: [状态恢复] 用于断点续传。保存对话的 messages 数组
        conn.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                messages TEXT,
                updated_at REAL
            )
        ''')
        # metrics 表: [成本控制] 用于永久记录并统计模型消耗的 Input/Output Token 数量
        conn.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                key TEXT PRIMARY KEY,
                value REAL
            )
        ''')
    return conn

# 全局单例占位符
_DB_CONN = None
DB_LOCK = FileLock(str(DB_PATH.with_suffix('.sqlite.lock')))

def get_db_conn():
    """
    懒加载获取数据库连接。确保在模型导入时不会触发磁盘 I/O 和表创建。
    """
    global _DB_CONN
    with DB_LOCK:
        if _DB_CONN is None:
            _DB_CONN = get_db()
        return _DB_CONN

# ------------------------------------------------------------------------------
# 状态恢复管理器 (Session Management)
# ------------------------------------------------------------------------------
def save_session(session_id: str, messages: list):
    """
    【断点续传核心机制】将当前 Agent 的完整记忆（messages）全量序列化落盘。
    无论任何时候用户按下 Ctrl+C，这里的记录都能确保上次工作不会丢失。
    """
    try:
        # 将结构化的消息列表转换为纯字符串
        data = json.dumps(messages, default=str)
        with DB_LOCK:
            get_db_conn().execute(
                "INSERT OR REPLACE INTO sessions (id, messages, updated_at) VALUES (?, ?, ?)",
                (session_id, data, time.time())
            )
            get_db_conn().commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to save session: {e}")

def load_session(session_id: str) -> list:
    """提取上一次未完结的对话历史。"""
    with DB_LOCK:
        row = get_db_conn().execute("SELECT messages FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row:
            try:
                return json.loads(row["messages"])
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to load session: {e}")
    return []

def clear_session(session_id: str):
    """用于 `/clear` 场景，彻底抹除特定 Agent 的记忆历史。"""
    with DB_LOCK:
        get_db_conn().execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        get_db_conn().commit()

# ------------------------------------------------------------------------------
# 成本监控与熔断记录管理器 (Cost Metrics)
# ------------------------------------------------------------------------------
def record_token_usage(in_tokens: int, out_tokens: int):
    """
    记录每一次 LLM API 返回的结果。
    因为单次对话结束并不代表生命周期结束，这些累加总数字能告诉用户真正的 API 账单花费了多少。
    """
    with DB_LOCK:
        row_in = get_db_conn().execute("SELECT value FROM metrics WHERE key = 'input_tokens'").fetchone()
        row_out = get_db_conn().execute("SELECT value FROM metrics WHERE key = 'output_tokens'").fetchone()
        curr_in = row_in["value"] if row_in else 0.0
        curr_out = row_out["value"] if row_out else 0.0
        
        get_db_conn().execute("INSERT OR REPLACE INTO metrics (key, value) VALUES ('input_tokens', ?)", (curr_in + in_tokens,))
        get_db_conn().execute("INSERT OR REPLACE INTO metrics (key, value) VALUES ('output_tokens', ?)", (curr_out + out_tokens,))
        get_db_conn().commit()

def print_cost_report():
    """打印消费账单（按 Claude 3.5 Sonnet 的商业标准估值，防止意外超支）。"""
    with DB_LOCK:
        row_in = get_db_conn().execute("SELECT value FROM metrics WHERE key = 'input_tokens'").fetchone()
        row_out = get_db_conn().execute("SELECT value FROM metrics WHERE key = 'output_tokens'").fetchone()
        curr_in = row_in["value"] if row_in else 0.0
        curr_out = row_out["value"] if row_out else 0.0
        
    # 定价公式（依据模型会有所不同）： Input $3.00 / 1M | Output $15.00 / 1M
    cost = (curr_in / 1_000_000) * 3.0 + (curr_out / 1_000_000) * 15.0
    
    from rich.table import Table
    from rich.console import Console
    console = Console()
    
    table = Table(title="💎 Token Usage & Cost Report", border_style="yellow")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="green")
    
    table.add_row("Tokens In (Prompt)", f"{int(curr_in):,}")
    table.add_row("Tokens Out (Completion)", f"{int(curr_out):,}")
    table.add_row("Total Cost (USD)", f"${cost:.4f}")
    
    console.print(table)

def close_db():
    """优雅关闭数据库连接，防止 ResourceWarning 和数据损坏。"""
    with DB_LOCK:
        try:
            if _DB_CONN:
                _DB_CONN.close()
            print("\033[90m[Database connection closed gracefully]\033[0m")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error closing database: {e}")
