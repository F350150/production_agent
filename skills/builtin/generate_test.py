"""
内置技能：测试用例生成 (Generate Test Skill)

【设计意图】
为指定的函数或文件自动生成单元测试用例，帮助开发者快速建立测试覆盖。
使用 AST 解析提取函数签名和参数类型，自动生成 pytest 格式的测试代码。

步骤：
    1. 读取目标文件，通过 AST 解析提取函数/类定义
    2. 分析函数签名（参数名、默认值、类型注解）
    3. 生成符合 pytest 规范的测试用例模板
    4. 可选择直接写入测试文件
"""

import ast
import logging
import re
from pathlib import Path

from skills.base import Skill

logger = logging.getLogger(__name__)


class GenerateTestSkill(Skill):
    """测试用例生成技能：为函数/类自动生成 pytest 测试模板"""

    name = "generate_test"
    description = (
        "Generate pytest unit test templates for a given function or class. "
        "Uses AST parsing to extract signatures and type hints. "
        "Saves multiple round-trips compared to manual test writing."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "File path to analyze (e.g., 'src/utils.py') or function name to test"
            },
            "function_name": {
                "type": "string",
                "description": "Specific function name to generate tests for (optional, tests all if not set)"
            },
            "test_framework": {
                "type": "string",
                "description": "Test framework to use",
                "enum": ["pytest", "unittest", "doctest"],
                "default": "pytest"
            },
            "write_to_file": {
                "type": "boolean",
                "description": "Whether to write tests directly to a test file",
                "default": False
            }
        },
        "required": ["target"]
    }

    def execute(self, tool_handlers: dict, **kwargs) -> str:
        target = kwargs.get("target", "")
        function_name = kwargs.get("function_name", "")
        test_framework = kwargs.get("test_framework", "pytest")
        write_to_file = kwargs.get("write_to_file", False)

        if not target:
            return "Error: 'target' parameter is required for generate_test skill."

        read_file = tool_handlers.get("read_file")
        if not read_file:
            return "Error: read_file tool is not available."

        try:
            content = read_file(file_path=target)
        except Exception as e:
            return f"Error: Failed to read target file '{target}': {e}"

        if not target.endswith('.py'):
            return f"Error: Only Python files (.py) are supported for test generation."

        report_lines = [
            f"# 🧪 Test Generation Report",
            f"",
            f"**Target**: `{target}`",
            f"**Function**: {function_name or 'All functions'}",
            f"**Framework**: `{test_framework}`",
            f""
        ]

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return f"Error: Cannot parse '{target}' - syntax error at line {e.lineno}: {e.msg}"

        functions = self._extract_functions(tree, function_name)

        if not functions:
            report_lines.append("## ⚠️ No Functions Found")
            report_lines.append("No functions were extracted from the target file.")
            return "\n".join(report_lines)

        report_lines.append(f"## Generated Tests")
        report_lines.append(f"")

        all_test_code = []
        for func_info in functions:
            test_code = self._generate_test_code(func_info, test_framework)
            all_test_code.append(test_code)

            report_lines.append(f"### 📝 `{func_info['name']}()`")
            report_lines.append(f"**Location**: Line {func_info['lineno']}")
            report_lines.append(f"**Parameters**: {', '.join(func_info['params']) or 'None'}")
            if func_info['returns']:
                report_lines.append(f"**Returns**: `{func_info['returns']}`")
            report_lines.append(f"")
            report_lines.append(f"```python")
            report_lines.append(test_code)
            report_lines.append(f"```")
            report_lines.append(f"")

        if write_to_file:
            test_file = self._generate_test_filename(target, test_framework)
            write_file = tool_handlers.get("write_file")
            if write_file:
                try:
                    full_test_code = self._wrap_with_imports("\n\n".join(all_test_code), target)
                    write_file(file_path=test_file, content=full_test_code)
                    report_lines.append(f"## ✅ Tests Written")
                    report_lines.append(f"Test file created: `{test_file}`")
                except Exception as e:
                    report_lines.append(f"## ❌ Write Failed")
                    report_lines.append(f"Could not write to file: {e}")
            else:
                report_lines.append(f"## ⚠️ Write Skipped")
                report_lines.append(f"write_file tool not available. Showing inline tests only.")

        report_lines.append(f"---")
        report_lines.append(f"_Test generation completed by GenerateTestSkill_")

        return "\n".join(report_lines)

    def _extract_functions(self, tree: ast.AST, function_name: str) -> list[dict]:
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if function_name and node.name != function_name:
                    continue
                if node.name.startswith('_') and not function_name:
                    continue

                params = []
                param_types = []
                returns = ""

                for arg in node.args.args:
                    param_name = arg.arg
                    param_type = self._get_type_annotation(arg.annotation)
                    params.append(param_name)
                    param_types.append(param_type or "Any")

                if node.returns:
                    returns = self._get_type_annotation(node.returns)

                functions.append({
                    'name': node.name,
                    'lineno': node.lineno,
                    'params': params,
                    'param_types': param_types,
                    'returns': returns,
                    'is_async': isinstance(node, ast.AsyncFunctionDef),
                    'decorators': [self._get_decorator_name(d) for d in node.decorator_list]
                })
        return functions

    def _get_type_annotation(self, annotation: ast.AST) -> str:
        if annotation is None:
            return ""
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(annotation, ast.BuiltinUnionType):
            return " | ".join(self._get_type_annotation(x) for x in annotation.lefts) + " | " + self._get_type_annotation(annotation.right)
        if isinstance(annotation, ast.BinOp):
            return self._get_type_annotation(annotation.left) + " | " + self._get_type_annotation(annotation.right)
        if isinstance(annotation, ast.Subscript):
            base = self._get_type_annotation(annotation.value)
            if isinstance(annotation.slice, ast.Tuple):
                args = ", ".join(self._get_type_annotation(x) for x in annotation.slice.elts)
            else:
                args = self._get_type_annotation(annotation.slice)
            return f"{base}[{args}]"
        if isinstance(annotation, ast.Constant):
            return repr(annotation.value)
        return "Any"

    def _get_decorator_name(self, decorator: ast.AST) -> str:
        if isinstance(decorator, ast.Name):
            return decorator.id
        if isinstance(decorator, ast.Attribute):
            parts = []
            node = decorator
            while isinstance(node, ast.Attribute):
                parts.append(node.attr)
                node = node.value
            if isinstance(node, ast.Name):
                parts.append(node.id)
            return ".".join(reversed(parts))
        return "unknown"

    def _generate_test_code(self, func_info: dict, framework: str) -> str:
        if framework == "pytest":
            return self._generate_pytest(func_info)
        elif framework == "doctest":
            return self._generate_doctest(func_info)
        else:
            return self._generate_unittest(func_info)

    def _generate_pytest(self, func_info: dict) -> str:
        func_name = func_info['name']
        params = func_info['params']
        param_types = func_info['param_types']
        is_async = func_info['is_async']

        test_name = f"test_{func_name}"
        if is_async:
            decorator = "@pytest.mark.asyncio\n    "
        else:
            decorator = ""

        param_list = []
        fixture_values = []
        for i, (pname, ptype) in enumerate(zip(params, param_types)):
            if ptype == "str":
                fixture_values.append(f'    {pname}: str = "{pname}_sample"')
            elif ptype == "int":
                fixture_values.append(f"    {pname}: int = {i + 1}")
            elif ptype == "float":
                fixture_values.append(f"    {pname}: float = {i + 1}.5")
            elif ptype == "bool":
                fixture_values.append(f"    {pname}: bool = True")
            elif ptype == "list":
                fixture_values.append(f"    {pname}: list = []")
            elif ptype == "dict":
                fixture_values.append(f"    {pname}: dict = {{}}")
            else:
                fixture_values.append(f"    {pname}: {ptype} = None")
            param_list.append(pname)

        fixture_block = "\n".join(fixture_values) if fixture_values else "    pass"

        call_sig = f"{func_name}({', '.join(param_list)})"
        if is_async:
            call_line = f"result = await {call_sig}"
            return_line = "return result"
        else:
            call_line = f"result = {call_sig}"
            return_line = "return result"

        return f"""def {test_name}({fixture_values[0] if fixture_values else ""}):
{decorator}    # Arrange
    
    # Act
    {call_line}
    
    # Assert
    assert result is not None
"""

    def _generate_doctest(self, func_info: dict) -> str:
        func_name = func_info['name']
        params = func_info['params']

        param_list = []
        for i, p in enumerate(params):
            if i == 0:
                param_list.append(f'"{p}_sample"')
            else:
                param_list.append(f"{i + 1}")

        call = f"{func_name}({', '.join(param_list)})"
        return f""">>> {call}
"""

    def _generate_unittest(self, func_info: dict) -> str:
        func_name = func_info['name']
        params = func_info['params']
        camel_name = ''.join(word.capitalize() for word in func_name.split('_'))

        param_list = []
        for i, (pname, ptype) in enumerate(zip(params, func_info['param_types'])):
            if ptype == "str":
                param_list.append(f'"{pname}_sample"')
            elif ptype in ("int", "float"):
                param_list.append(f"{i + 1}")
            elif ptype == "bool":
                param_list.append("True")
            else:
                param_list.append("None")

        call = f"{func_name}({', '.join(param_list)})"

        return f"""class Test{camel_name}(unittest.TestCase):
    def test_{func_name}(self):
        result = {call}
        self.assertIsNotNone(result)
"""

    def _generate_test_filename(self, target: str, framework: str) -> str:
        path = Path(target)
        test_dir = path.parent / "tests"
        stem = path.stem
        if framework == "pytest":
            return str(test_dir / f"test_{stem}.py")
        elif framework == "doctest":
            return str(test_dir / f"test_{stem}_doctest.py")
        else:
            return str(test_dir / f"test_{stem}.py")

    def _wrap_with_imports(self, test_code: str, original_file: str) -> str:
        module_name = Path(original_file).stem
        imports = [
            "import pytest",
            f"import sys",
            f"sys.path.insert(0, '.')",
            f"from {module_name} import *",
            "",
            ""
        ]
        return "\n".join(imports) + test_code
