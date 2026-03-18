"""
内置技能：调试解释 (Debug Explain Skill)

【设计意图】
将错误堆栈解析为人类可读的解释，帮助开发者快速理解问题根因并给出修复建议。
无需 LLM 参与，纯规则解析，零 Token 消耗。

步骤：
    1. 解析错误类型和消息
    2. 提取关键代码位置（文件路径、行号、函数名）
    3. 识别常见错误模式并给出解释
    4. 生成修复建议
"""

import re
import logging
from pathlib import Path

from skills.base import Skill

logger = logging.getLogger(__name__)


class DebugExplainSkill(Skill):
    """错误调试解释技能：解析堆栈、定位问题、给出修复建议"""

    name = "debug_explain"
    description = (
        "Parse an error traceback and explain it in plain language. "
        "Identifies root causes, pinpoints the exact file and line, "
        "and suggests fixes. Zero LLM tokens - pure rule-based analysis."
    )
    parameters = {
        "type": "object",
        "properties": {
            "error_traceback": {
                "type": "string",
                "description": "The error traceback to analyze"
            },
            "language": {
                "type": "string",
                "description": "Explanation language (en/zh)",
                "default": "en"
            }
        },
        "required": ["error_traceback"]
    }

    ERROR_PATTERNS = {
        "ImportError": {
            "pattern": r"ImportError: (.*)",
            "en": "Python cannot find and import the requested module. This usually means:\n"
                  "  1. The module is not installed\n"
                  "  2. The module name is misspelled\n"
                  "  3. There's a circular import issue",
            "zh": "Python 无法找到并导入请求的模块。这通常意味着：\n"
                 "  1. 模块未安装\n"
                 "  2. 模块名称拼写错误\n"
                 "  3. 存在循环导入问题"
        },
        "ModuleNotFoundError": {
            "pattern": r"ModuleNotFoundError: No module named '(.*)'",
            "en": "The specified module is not installed. Try running:\n"
                  "  pip install {module}",
            "zh": "指定的模块未安装。尝试运行：\n  pip install {module}"
        },
        "SyntaxError": {
            "pattern": r"SyntaxError: (.*)",
            "en": "Your code has a syntax error that prevents Python from parsing it.\n"
                  "Check for missing colons, parentheses, or incorrect indentation.",
            "zh": "代码存在语法错误，Python 无法解析。\n"
                 "请检查是否缺少冒号、括号或缩进不正确。"
        },
        "NameError": {
            "pattern": r"NameError: name '(.*)' is not defined",
            "en": "A variable or function name is used before being defined.\n"
                  "This is a typo or the definition is missing.",
            "zh": "变量或函数在使用前未定义。\n"
                 "这是拼写错误或定义缺失。"
        },
        "TypeError": {
            "pattern": r"TypeError: (.*)",
            "en": "An operation was performed on an object of the wrong type.\n"
                  "For example, trying to add a string to an integer.",
            "zh": "对错误类型的对象执行了操作。\n"
                 "例如，尝试将字符串与整数相加。"
        },
        "AttributeError": {
            "pattern": r"AttributeError: '(.*?)' object has no attribute '(.*)'",
            "en": "The object does not have the specified attribute.\n"
                  "Check if you're using the correct method on the correct object type.",
            "zh": "对象没有指定的属性。\n"
                 "请检查是否对正确类型的对象使用了正确的方法。"
        },
        "KeyError": {
            "pattern": r"KeyError: (.*)",
            "en": "A dictionary key was not found. The key may be misspelled or missing.",
            "zh": "字典中未找到该键。键可能拼写错误或不存在。"
        },
        "IndexError": {
            "pattern": r"IndexError: list index out of range",
            "en": "You tried to access an index that doesn't exist in the list.\n"
                  "Check if the list is empty or the index is beyond its length.",
            "zh": "你试图访问列表中不存在的索引。\n"
                 "请检查列表是否为空或索引是否超出范围。"
        },
        "FileNotFoundError": {
            "pattern": r"FileNotFoundError: (.*)",
            "en": "The file or directory does not exist. Check the path.",
            "zh": "文件或目录不存在。请检查路径是否正确。"
        },
        "PermissionError": {
            "pattern": r"PermissionError: (.*)",
            "en": "You don't have permission to access this file or resource.",
            "zh": "你没有访问此文件或资源的权限。"
        },
        "TimeoutError": {
            "pattern": r"TimeoutError: (.*)",
            "en": "An operation took too long and timed out.\n"
                  "The server may be busy or the network connection is slow.",
            "zh": "操作花费时间过长而超时。\n"
                 "服务器可能繁忙或网络连接较慢。"
        },
        "ConnectionError": {
            "pattern": r"ConnectionError: (.*)",
            "en": "Could not connect to a remote server or service.\n"
                  "Check if the service is running and network connectivity.",
            "zh": "无法连接到远程服务器或服务。\n"
                 "请检查服务是否正在运行以及网络连接。"
        },
        "JSONDecodeError": {
            "pattern": r"JSONDecodeError: (.*)",
            "en": "The string is not valid JSON. Check for missing quotes, commas, or brackets.",
            "zh": "字符串不是有效的 JSON。\n"
                 "请检查是否缺少引号、逗号或括号。"
        },
        "AssertionError": {
            "pattern": r"AssertionError: (.*)",
            "en": "An assertion failed. This means a condition that should be true was false.\n"
                  "Check the expected vs actual values.",
            "zh": "断言失败。这意味着应为真的条件为假。\n"
                 "请检查期望值与实际值。"
        },
        "RuntimeError": {
            "pattern": r"RuntimeError: (.*)",
            "en": "A runtime error occurred during program execution.",
            "zh": "程序执行过程中发生运行时错误。"
        }
    }

    def execute(self, tool_handlers: dict, **kwargs) -> str:
        error_traceback = kwargs.get("error_traceback", "")
        language = kwargs.get("language", "en")

        if not error_traceback:
            return "Error: 'error_traceback' parameter is required for debug_explain skill."

        lines = error_traceback.strip().split("\n")
        if not lines:
            return "Error: Empty traceback provided."

        report_lines = [
            f"# 🐛 Debug Analysis Report",
            f"",
            f"**Language**: {language}",
            f"",
            f"## Raw Traceback",
            f"```",
            error_traceback[:2000],
            f"```",
            f""
        ]

        error_type = "UnknownError"
        error_msg = ""

        for line in lines:
            line = line.strip()
            error_type_match = re.match(r"(\w+Error|Exception):", line)
            if error_type_match:
                error_type = error_type_match.group(1)
                error_msg_match = re.search(r": (.+)$", line)
                if error_msg_match:
                    error_msg = error_msg_match.group(1)
                break

        report_lines.append(f"## Error Identification")
        report_lines.append(f"- **Type**: `{error_type}`")
        report_lines.append(f"- **Message**: {error_msg}")
        report_lines.append(f"")

        if error_type in self.ERROR_PATTERNS:
            pattern_info = self.ERROR_PATTERNS[error_type]
            template = pattern_info.get(language, pattern_info["en"])
            module_match = re.search(r"'(.*?)'", error_msg)
            module_name = module_match.group(1) if module_match else error_msg
            explanation = template.format(module=module_name) if "{module}" in template else template
            report_lines.append(f"## Explanation")
            report_lines.append(explanation)
            report_lines.append(f"")
        else:
            report_lines.append(f"## Explanation")
            if language == "zh":
                report_lines.append(f"这是一个 `{error_type}` 类型的错误。\n"
                                    f"请查看堆栈跟踪以了解更多信息。")
            else:
                report_lines.append(f"This is a `{error_type}` type error.\n"
                                    f"Check the stack trace for more details.")
            report_lines.append(f"")

        file_location_match = re.search(r'File "(.*?)", line (\d+)', error_traceback)
        if file_location_match:
            file_path = file_location_match.group(1)
            line_num = file_location_match.group(2)
            report_lines.append(f"## Problem Location")
            report_lines.append(f"- **File**: `{file_path}`")
            report_lines.append(f"- **Line**: `{line_num}`")
            report_lines.append(f"")

            read_file = tool_handlers.get("read_file")
            if read_file:
                try:
                    content = read_file(file_path=file_path)
                    file_lines = content.split("\n")
                    start_line = max(0, int(line_num) - 6)
                    end_line = min(len(file_lines), int(line_num) + 3)
                    context = "\n".join(f"{i+1:4d}: {file_lines[i]}" for i in range(start_line, end_line))
                    report_lines.append(f"## Code Context")
                    report_lines.append(f"```python")
                    report_lines.append(context)
                    report_lines.append(f"```")
                    report_lines.append(f"")
                except Exception as e:
                    logger.warning(f"[DebugExplainSkill] Failed to read file: {e}")

        report_lines.append(f"## Suggested Fixes")
        fixes = self._suggest_fixes(error_type, error_msg, language)
        report_lines.extend(fixes)

        report_lines.append(f"")
        report_lines.append(f"---")
        report_lines.append(f"_Debug analysis completed by DebugExplainSkill_")

        return "\n".join(report_lines)

    def _suggest_fixes(self, error_type: str, error_msg: str, language: str) -> list[str]:
        suggestions = []

        if language == "zh":
            generic = [
                "1. 检查拼写错误（变量名、模块名、函数名）",
                "2. 确认所有依赖都已正确安装",
                "3. 查看完整的堆栈跟踪以定位根本原因",
                "4. 使用 try-except 包装可能失败的代码",
                "5. 检查 API 文档确认正确的使用方式"
            ]
        else:
            generic = [
                "1. Check for typos in variable, module, or function names",
                "2. Ensure all dependencies are properly installed",
                "3. Review the full stack trace to identify the root cause",
                "4. Wrap potentially failing code in try-except blocks",
                "5. Check API documentation for correct usage"
            ]

        if error_type == "ModuleNotFoundError":
            module_name = error_msg.strip("'\"")
            if language == "zh":
                suggestions.append(f"1. 安装缺失的模块：\n   ```bash\n   pip install {module_name}\n   ```")
            else:
                suggestions.append(f"1. Install the missing module:\n   ```bash\n   pip install {module_name}\n   ```")

        if error_type == "SyntaxError":
            if language == "zh":
                suggestions.append("1. 检查是否缺少冒号 `:` 结尾（if/for/def 等）")
                suggestions.append("2. 检查括号、引号是否成对匹配")
                suggestions.append("3. 检查缩进是否使用空格而非制表符")
            else:
                suggestions.append("1. Check for missing colons `:` at the end of statements")
                suggestions.append("2. Ensure all brackets and quotes are properly paired")
                suggestions.append("3. Use spaces instead of tabs for indentation")

        if error_type == "ImportError":
            if language == "zh":
                suggestions.append("1. 检查是否存在循环导入（A 导入 B，B 导入 A）")
                suggestions.append("2. 确认 __init__.py 文件存在（如果是包）")
            else:
                suggestions.append("1. Check for circular imports (A imports B, B imports A)")
                suggestions.append("2. Ensure __init__.py exists if it's a package")

        suggestions.extend(generic[:5 - len(suggestions)] if len(suggestions) < 5 else generic[:5])

        return suggestions
