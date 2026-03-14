import os
import sqlite3
import threading
import pytest
from production_agent.managers.database import get_db_conn, DB_LOCK, close_db

@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    """为每个测试隔离数据库"""
    db_file = tmp_path / "test.db"
    # 注入测试用的临时路径
    monkeypatch.setattr("production_agent.managers.database.DB_PATH", str(db_file))
    # 强制重置全局连接，确保使用新生成的连接
    monkeypatch.setattr("production_agent.managers.database._DB_CONN", None)
    yield
    # 测试结束后关闭并再次重置
    close_db()
    monkeypatch.setattr("production_agent.managers.database._DB_CONN", None)

def test_db_initialization():
    """验证数据库初始化并能创建核心表"""
    # 强制在测试目录下创建一个临时数据库
    test_db = "data/test_db_init.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    
    try:
        # get_db_conn 会自动调用 _init_db
        conn = get_db_conn()
        cursor = conn.cursor()
        
        # 验证核心表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        assert "sessions" in tables
        assert "tasks" in tables
        assert "inbox" in tables
        assert "metrics" in tables
    finally:
        pass # 不要在这里关闭全局连接，否则后续测试会失败

def test_db_lock_concurrency():
    """验证 DB_LOCK (RLock) 在多线程环境下的有效性"""
    results = []
    
    def worker():
        try:
            with DB_LOCK:
                conn = get_db_conn()
                # 再次确认连接没关
                conn.execute("SELECT 1")
                results.append(True)
        except Exception:
            results.append(False)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # 只验证并发获取连接和执行 SELECT 无异常
    assert all(results)
    assert len(results) == 10

def test_session_save_and_load():
    """验证会话数据的持久化与恢复"""
    session_id = "test_session_123"
    messages = [{"role": "user", "content": "Hello DB"}]
    
    from production_agent.managers.database import save_session, load_session
    
    with DB_LOCK:
        save_session(session_id, messages)
    
    loaded_msgs = load_session(session_id)
    assert loaded_msgs == messages
    
    # 测试覆盖更新
    new_messages = messages + [{"role": "assistant", "content": "Hi there"}]
    with DB_LOCK:
        save_session(session_id, new_messages)
    
    loaded_again = load_session(session_id)
    assert len(loaded_again) == 2
    assert loaded_again[1]["content"] == "Hi there"

def test_token_usage_and_report():
    """验证 Token 计数与报告打印"""
    from production_agent.managers.database import record_token_usage, print_cost_report
    
    # 记录一些使用量
    record_token_usage(1000, 500)
    record_token_usage(500, 500)
    
    # 验证是否能成功打印报告而不崩溃
    print_cost_report()
    
    # 验证数据库中数据
    conn = get_db_conn()
    row_in = conn.execute("SELECT value FROM metrics WHERE key = 'input_tokens'").fetchone()
    assert row_in["value"] == 1500.0

def test_clear_session():
    """验证清除会话数据"""
    from production_agent.managers.database import save_session, load_session, clear_session
    sid = "clear_me"
    save_session(sid, [{"r": "u", "c": "x"}])
    assert len(load_session(sid)) == 1
    
    clear_session(sid)
    assert len(load_session(sid)) == 0

def test_close_db_idempotency():
    """验证多次关闭数据库无碍"""
    from production_agent.managers.database import close_db
    close_db()
    close_db() # 应该不报错
