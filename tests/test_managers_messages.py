import pytest
import json
from unittest.mock import MagicMock, patch
from production_agent.managers.messages import MessageBus

@pytest.fixture
def mock_db(monkeypatch):
    mock_conn = MagicMock()
    monkeypatch.setattr("production_agent.managers.messages.get_db_conn", lambda: mock_conn)
    return mock_conn

def test_message_bus_send(mock_db):
    bus = MessageBus()
    bus.send("Alice", "Bob", "Hello", "message")
    
    # 验证是否插入了数据库
    assert mock_db.execute.called
    args, kwargs = mock_db.execute.call_args
    query = args[0]
    params = args[1]
    assert "INSERT INTO inbox" in query
    # params: (sender, recipient, content, msg_type, meta_str, timestamp)
    assert params[0] == "Alice"
    assert params[1] == "Bob"
    assert params[2] == "Hello"
    assert params[3] == "message"

def test_message_bus_read_inbox(mock_db):
    bus = MessageBus()
    mock_db.execute.return_value.fetchall.return_value = [
        {"id": 1, "sender": "A", "content": "C1", "msg_type": "m", "metadata": "{}", "timestamp": 123},
        {"id": 2, "sender": "B", "content": "C2", "msg_type": "m", "metadata": "{}", "timestamp": 124}
    ]
    
    msgs = bus.read_inbox("Recipient")
    assert len(msgs) == 2
    assert msgs[0]["content"] == "C1"
    
    # 验证是否删除了已读消息
    assert mock_db.execute.call_count >= 2
    delete_query = mock_db.execute.call_args_list[-1][0][0]
    assert "DELETE FROM inbox" in delete_query

def test_message_bus_broadcast(mock_db):
    bus = MessageBus()
    bus.broadcast("Manager", "Work!", ["A", "B"])
    assert mock_db.execute.call_count == 2
