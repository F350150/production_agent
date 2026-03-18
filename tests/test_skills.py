"""
技能单元测试 (test_skills.py)

测试新添加的内置技能：debug_explain, generate_test, api_design_review,
dependency_analysis, code_migration
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestDebugExplainSkill:
    """测试调试解释技能"""

    def test_error_type_detection(self):
        """验证能正确识别常见的 Python 错误类型"""
        from skills.builtin.debug_explain import DebugExplainSkill

        skill = DebugExplainSkill()
        traceback = "ModuleNotFoundError: No module named 'requests'"
        result = skill.execute({}, error_traceback=traceback)

        assert "ModuleNotFoundError" in result
        assert "pip install requests" in result

    def test_import_error_handling(self):
        """验证 ImportError 的处理"""
        from skills.builtin.debug_explain import DebugExplainSkill

        skill = DebugExplainSkill()
        traceback = "ImportError: cannot import name 'something' from 'os'"
        result = skill.execute({}, error_traceback=traceback, language="en")

        assert "ImportError" in result
        assert "circular import" in result.lower() or "module" in result.lower()

    def test_syntax_error_explanation(self):
        """验证 SyntaxError 的解释"""
        from skills.builtin.debug_explain import DebugExplainSkill

        skill = DebugExplainSkill()
        traceback = "SyntaxError: invalid syntax"
        result = skill.execute({}, error_traceback=traceback, language="zh")

        assert "SyntaxError" in result
        assert "语法错误" in result

    def test_empty_traceback_error(self):
        """验证空 traceback 返回错误信息"""
        from skills.builtin.debug_explain import DebugExplainSkill

        skill = DebugExplainSkill()
        result = skill.execute({}, error_traceback="")

        assert "Error" in result or "required" in result

    def test_file_location_extraction(self):
        """验证能从堆栈中提取文件位置"""
        from skills.builtin.debug_explain import DebugExplainSkill

        skill = DebugExplainSkill()
        traceback = '''Traceback (most recent call last):
  File "src/main.py", line 42, in <module>
    main()
ValueError: invalid value
'''
        mock_handlers = {
            "read_file": MagicMock(return_value="def main():\n    pass\n")
        }
        result = skill.execute(mock_handlers, error_traceback=traceback)

        assert "main.py" in result or "src/main.py" in result


class TestGenerateTestSkill:
    """测试测试用例生成技能"""

    def test_generates_pytest_format(self):
        """验证生成 pytest 格式的测试"""
        from skills.builtin.generate_test import GenerateTestSkill

        skill = GenerateTestSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''def add(a: int, b: int) -> int:
    return a + b
''')
        }
        result = skill.execute(mock_handlers, target="math_utils.py", test_framework="pytest")

        assert "test_" in result
        assert "pytest" in result or "assert" in result

    def test_function_name_filter(self):
        """验证能针对特定函数生成测试"""
        from skills.builtin.generate_test import GenerateTestSkill

        skill = GenerateTestSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''def add(a, b):
    return a + b

def sub(a, b):
    return a - b
''')
        }
        result = skill.execute(mock_handlers, target="math.py", function_name="add")

        assert "add" in result
        assert "test_add" in result

    def test_handles_non_python_file(self):
        """验证对非 Python 文件返回错误"""
        from skills.builtin.generate_test import GenerateTestSkill

        skill = GenerateTestSkill()
        mock_handlers = {"read_file": MagicMock()}
        result = skill.execute(mock_handlers, target="data.json")

        assert "Error" in result
        assert ".py" in result

    def test_async_function_detection(self):
        """验证能检测异步函数"""
        from skills.builtin.generate_test import GenerateTestSkill

        skill = GenerateTestSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''async def fetch_data(url: str) -> dict:
    return {"url": url}
''')
        }
        result = skill.execute(mock_handlers, target="async_utils.py")

        assert "async" in result.lower() or "await" in result


class TestApiDesignReviewSkill:
    """测试 API 设计审查技能"""

    def test_scores_functions(self):
        """验证对函数进行评分"""
        from skills.builtin.api_design_review import ApiDesignReviewSkill

        skill = ApiDesignReviewSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''def good_function(param: str) -> bool:
    """A well-documented function."""
    return True
''')
        }
        result = skill.execute(mock_handlers, target="good_code.py")

        assert "Score" in result or "100" in result or "Issues" in result

    def test_detects_missing_docstrings(self):
        """验证能检测缺失的文档字符串"""
        from skills.builtin.api_design_review import ApiDesignReviewSkill

        skill = ApiDesignReviewSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''def undocumented():
    pass
''')
        }
        result = skill.execute(mock_handlers, target="bad_code.py")

        assert "docstring" in result.lower() or "missing" in result.lower()

    def test_naming_convention_check(self):
        """验证命名规范检查"""
        from skills.builtin.api_design_review import ApiDesignReviewSkill

        skill = ApiDesignReviewSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''class badClassName:
    pass
''')
        }
        result = skill.execute(mock_handlers, target="naming.py")

        assert "PascalCase" in result or "naming" in result.lower()


class TestDependencyAnalysisSkill:
    """测试依赖分析技能"""

    def test_extracts_imports(self):
        """验证能提取 import 语句"""
        from skills.builtin.dependency_analysis import DependencyAnalysisSkill

        skill = DependencyAnalysisSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''import os
import sys
from pathlib import Path
import requests
''')
        }
        result = skill.execute(mock_handlers, target="example.py")

        assert "import" in result.lower() or "Import" in result
        assert "os" in result
        assert "requests" in result

    def test_detects_local_imports(self):
        """验证能检测本地导入"""
        from skills.builtin.dependency_analysis import DependencyAnalysisSkill

        skill = DependencyAnalysisSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''from . import utils
from ..models import User
''')
        }
        result = skill.execute(mock_handlers, target="module.py")

        assert "local" in result.lower() or "." in result

    def test_identifies_stdlib_modules(self):
        """验证能识别标准库模块"""
        from skills.builtin.dependency_analysis import DependencyAnalysisSkill

        skill = DependencyAnalysisSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''import os
import json
import requests
''')
        }
        result = skill.execute(mock_handlers, target="example.py")

        assert "Standard Library" in result or "stdlib" in result.lower()
        assert "Third-Party" in result or "requests" in result


class TestCodeMigrationSkill:
    """测试代码迁移技能"""

    def test_migration_type_recognition(self):
        """验证能识别迁移类型"""
        from skills.builtin.code_migration import CodeMigrationSkill

        skill = CodeMigrationSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value="print 'hello'")
        }
        result = skill.execute(mock_handlers, target="python2.py", migration_type="python2_to_3")

        assert "Migrated" in result or "print(" in result or "Changes" in result

    def test_flask_to_fastapi_patterns(self):
        """验证 Flask 到 FastAPI 迁移模式"""
        from skills.builtin.code_migration import CodeMigrationSkill

        skill = CodeMigrationSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''from flask import Flask
app = Flask(__name__)
@app.route('/')
def hello():
    return "Hello"
''')
        }
        result = skill.execute(mock_handlers, target="flask_app.py", migration_type="flask_to_fastapi")

        assert "FastAPI" in result or "app = FastAPI" in result or "Migrated" in result

    def test_requests_to_httpx_patterns(self):
        """验证 requests 到 httpx 迁移模式"""
        from skills.builtin.code_migration import CodeMigrationSkill

        skill = CodeMigrationSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value='''import requests
r = requests.get("https://api.example.com")
''')
        }
        result = skill.execute(mock_handlers, target="api_client.py", migration_type="requests_to_httpx")

        assert "httpx" in result or "Migrated" in result

    def test_unknown_migration_type_error(self):
        """验证未知迁移类型返回错误"""
        from skills.builtin.code_migration import CodeMigrationSkill

        skill = CodeMigrationSkill()
        mock_handlers = {"read_file": MagicMock(return_value="code")}
        result = skill.execute(mock_handlers, target="code.py", migration_type="unknown_type")

        assert "Error" in result or "Unknown" in result

    def test_preview_mode_by_default(self):
        """验证默认是预览模式，不写入文件"""
        from skills.builtin.code_migration import CodeMigrationSkill

        skill = CodeMigrationSkill()
        mock_handlers = {
            "read_file": MagicMock(return_value="print 'hello'"),
            "write_file": MagicMock()
        }
        result = skill.execute(mock_handlers, target="python2.py", migration_type="python2_to_3")

        assert "Preview" in result or "apply_changes" in result.lower()


class TestSkillRegistry:
    """测试技能注册中心能否正确发现新技能"""

    def test_new_skills_are_discoverable(self):
        """验证新添加的技能能被 SkillRegistry 发现"""
        from skills.skill_registry import SkillRegistry

        registry = SkillRegistry()
        registry.initialize()

        skill_names = registry.get_skill_names()

        expected_skills = [
            "debug_explain",
            "generate_test",
            "api_design_review",
            "dependency_analysis",
            "code_migration"
        ]

        for skill_name in expected_skills:
            assert skill_name in skill_names, f"Skill '{skill_name}' not found in registry"


class TestCodeReviewSkill:
    """测试代码评审技能 (原有)"""

    def test_code_review_skill_logic(self):
        """验证代码评审技能的逻辑流程"""
        from skills.builtin.code_review import CodeReviewSkill

        skill = CodeReviewSkill()

        mock_read = MagicMock(return_value="def insecure_func():\n    eval('dangerous')")
        mock_bash = MagicMock(return_value="Review output: Potential Security Risk found.")
        handlers = {
            "read_file": mock_read,
            "run_bash": mock_bash,
            "sandbox_bash": mock_bash
        }

        report = skill.execute(tool_handlers=handlers, path="vuln.py", focus="security")

        assert "Code Review Report" in report
        mock_read.assert_called_with(path="vuln.py")
        assert mock_bash.called

    def test_skill_input_schema(self):
        """验证 Skill 的 Schema 定义符合预期"""
        from skills.builtin.code_review import CodeReviewSkill

        skill = CodeReviewSkill()
        schema = skill.parameters
        assert "type" in schema
        assert "properties" in schema
        assert "path" in schema["properties"]
