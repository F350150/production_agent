"""
内置技能：代码审查 (Code Review Skill)

【设计意图】
将"读文件 → 分析结构 → 沙箱执行测试/Lint → 汇总报告"全流程封装为一个 use_skill 调用。
对 QA_Reviewer 角色尤其有用：无需多轮工具调用即可产出一份完整的代码质量报告。

步骤：
    1. read_file(path)          → 读取目标文件内容
    2. get_repo_map(path)       → 获取代码结构骨架（可选，path 为文件时降级为目录扫描）
    3. sandbox_bash(command)    → 在 Docker 沙箱中运行 Lint（flake8）和单元测试（pytest）
    4. 汇总所有结果，生成结构化报告

注意：sandbox_bash 步骤依赖 Docker 可用性；若不可用则降级为 run_bash。
"""

import logging
import os

from skills.base import Skill

logger = logging.getLogger(__name__)


class CodeReviewSkill(Skill):
    """代码审查技能：读文件 → 结构分析 → 沙箱 Lint/测试 → 报告"""

    name = "code_review"
    description = (
        "Perform a comprehensive code review on a file or directory: "
        "read the source, analyze structure via AST repo map, run linting (flake8) "
        "and tests (pytest) in a Docker sandbox, then return a quality report. "
        "Ideal for QA_Reviewer to assess code before sign-off."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file or directory to review."
            },
            "run_tests": {
                "type": "boolean",
                "description": "Whether to run pytest in sandbox (default: true).",
                "default": True
            },
            "test_command": {
                "type": "string",
                "description": "Custom test command to run in sandbox (default: 'python -m pytest -v').",
                "default": "python -m pytest -v"
            }
        },
        "required": ["path"]
    }

    def execute(self, tool_handlers: dict, **kwargs) -> str:
        path = kwargs.get("path", "")
        run_tests = kwargs.get("run_tests", True)
        test_command = kwargs.get("test_command", "python -m pytest -v")

        if not path:
            return "Error: 'path' parameter is required for code_review skill."

        report_lines = [
            f"# 🔎 Code Review Report",
            f"**Target**: `{path}`",
            "",
        ]

        # ── Step 1: 读取文件 ──────────────────────────────────────
        read_file = tool_handlers.get("read_file")
        if read_file:
            try:
                content = read_file(path=path)
                line_count = len(str(content).splitlines())
                snippet = "\n".join(str(content).splitlines()[:60])
                report_lines += [
                    "## Source Code",
                    f"_({line_count} lines total; showing first 60)_",
                    "```python",
                    snippet,
                    "```" if line_count <= 60 else "```\n_[truncated]_",
                    "",
                ]
            except Exception as e:
                report_lines.append(f"⚠️ Could not read file: {e}\n")
        else:
            report_lines.append("⚠️ read_file tool not available.\n")

        # ── Step 2: 代码结构骨架 ─────────────────────────────────
        get_repo_map = tool_handlers.get("get_repo_map")
        if get_repo_map:
            try:
                # 如果传的是文件，取其父目录
                scan_path = path if os.path.isdir(path) else os.path.dirname(path)
                repo_map = get_repo_map(path=scan_path)
                report_lines += [
                    "## Code Structure (AST Repo Map)",
                    "```",
                    str(repo_map)[:2000],
                    "```",
                    "",
                ]
            except Exception as e:
                logger.warning(f"[CodeReviewSkill] get_repo_map failed: {e}")
                report_lines.append(f"⚠️ Repo map unavailable: {e}\n")

        # ── Step 3: Lint ─────────────────────────────────────────
        sandbox_bash = tool_handlers.get("sandbox_bash")
        run_bash = tool_handlers.get("run_bash")
        executor = sandbox_bash or run_bash

        if executor:
            lint_cmd = f"pip install flake8 -q && flake8 {path} --max-line-length=120 --count"
            try:
                if sandbox_bash:
                    lint_result = sandbox_bash(command=lint_cmd, image="python:3.11-slim")
                else:
                    lint_result = run_bash(command=lint_cmd)
                report_lines += [
                    "## Linting (flake8)",
                    "```",
                    str(lint_result)[:2000],
                    "```",
                    "",
                ]
            except Exception as e:
                logger.warning(f"[CodeReviewSkill] Lint failed: {e}")
                report_lines.append(f"⚠️ Lint failed: {e}\n")

            # ── Step 4: 单元测试 ─────────────────────────────────
            if run_tests:
                # 确定测试目录（向上找 tests/ 或就在当前目录）
                check_dir = path if os.path.isdir(path) else os.path.dirname(path)
                full_cmd = f"cd {check_dir} && pip install pytest -q && {test_command}"
                try:
                    if sandbox_bash:
                        test_result = sandbox_bash(command=full_cmd, image="python:3.11-slim")
                    else:
                        test_result = run_bash(command=full_cmd)
                    report_lines += [
                        "## Test Results",
                        "```",
                        str(test_result)[:3000],
                        "```",
                        "",
                    ]
                except Exception as e:
                    logger.warning(f"[CodeReviewSkill] Tests failed: {e}")
                    report_lines.append(f"⚠️ Tests failed to run: {e}\n")
        else:
            report_lines.append("⚠️ Neither sandbox_bash nor run_bash available for lint/test.\n")

        report_lines += [
            "---",
            "_Review completed by CodeReviewSkill_",
        ]

        return "\n".join(report_lines)
