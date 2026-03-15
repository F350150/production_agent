import pytest
from unittest.mock import MagicMock, patch
from skills.builtin.code_review import CodeReviewSkill

def test_code_review_skill_logic():
    """验证代码评审技能的逻辑流程"""
    skill = CodeReviewSkill()
    
    # 准备 Mock 工具集
    mock_read = MagicMock(return_value="def insecure_func():\n    eval('dangerous')")
    mock_bash = MagicMock(return_value="Review output: Potential Security Risk found.")
    handlers = {
        "read_file": mock_read,
        "run_bash": mock_bash,
        "sandbox_bash": mock_bash
    }
    
    # 执行技能
    report = skill.execute(tool_handlers=handlers, path="vuln.py", focus="security")
    
    assert "Code Review Report" in report
    mock_read.assert_called_with(path="vuln.py")
    # 验证是否至少调用了一次分析命令 (bash)
    assert mock_bash.called

def test_skill_input_schema():
    """验证 Skill 的 Schema 定义符合预期"""
    skill = CodeReviewSkill()
    schema = skill.parameters
    assert "type" in schema
    assert "properties" in schema
    assert "path" in schema["properties"]
