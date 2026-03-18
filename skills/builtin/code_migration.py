"""
内置技能：代码迁移 (Code Migration Skill)

【设计意图】
帮助将代码从旧框架/库迁移到新版本，或将代码从一种技术栈转换到另一种。
支持常见的迁移场景：
1. Python 2 → Python 3
2. 旧 API 版本 → 新 API 版本
3. 语法转换（如装饰器、类型注解）
4. 框架特定代码转换（如 Flask → FastAPI）

步骤：
    1. 分析目标文件的代码模式
    2. 识别需要迁移的代码片段
    3. 生成迁移后的代码
    4. 给出迁移说明和注意事项
"""

import ast
import logging
import re

from skills.base import Skill

logger = logging.getLogger(__name__)


class CodeMigrationSkill(Skill):
    """代码迁移技能：Python 2→3、API 升级、框架迁移"""

    name = "code_migration"
    description = (
        "Migrate code from old frameworks/versions to new ones. "
        "Supports Python 2 to 3, API upgrades, syntax modernization, "
        "and framework conversions (e.g., Flask to FastAPI). "
        "Provides both migrated code and migration notes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "File path to migrate (e.g., 'legacy/api.py')"
            },
            "migration_type": {
                "type": "string",
                "description": "Type of migration to perform",
                "enum": [
                    "python2_to_3",
                    "python_modernize",
                    "flask_to_fastapi",
                    "requests_to_httpx",
                    "json_lib",
                    "type_annotations"
                ]
            },
            "apply_changes": {
                "type": "boolean",
                "description": "Whether to write migrated code to file",
                "default": False
            }
        },
        "required": ["target", "migration_type"]
    }

    MIGRATION_PATTERNS = {
        "python2_to_3": [
            (r"print\s+['\"](.+?)['\"]", r"print('\1')"),
            (r"print\s+(.+)", r"print(\1)"),
            (r"xrange\(", "range("),
            (r"\.iteritems\(\)", ".items()"),
            (r"\.iterkeys\(\)", ".keys()"),
            (r"\.itervalues\(\)", ".values()"),
            (r"raw_input\(", "input("),
            (r"`(.+?)`", r"str(\1)"),
            (r"unicode\(", "str("),
        ],
        "python_modernize": [
            (r"from\s+__future__\s+import\s+print_function", ""),
            (r"%\((\w+)\)", r"{\1}"),
            (r"\.format\(", "f-string or "),
            (r"class\s+(\w+)\(object\):", r"class \1:"),
        ],
        "requests_to_httpx": [
            (r"import\s+requests", "import httpx"),
            (r"requests\.get\(", "httpx.get("),
            (r"requests\.post\(", "httpx.post("),
            (r"requests\.put\(", "httpx.put("),
            (r"requests\.delete\(", "httpx.delete("),
            (r"requests\.patch\(", "httpx.patch("),
            (r"\.json\(\)", ".json()"),
            (r"r\.status_code", "r.status_code"),
        ],
        "flask_to_fastapi": [
            (r"from\s+flask\s+import\s+Flask", "from fastapi import FastAPI"),
            (r"app\s*=\s*Flask\(__name__\)", "app = FastAPI()"),
            (r"@app\.route\(['\"](.+?)['\"]\)", r"@app.get('\1')"),
            (r"@app\.route\(['\"](.+?)['\"],\s*methods=['\"](.+?)['\"]\)", r"@app.\2('\1')"),
            (r"request\.args", "request.query_params"),
            (r"request\.form", "request.form()"),
            (r"request\.get_json\(\)", "request.json()"),
            (r"jsonify\(", "json("),
        ],
        "json_lib": [
            (r"import\s+json", "import json"),
            (r"json\.loads\(", "json.loads("),
            (r"json\.dumps\(", "json.dumps("),
            (r"\.read\(\)", ".read()"),
        ],
        "type_annotations": [
            (r"def\s+(\w+)\((.*)\):", r"def \1(\2) -> None:"),
        ],
    }

    def execute(self, tool_handlers: dict, **kwargs) -> str:
        target = kwargs.get("target", "")
        migration_type = kwargs.get("migration_type", "")
        apply_changes = kwargs.get("apply_changes", False)

        if not target:
            return "Error: 'target' parameter is required for code_migration skill."

        if not migration_type:
            return "Error: 'migration_type' parameter is required."

        read_file = tool_handlers.get("read_file")
        if not read_file:
            return "Error: read_file tool is not available."

        try:
            content = read_file(file_path=target)
        except Exception as e:
            return f"Error: Failed to read target file '{target}': {e}"

        if not target.endswith('.py'):
            return f"Error: Only Python files (.py) are supported for migration."

        report_lines = [
            f"# 🔄 Code Migration Report",
            f"",
            f"**File**: `{target}`",
            f"**Migration Type**: `{migration_type}`",
            f"**Apply Changes**: {'Yes' if apply_changes else 'No (preview only)'}",
            f""
        ]

        migration_desc = self._get_migration_description(migration_type)
        report_lines.append(f"## 📋 Migration Overview")
        report_lines.append(migration_desc)
        report_lines.append(f"")

        original_content = content
        migrated_content = content
        changes_made = []

        patterns = self.MIGRATION_PATTERNS.get(migration_type, [])
        if not patterns:
            return f"Error: Unknown migration type '{migration_type}'. Available types: {', '.join(self.MIGRATION_PATTERNS.keys())}"

        for pattern_regex, replacement in patterns:
            new_content, count = re.subn(pattern_regex, replacement, migrated_content)
            if count > 0:
                migrated_content = new_content
                changes_made.append({
                    'pattern': pattern_regex,
                    'replacement': replacement,
                    'count': count
                })

        report_lines.append(f"## 🔍 Changes Detected ({len(changes_made)} patterns)")
        report_lines.append(f"")

        for change in changes_made:
            report_lines.append(f"### Pattern")
            report_lines.append(f"```regex")
            report_lines.append(f"{change['pattern']}")
            report_lines.append(f"```")
            report_lines.append(f"**Replacement**: `{change['replacement']}`")
            report_lines.append(f"**Occurrences**: {change['count']}")
            report_lines.append(f"")

        if migrated_content != original_content:
            report_lines.append(f"## ✅ Migrated Code")
            report_lines.append(f"```python")
            diff_lines = self._generate_diff(original_content, migrated_content)
            report_lines.extend(diff_lines[:100])
            if len(diff_lines) > 100:
                report_lines.append(f"... ({len(diff_lines) - 100} more lines)")
            report_lines.append(f"```")
            report_lines.append(f"")
        else:
            report_lines.append(f"## ⚠️ No Changes Made")
            report_lines.append(f"No patterns matched in the target file.")
            report_lines.append(f"")

        if apply_changes and migrated_content != original_content:
            write_file = tool_handlers.get("write_file")
            if write_file:
                try:
                    backup_path = target + ".bak"
                    write_file(file_path=backup_path, content=original_content)
                    write_file(file_path=target, content=migrated_content)
                    report_lines.append(f"## ✅ Changes Applied")
                    report_lines.append(f"- Original file backed up to: `{backup_path}`")
                    report_lines.append(f"- Migrated code written to: `{target}`")
                except Exception as e:
                    report_lines.append(f"## ❌ Write Failed")
                    report_lines.append(f"Could not write changes: {e}")
            else:
                report_lines.append(f"## ⚠️ Write Skipped")
                report_lines.append(f"write_file tool not available. Showing preview only.")
        else:
            report_lines.append(f"## 📝 Preview Mode")
            report_lines.append(f"Set `apply_changes: true` to write migrated code to file.")
            report_lines.append(f"")

        report_lines.append(f"## ⚠️ Manual Review Required")
        review_notes = self._get_migration_notes(migration_type)
        report_lines.extend(review_notes)

        report_lines.append(f"")
        report_lines.append(f"---")
        report_lines.append(f"_Code migration completed by CodeMigrationSkill_")

        return "\n".join(report_lines)

    def _get_migration_description(self, migration_type: str) -> str:
        descriptions = {
            "python2_to_3": (
                "Converts Python 2 syntax to Python 3. This includes:\n"
                "  - print statements → print() function\n"
                "  - xrange() → range()\n"
                "  - .iteritems() → .items()\n"
                "  - raw_input() → input()\n"
                "  - String formatting modernization"
            ),
            "python_modernize": (
                "Modernizes Python 3 code to use latest idioms:\n"
                "  - Removes unnecessary __future__ imports\n"
                "  - Uses f-strings instead of .format()\n"
                "  - Removes redundant (object) inheritance"
            ),
            "flask_to_fastapi": (
                "Converts Flask applications to FastAPI:\n"
                "  - Flask → FastAPI initialization\n"
                "  - @app.route() → @app.get/post/put/delete()\n"
                "  - request.args → request.query_params\n"
                "  - jsonify() → json()"
            ),
            "requests_to_httpx": (
                "Migrates from requests library to httpx:\n"
                "  - httpx.get/post/put/delete()\n"
                "  - Async support\n"
                "  - Same API surface with httpx compatibility"
            ),
            "json_lib": (
                "Modernizes JSON handling:\n"
                "  - Uses standard json library properly\n"
                "  - Ensures proper encoding/decoding"
            ),
            "type_annotations": (
                "Adds type annotations to function signatures:\n"
                "  - Parameter types\n"
                "  - Return types\n"
                "  - Note: This is a basic pattern; for full type hints use pyright/mypy"
            )
        }
        return descriptions.get(migration_type, "Unknown migration type")

    def _generate_diff(self, original: str, migrated: str) -> list[str]:
        orig_lines = original.split('\n')
        mig_lines = migrated.split('\n')
        diff = []

        for i, (orig, mig) in enumerate(zip(orig_lines, mig_lines), 1):
            if orig != mig:
                diff.append(f"- {i}: {orig[:80]}")
                diff.append(f"+ {i}: {mig[:80]}")

        if len(mig_lines) > len(orig_lines):
            for i in range(len(orig_lines), len(mig_lines)):
                diff.append(f"+ {i+1}: {mig_lines[i][:80]}")

        if not diff:
            diff.append("# No visible line changes (whitespace/formatting only)")

        return diff

    def _get_migration_notes(self, migration_type: str) -> list[str]:
        notes = {
            "python2_to_3": [
                "⚠️ Manual review required for:",
                "  - Unicode string handling (u'' prefix)",
                "  - Division operator changes (/ vs //)",
                "  - Exception handling syntax",
                "  - Relative imports",
                "💡 Consider using '2to3' tool for comprehensive migration",
            ],
            "python_modernize": [
                "⚠️ Manual review required for:",
                "  - f-string complex expressions",
                "  - Type annotation completeness",
                "💡 Consider running 'pyupgrade --py36-plus' after this migration",
            ],
            "flask_to_fastapi": [
                "⚠️ Manual review required for:",
                "  - Response models and Pydantic schemas",
                "  - Dependency injection system",
                "  - Async/await patterns",
                "  - Error handling (HTTPException vs Flask abort)",
                "  - CORS configuration",
                "💡 FastAPI uses Pydantic for request/response validation",
            ],
            "requests_to_httpx": [
                "⚠️ Manual review required for:",
                "  - Session objects (httpx.Client vs requests.Session)",
                "  - Timeout parameter differences",
                "  - Response object attribute access",
                "💡 httpx supports both sync and async: httpx.AsyncClient",
            ],
            "json_lib": [
                "⚠️ Manual review required for:",
                "  - Encoding parameters (ensure_ascii, etc.)",
                "  - Custom JSONEncoder classes",
                "💡 Consider using 'orjson' for performance-critical code",
            ],
            "type_annotations": [
                "⚠️ This is a basic pattern-based transformation.",
                "💡 For comprehensive type hints, use:",
                "  - pyright / mypy for checking",
                "  - 'pyright' extension in VS Code",
                "  - Consider 'duck typing' where appropriate",
            ]
        }
        default_notes = ["⚠️ Please review the migrated code carefully before deploying."]
        return notes.get(migration_type, default_notes)
