import pytest
import time
from unittest.mock import MagicMock, patch
from production_agent.managers.background import BackgroundManager

def test_background_manager_run_completed():
    """测试后台任务运行成功"""
    bm = BackgroundManager()
    
    # 模拟 subprocess.run
    with patch("subprocess.run") as mock_run:
        mock_result = MagicMock()
        mock_result.stdout = "output"
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        msg = bm.run("echo hello", timeout=1)
        assert "started" in msg
        
        # 等待线程完成并把结果放进队列
        # 因为是真实线程，我们简单等待一下
        start_time = time.time()
        results = []
        while time.time() - start_time < 2:
            results = bm.drain()
            if results: break
            time.sleep(0.1)
            
        assert len(results) == 1
        assert results[0]["status"] == "completed"
        assert "output" in results[0]["result"]

def test_background_manager_check():
    """测试状态检查"""
    bm = BackgroundManager()
    with patch("threading.Thread") as mock_thread:
        mock_t = MagicMock()
        mock_t.is_alive.return_value = True
        mock_thread.return_value = mock_t
        
        bm.run("long_cmd")
        status = bm.check()
        assert "Active tasks" in status

def test_background_manager_drain_empty():
    """测试空队列 drain"""
    bm = BackgroundManager()
    assert bm.drain() == []
