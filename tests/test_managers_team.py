import pytest
from unittest.mock import MagicMock
from managers.team import TeammateManager

@pytest.fixture
def mock_db(monkeypatch):
    mock_conn = MagicMock()
    monkeypatch.setattr("managers.team.get_db_conn", lambda: mock_conn)
    return mock_conn

def test_team_manager_spawn_new(mock_db, monkeypatch):
    monkeypatch.setattr("asyncio.create_task", MagicMock())
    bus = MagicMock()
    tm = TeammateManager(bus, MagicMock())
    
    # 模拟数据库中不存在同名成员
    mock_db.execute.return_value.fetchone.return_value = None
    
    res = tm.spawn("AgentA", "Coder", "Do stuff")
    assert "spawned" in res
    assert mock_db.execute.call_count >= 2 # SELECT + INSERT + UPDATE

def test_team_manager_spawn_duplicate(mock_db):
    bus = MagicMock()
    tm = TeammateManager(bus, MagicMock())
    
    # 模拟存在同名成员
    mock_db.execute.return_value.fetchone.return_value = {"name": "AgentA"}
    
    res = tm.spawn("AgentA", "Coder", "Do stuff")
    assert "already exists" in res

def test_team_manager_list_all(mock_db):
    tm = TeammateManager(None, None)
    mock_db.execute.return_value.fetchall.return_value = [
        {"name": "A1", "role": "R1", "status": "S1"},
        {"name": "A2", "role": "R2", "status": "S2"}
    ]
    
    report = tm.list_all()
    assert "A1 (R1): S1" in report
    assert "A2 (R2): S2" in report

def test_team_manager_list_empty(mock_db):
    tm = TeammateManager(None, None)
    mock_db.execute.return_value.fetchall.return_value = []
    assert tm.list_all() == "No teammates."

def test_team_manager_member_names(mock_db):
    tm = TeammateManager(None, None)
    mock_db.execute.return_value.fetchall.return_value = [{"name": "N1"}, {"name": "N2"}]
    assert tm.member_names() == ["N1", "N2"]
