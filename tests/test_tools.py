import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from production_agent.tools.ast_tools import ASTTools
from production_agent.tools.system_tools import SystemTools

def test_ast_parse_python():
    """测试 AST 工具是否能正确解析 Python 文件结构"""
    # 创建一个内存中的测试文件
    test_code = """
class MyTest:
    def method_one(self):
        pass

def top_level_func(a, b):
    return a + b
"""
    # ASTTools._parse_python 接受 Path 对象
    mock_path = MagicMock(spec=Path)
    mock_path.read_text.return_value = test_code
    
    structure = ASTTools._parse_python(mock_path)
    
    assert "class MyTest:" in structure
    assert "def method_one" in structure
    assert "def top_level_func" in structure

def test_read_file_tool():
    """测试读取文件工具"""
    with patch("builtins.open", MagicMock(return_value=MagicMock(__enter__=lambda s: MagicMock(read=lambda: "file content")))):
        with patch("pathlib.Path.is_file", return_value=True):
            with patch("pathlib.Path.read_text", return_value="file content"):
                content = SystemTools.read_file(path="any.txt")
                assert content == "file content"

def test_write_file_tool(tmp_path):
    """测试写入文件工具（使用 tmp_path 真实写入）"""
    test_file = tmp_path / "output.txt"
    # 我们需要 patch SystemTools.WORKDIR 否则它会去 WORKSPACE_DIR
    with patch("production_agent.tools.system_tools.WORKDIR", tmp_path):
        result = SystemTools.write_file(path="output.txt", content="hello world")
    
    assert "Success" in result
    assert test_file.read_text() == "hello world"

def test_system_info_noop():
    """SystemTools 暂无 get_system_info，仅为占位"""
    pass
