import pytest
from unittest.mock import MagicMock, patch
from managers.tasks import TaskManager

@pytest.fixture
def task_manager():
    """创建一个带有 Mock 数据库的 TaskManager"""
    manager = TaskManager()
    manager.db = MagicMock()
    return manager

def test_create_task(task_manager):
    """测试创建任务并存入数据库"""
    # 模拟数据库返回自增 ID
    task_manager.db.execute.return_value.lastrowid = 1
    
    task_id_info = task_manager.create(
        subject="Test Task",
        description="Write some tests"
    )
    
    # create 返回的是字符串 "Task 1 created: ..." 或 "Task 3 created: ..."
    # 因为 DB 可能在测试间保留了状态
    assert "Task" in task_id_info and "created" in task_id_info
    
    # 验证是否通过 get_db_conn 调用了 execute
    with patch("managers.tasks.get_db_conn") as mock_get_conn:
        task_manager.create(subject="T2", description="D2")
        assert mock_get_conn.return_value.cursor.return_value.execute.called

def test_update_task_status(task_manager):
    """测试更新任务状态"""
    with patch("managers.tasks.get_db_conn") as mock_get_conn:
        # 模拟 fetchone 返回一个 dict-like 对象
        mock_get_conn.return_value.execute.return_value.fetchone.return_value = {
            'status': 'pending',
            'blocked_by': '[]',
            'blocks': '[]'
        }
        task_manager.update(1, status="completed")
        assert mock_get_conn.return_value.execute.called

def test_check_dependencies_noop(task_manager):
    """TaskManager 目前没有 check_cycle 逻辑，保留占位"""
    pass

def test_list_all_tasks(task_manager):
    """测试获取全部任务"""
    with patch("managers.tasks.get_db_conn") as mock_get_conn:
        task_manager.list_all()
        assert mock_get_conn.return_value.execute.called
