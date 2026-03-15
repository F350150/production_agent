"""
Skill 注册中心单元测试 (test_skill_registry.py)

测试策略：完全不依赖 LLM API 和网络，通过 mock tool_handlers 验证技能系统的正确性。
"""

import pytest
from unittest.mock import MagicMock, patch


class TestSkillRegistry:
    """测试 SkillRegistry 自动发现和注册功能"""

    def setup_method(self):
        """每个测试前重置 SkillRegistry 单例状态（确保测试间完全隔离）"""
        import importlib
        # 兼容两种导入方式：作为包还是直接运行
        try:
            sreg_module = importlib.import_module("skills.skill_registry")
        except ImportError:
            sreg_module = importlib.import_module("skills.skill_registry")
        RegistryClass = sreg_module.SkillRegistry
        # 彻底重置单例类状态，避免跨测试状态污染
        RegistryClass._instance = None
        RegistryClass._initialized = False
        RegistryClass._skills = {}
        # 重新实例化（触发 __new__ 创建全新实例）
        self.registry = RegistryClass()
        self.registry._skills = {}  # 确保实例有独立的字典引用

    def test_initialize_discovers_builtin_skills(self):
        """验证 initialize() 可以自动发现内置技能"""
        self.registry.initialize()
        names = self.registry.get_skill_names()
        assert "web_research" in names, f"web_research not found in {names}"
        assert "code_review" in names, f"code_review not found in {names}"

    def test_idempotent_initialization(self):
        """验证多次调用 initialize() 不会重复注册技能"""
        self.registry.initialize()
        count_first = len(self.registry.get_skill_names())
        self.registry.initialize()  # 第二次调用
        count_second = len(self.registry.get_skill_names())
        assert count_first == count_second

    def test_get_skill_tool_schema_structure(self):
        """验证 use_skill 工具的 Schema 结构符合 Anthropic 格式"""
        self.registry.initialize()
        schema = self.registry.get_skill_tool_schema()
        assert schema is not None
        assert schema["name"] == "use_skill"
        assert "input_schema" in schema
        props = schema["input_schema"]["properties"]
        assert "skill_name" in props
        assert "parameters" in props
        # skill_name 应该有枚举约束
        assert "enum" in props["skill_name"]
        assert "web_research" in props["skill_name"]["enum"]
        assert "code_review" in props["skill_name"]["enum"]

    def test_get_skill_handler_unknown_skill(self):
        """验证对未知技能返回有意义的错误信息而非抛出异常"""
        self.registry.initialize()
        mock_handlers = {}
        handler = self.registry.get_skill_handler(mock_handlers)
        result = handler(skill_name="nonexistent_skill", parameters={})
        assert "Error" in result or "Unknown" in result

    def test_no_skills_returns_none_schema(self):
        """验证没有技能时 get_skill_tool_schema 返回 None（不暴露空工具给 LLM）"""
        # 已初始化但 _skills 为空
        self.registry._initialized = True
        self.registry._skills = {}
        schema = self.registry.get_skill_tool_schema()
        assert schema is None


class TestWebResearchSkill:
    """测试 WebResearchSkill 的执行逻辑（Mock 底层工具）"""

    def setup_method(self):
        from skills.builtin.web_research import WebResearchSkill
        self.skill = WebResearchSkill()

    def test_execute_missing_query_returns_error(self):
        """缺少 query 参数时应返回错误信息"""
        result = self.skill.execute(tool_handlers={})
        assert "Error" in result

    def test_execute_missing_web_search_tool_returns_error(self):
        """当 web_search 工具不可用时，应返回友好错误"""
        result = self.skill.execute(tool_handlers={}, query="test topic")
        assert "Error" in result or "not available" in result

    def test_execute_calls_web_search(self):
        """验证 execute 会调用 web_search，并将结果纳入报告"""
        mock_search = MagicMock(return_value="Result1: https://example.com snippet text")
        mock_fetch = MagicMock(return_value="Full page content here")
        handlers = {"web_search": mock_search, "fetch_url": mock_fetch}

        result = self.skill.execute(tool_handlers=handlers, query="MCP protocol", max_results=5, fetch_pages=1)

        mock_search.assert_called_once_with(query="MCP protocol", max_results=5)
        assert "Web Research Report" in result
        assert "MCP protocol" in result

    def test_execute_calls_fetch_url_for_urls_in_results(self):
        """验证 execute 会对搜索结果中的 URL 调用 fetch_url"""
        mock_search = MagicMock(return_value="Check this https://docs.example.com/api for details")
        mock_fetch = MagicMock(return_value="Page content")
        handlers = {"web_search": mock_search, "fetch_url": mock_fetch}

        self.skill.execute(tool_handlers=handlers, query="test", fetch_pages=1)

        mock_fetch.assert_called_once_with(url="https://docs.example.com/api")

    def test_execute_gracefully_handles_fetch_failure(self):
        """fetch_url 失败时不应中断整体报告生成"""
        mock_search = MagicMock(return_value="See https://example.com for info")
        mock_fetch = MagicMock(side_effect=Exception("Connection refused"))
        handlers = {"web_search": mock_search, "fetch_url": mock_fetch}

        result = self.skill.execute(tool_handlers=handlers, query="test", fetch_pages=1)
        # 应该包含失败提示，但不影响报告整体生成
        assert "Fetch failed" in result or "Connection refused" in result


class TestCodeReviewSkill:
    """测试 CodeReviewSkill 的执行逻辑（Mock 底层工具）"""

    def setup_method(self):
        from skills.builtin.code_review import CodeReviewSkill
        self.skill = CodeReviewSkill()

    def test_execute_missing_path_returns_error(self):
        """缺少 path 参数时应返回错误信息"""
        result = self.skill.execute(tool_handlers={})
        assert "Error" in result

    def test_execute_reads_file_content(self):
        """验证 execute 会读取指定文件"""
        mock_read = MagicMock(return_value="def hello():\n    return 'world'\n")
        mock_sandbox = MagicMock(return_value="0 errors")
        handlers = {"read_file": mock_read, "sandbox_bash": mock_sandbox}

        result = self.skill.execute(
            tool_handlers=handlers,
            path="/tmp/test.py",
            run_tests=False
        )

        mock_read.assert_called_once_with(path="/tmp/test.py")
        assert "Code Review Report" in result

    def test_execute_runs_lint(self):
        """验证 execute 会触发 sandbox_bash 进行 lint"""
        mock_read = MagicMock(return_value="print('hello')")
        mock_sandbox = MagicMock(return_value="0 violations")
        handlers = {"read_file": mock_read, "sandbox_bash": mock_sandbox}

        self.skill.execute(tool_handlers=handlers, path="/tmp/test.py", run_tests=False)

        # sandbox_bash 应至少被调用一次（lint）
        assert mock_sandbox.call_count >= 1
        # 验证 flake8 命令被包含在调用中
        call_args = str(mock_sandbox.call_args_list)
        assert "flake8" in call_args

    def test_execute_falls_back_to_run_bash_when_no_sandbox(self):
        """当 sandbox_bash 不可用时，应降级使用 run_bash"""
        mock_read = MagicMock(return_value="x = 1")
        mock_bash = MagicMock(return_value="ok")
        handlers = {"read_file": mock_read, "run_bash": mock_bash}

        result = self.skill.execute(tool_handlers=handlers, path="/tmp/test.py", run_tests=False)

        mock_bash.assert_called()
        assert "Code Review Report" in result
