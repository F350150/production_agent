import pytest
from unittest.mock import MagicMock
from production_agent.skills.builtin.web_research import WebResearchSkill

def test_web_research_skill_full_flow():
    """测试完整的 WebResearchSkill 流程（搜索+抓取）"""
    skill = WebResearchSkill()
    
    # 模拟工具 handlers
    mock_web_search = MagicMock(return_value="Results: https://example.com/page1")
    mock_fetch_url = MagicMock(return_value="Detailed page content here")
    
    handlers = {
        "web_search": mock_web_search,
        "fetch_url": mock_fetch_url
    }
    
    result = skill.execute(tool_handlers=handlers, query="test", fetch_pages=1)
    
    assert "Web Research Report" in result
    assert "Results: https://example.com/page1" in result
    assert "Detailed page content here" in result
    
    mock_web_search.assert_called_once()
    mock_fetch_url.assert_called_once_with(url="https://example.com/page1")

def test_web_research_skill_missing_tool():
    """测试缺少工具时的错误处理"""
    skill = WebResearchSkill()
    handlers = {}
    result = skill.execute(tool_handlers=handlers, query="test")
    assert "Error" in result
    assert "web_search tool is not available" in result

def test_web_research_skill_fetch_error():
    """测试抓取失败时的处理"""
    skill = WebResearchSkill()
    
    mock_web_search = MagicMock(return_value="https://fail.com")
    mock_fetch_url = MagicMock(side_effect=Exception("Timeout"))
    
    handlers = {
        "web_search": mock_web_search,
        "fetch_url": mock_fetch_url
    }
    
    result = skill.execute(tool_handlers=handlers, query="test", fetch_pages=1)
    assert "Fetch failed: Timeout" in result
