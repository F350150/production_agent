"""
内置技能：API 设计审查 (API Design Review Skill)

【设计意图】
对 Python 文件中的 API（函数/类）进行设计质量审查，
检查命名规范、类型注解、文档字符串、参数设计等最佳实践。
给出具体改进建议，帮助提升代码可读性和可维护性。

步骤：
    1. 读取目标文件，解析 AST 获取 API 定义
    2. 按照预设规则进行多维度审查
    3. 生成问题列表和改进建议
    4. 给出整体设计评分
"""

import ast
import logging
import re
from pathlib import Path

from skills.base import Skill

logger = logging.getLogger(__name__)


class ApiDesignReviewSkill(Skill):
    """API 设计审查技能：检查命名、类型注解、文档、可维护性"""

    name = "api_design_review"
    description = (
        "Review API (function/class) design quality in a Python file. "
        "Checks naming conventions, type hints, docstrings, parameter design, "
        "and provides specific improvement suggestions with an overall score."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "File path to review (e.g., 'src/api.py')"
            },
            "check_naming": {
                "type": "boolean",
                "description": "Check naming conventions",
                "default": True
            },
            "check_types": {
                "type": "boolean",
                "description": "Check type annotations",
                "default": True
            },
            "check_docs": {
                "type": "boolean",
                "description": "Check docstrings",
                "default": True
            }
        },
        "required": ["target"]
    }

    NAMING_SCORE_WEIGHTS = {
        "function": 2,
        "class": 2,
        "parameter": 1,
        "variable": 1
    }

    def execute(self, tool_handlers: dict, **kwargs) -> str:
        target = kwargs.get("target", "")
        check_naming = kwargs.get("check_naming", True)
        check_types = kwargs.get("check_types", True)
        check_docs = kwargs.get("check_docs", True)

        if not target:
            return "Error: 'target' parameter is required for api_design_review skill."

        read_file = tool_handlers.get("read_file")
        if not read_file:
            return "Error: read_file tool is not available."

        try:
            content = read_file(file_path=target)
        except Exception as e:
            return f"Error: Failed to read target file '{target}': {e}"

        if not target.endswith('.py'):
            return f"Error: Only Python files (.py) are supported for API review."

        report_lines = [
            f"# 🔍 API Design Review Report",
            f"",
            f"**File**: `{target}`",
            f"**Checks**: naming={check_naming}, types={check_types}, docs={check_docs}",
            f""
        ]

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return f"Error: Cannot parse '{target}' - syntax error at line {e.lineno}: {e.msg}"

        issues = []
        total_score = 100
        max_deductions = 0

        functions = self._extract_apis(tree)
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

        for func in functions:
            func_issues, deductions = self._review_function(func, check_naming, check_types, check_docs)
            issues.extend(func_issues)
            max_deductions += deductions

        for cls in classes:
            cls_issues, deductions = self._review_class(cls, check_naming, check_types, check_docs)
            issues.extend(cls_issues)
            max_deductions += deductions

        final_score = max(0, total_score - max_deductions)

        score_color = self._get_score_color(final_score)
        report_lines.append(f"## 📊 Overall Design Score")
        report_lines.append(f"{score_color} **{final_score}/100**")
        report_lines.append(f"")

        if not issues:
            report_lines.append(f"## ✅ No Issues Found")
            report_lines.append(f"Great job! Your API design follows best practices.")
        else:
            report_lines.append(f"## ⚠️ Issues Found ({len(issues)})")
            report_lines.append(f"")

            critical_issues = [i for i in issues if i['severity'] == 'critical']
            warning_issues = [i for i in issues if i['severity'] == 'warning']
            info_issues = [i for i in issues if i['severity'] == 'info']

            if critical_issues:
                report_lines.append(f"### 🔴 Critical ({len(critical_issues)})")
                for issue in critical_issues:
                    report_lines.append(f"- **[L{issue['line']}]** {issue['message']}")
                report_lines.append(f"")

            if warning_issues:
                report_lines.append(f"### 🟡 Warnings ({len(warning_issues)})")
                for issue in warning_issues:
                    report_lines.append(f"- **[L{issue['line']}]** {issue['message']}")
                report_lines.append(f"")

            if info_issues:
                report_lines.append(f"### 🔵 Suggestions ({len(info_issues)})")
                for issue in info_issues:
                    report_lines.append(f"- **[L{issue['line']}]** {issue['message']}")
                report_lines.append(f"")

        report_lines.append(f"## 📝 Detailed Analysis")
        report_lines.append(f"")

        naming_issues = [i for i in issues if i['category'] == 'naming']
        type_issues = [i for i in issues if i['category'] == 'types']
        doc_issues = [i for i in issues if i['category'] == 'docs']
        design_issues = [i for i in issues if i['category'] == 'design']

        if check_naming:
            report_lines.append(f"### 📛 Naming Conventions")
            if naming_issues:
                report_lines.append(f"Found {len(naming_issues)} naming issues:")
                for issue in naming_issues[:10]:
                    report_lines.append(f"  - `{issue['entity']}`: {issue['message']}")
            else:
                report_lines.append(f"✅ All names follow conventions.")
            report_lines.append(f"")

        if check_types:
            report_lines.append(f"### 🏷️ Type Annotations")
            if type_issues:
                report_lines.append(f"Found {len(type_issues)} type annotation issues:")
                for issue in type_issues[:10]:
                    report_lines.append(f"  - `{issue['entity']}`: {issue['message']}")
            else:
                report_lines.append(f"✅ All functions/classes have proper type hints.")
            report_lines.append(f"")

        if check_docs:
            report_lines.append(f"### 📖 Documentation")
            if doc_issues:
                report_lines.append(f"Found {len(doc_issues)} documentation issues:")
                for issue in doc_issues[:10]:
                    report_lines.append(f"  - `{issue['entity']}`: {issue['message']}")
            else:
                report_lines.append(f"✅ All APIs have proper docstrings.")
            report_lines.append(f"")

        report_lines.append(f"## 💡 Recommendations")
        recommendations = self._generate_recommendations(issues)
        for rec in recommendations:
            report_lines.append(f"- {rec}")

        report_lines.append(f"")
        report_lines.append(f"---")
        report_lines.append(f"_API design review completed by ApiDesignReviewSkill_")

        return "\n".join(report_lines)

    def _extract_apis(self, tree: ast.AST) -> list[dict]:
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if any(isinstance(parent, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                       for parent in ast.walk(tree)):
                    continue
                params = [arg.arg for arg in node.args.args]
                returns = self._get_type_str(node.returns)
                has_docstring = ast.get_docstring(node) is not None
                functions.append({
                    'name': node.name,
                    'lineno': node.lineno,
                    'params': params,
                    'returns': returns,
                    'has_docstring': has_docstring,
                    'is_async': isinstance(node, ast.AsyncFunctionDef),
                    'decorators': [self._get_decorator_name(d) for d in node.decorator_list]
                })
        return functions

    def _review_function(self, func: dict, check_naming: bool, check_types: bool, check_docs: bool) -> tuple:
        issues = []
        deductions = 0

        if check_naming:
            if not func['name'].islower() and not func['name'].startswith('_'):
                if re.match(r'^[A-Z][a-zA-Z0-9]*$', func['name']) and not func['decorators']:
                    issues.append({
                        'category': 'naming',
                        'severity': 'warning',
                        'line': func['lineno'],
                        'entity': func['name'],
                        'message': 'Function name uses PascalCase. Consider using snake_case.'
                    })
                    deductions += 2

            if len(func['name']) < 3 and not func['name'].startswith('_'):
                issues.append({
                    'category': 'naming',
                    'severity': 'info',
                    'line': func['lineno'],
                    'entity': func['name'],
                    'message': 'Function name is very short. Consider a more descriptive name.'
                })
                deductions += 1

        if check_types and not func['returns'] and not func['is_async']:
            issues.append({
                'category': 'types',
                'severity': 'warning',
                'line': func['lineno'],
                'entity': f"{func['name']}()",
                'message': 'Missing return type annotation.'
            })
            deductions += 2

        if check_docs and not func['has_docstring']:
            issues.append({
                'category': 'docs',
                'severity': 'warning',
                'line': func['lineno'],
                'entity': f"{func['name']}()",
                'message': 'Missing docstring.'
            })
            deductions += 2

        return issues, deductions

    def _review_class(self, cls: ast.ClassDef, check_naming: bool, check_types: bool, check_docs: bool) -> tuple:
        issues = []
        deductions = 0

        if check_naming:
            if not cls.name[0].isupper():
                issues.append({
                    'category': 'naming',
                    'severity': 'critical',
                    'line': cls.lineno,
                    'entity': cls.name,
                    'message': 'Class name should use PascalCase.'
                })
                deductions += 3

        if check_docs and not ast.get_docstring(cls):
            issues.append({
                'category': 'docs',
                'severity': 'warning',
                'line': cls.lineno,
                'entity': f"class {cls.name}",
                'message': 'Missing class docstring.'
            })
            deductions += 2

        return issues, deductions

    def _get_type_str(self, annotation: ast.AST) -> str:
        if annotation is None:
            return ""
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(annotation, ast.BinOp):
            return self._get_type_str(annotation.left) + " | " + self._get_type_str(annotation.right)
        if isinstance(annotation, ast.Subscript):
            base = self._get_type_str(annotation.value)
            return f"{base}[...]"
        return "Any"

    def _get_decorator_name(self, decorator: ast.AST) -> str:
        if isinstance(decorator, ast.Name):
            return decorator.id
        if isinstance(decorator, ast.Attribute):
            return f"{self._get_decorator_name(decorator.value)}.{decorator.attr}"
        return "unknown"

    def _get_score_color(self, score: int) -> str:
        if score >= 90:
            return "🟢"
        elif score >= 70:
            return "🟡"
        elif score >= 50:
            return "🟠"
        else:
            return "🔴"

    def _generate_recommendations(self, issues: list) -> list:
        recs = []
        categories = {i['category'] for i in issues}

        if 'docs' in categories:
            recs.append("Add comprehensive docstrings to all public APIs using Google/NumPy style.")
        if 'types' in categories:
            recs.append("Add type annotations for all function parameters and return values.")
        if 'naming' in categories:
            recs.append("Follow PEP 8 naming conventions: snake_case for functions, PascalCase for classes.")
        if 'design' in categories:
            recs.append("Consider refactoring long functions (>50 lines) into smaller, focused functions.")

        if not recs:
            recs.append("Continue following best practices for maintainable code.")
            recs.append("Consider adding docstrings even for private/internal functions for better code comprehension.")

        return recs
