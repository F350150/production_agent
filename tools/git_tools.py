import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class GitTools:
    """
    Git 深度集成工具

    【设计意图】
    提供 Git 版本控制的完整操作能力，让 Agent 能够：
    - 查看仓库状态、变更差异、提交历史
    - 进行代码溯源（blame）
    - 执行提交操作
    - 通过 GitHub CLI 创建 PR
    """

    @staticmethod
    def _run_git(cmd: str, cwd: str = ".") -> str:
        """执行 git 命令并返回输出"""
        try:
            result = subprocess.run(
                f"git {cmd}",
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return f"Git error (code {result.returncode}): {result.stderr.strip()}"
            return result.stdout.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: git command timed out after 30s"
        except Exception as e:
            return f"Error running git: {e}"

    @staticmethod
    def status(cwd: str = ".") -> str:
        """查看当前仓库状态（修改/暂存/未跟踪文件）"""
        logger.info("Tool git_status")
        return GitTools._run_git("status --short --branch", cwd)

    @staticmethod
    def diff(file: str = "", staged: bool = False, cwd: str = ".") -> str:
        """
        查看文件变更差异。
        file: 可选，指定文件路径。为空则显示所有变更。
        staged: 是否只看已暂存的变更。
        """
        logger.info(f"Tool git_diff: file={file}, staged={staged}")
        cmd = "diff"
        if staged:
            cmd += " --staged"
        if file:
            cmd += f" -- {file}"
        output = GitTools._run_git(cmd, cwd)
        # 限制输出长度避免 token 爆炸
        if len(output) > 5000:
            output = output[:5000] + f"\n\n... (truncated, total {len(output)} chars)"
        return output

    @staticmethod
    def log(n: int = 10, oneline: bool = True, cwd: str = ".") -> str:
        """查看最近 N 条提交历史"""
        logger.info(f"Tool git_log: n={n}")
        n = min(n, 50)  # 安全上限
        fmt = "--oneline" if oneline else '--format="%h %an %ar %s"'
        return GitTools._run_git(f"log -{n} {fmt}", cwd)

    @staticmethod
    def blame(file: str, start_line: int = 1, end_line: int = 50, cwd: str = ".") -> str:
        """
        对文件进行行级溯源（谁在什么时候改了哪行）。
        file: 文件路径
        start_line / end_line: 行范围
        """
        logger.info(f"Tool git_blame: {file} L{start_line}-{end_line}")
        return GitTools._run_git(f"blame -L {start_line},{end_line} {file}", cwd)

    @staticmethod
    def commit(message: str, add_all: bool = True, cwd: str = ".") -> str:
        """
        提交更改到 Git。
        message: 提交信息
        add_all: 是否先 git add -A
        """
        logger.info(f"Tool git_commit: {message}")
        if add_all:
            add_result = GitTools._run_git("add -A", cwd)
            if "error" in add_result.lower():
                return f"Git add failed: {add_result}"
        return GitTools._run_git(f'commit -m "{message}"', cwd)

    @staticmethod
    def create_branch(branch_name: str, cwd: str = ".") -> str:
        """创建并切换到新分支"""
        logger.info(f"Tool git_create_branch: {branch_name}")
        return GitTools._run_git(f"checkout -b {branch_name}", cwd)

    @staticmethod
    def create_pr(title: str, body: str = "", cwd: str = ".") -> str:
        """
        通过 GitHub CLI 创建 Pull Request。
        需要预先安装 gh CLI 并完成认证。
        """
        logger.info(f"Tool git_create_pr: {title}")
        try:
            # 检查 gh CLI 是否可用
            check = subprocess.run(
                "gh --version", shell=True, capture_output=True, text=True
            )
            if check.returncode != 0:
                return "Error: GitHub CLI (gh) not installed. Run: brew install gh && gh auth login"

            body_arg = f'--body "{body}"' if body else '--body ""'
            result = subprocess.run(
                f'gh pr create --title "{title}" {body_arg}',
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return f"PR creation failed: {result.stderr.strip()}"
            return result.stdout.strip()
        except Exception as e:
            return f"Error creating PR: {e}"
