import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

from utils.paths import WORKSPACE_DIR

# 全局工作区路径，防止 Agent 乱爬出目录
WORKDIR = WORKSPACE_DIR

# 针对原生 Mac OS 的 HITL 危险命令拦截名单
DANGEROUS_COMMANDS = ['rm -rf /', 'mkfs', 'dd', 'shutdown', 'reboot', 'halt', 'sudo']

class SystemTools:
    """
    通用操作系统层工具 (SystemTools)
    【核心职责】
    管理与宿主机最底层、最关键的文件读写和 Shell 调用。
    出于生产安全考虑（防止越权或者误删），加入了人为断点审查（HITL）。
    """
    
    @staticmethod
    def run_bash(command: str) -> str:
        """
        在宿主机直接执行原生的 /bin/sh 脚本。
        危险命令触发 Human-in-the-loop 人类审核。
        如果为了绝对安全，应当使用 docker_tools 里的 sandbox_bash 代替！
        """
        logger.info(f"Tool run_bash: {command}")
        
        # 安全拦截：包含危险命令时，直接记录警告（现在由 SwarmOrchestrator 在上层统一拦截）
        if any(cmd in command for cmd in DANGEROUS_COMMANDS):
            logger.warning(f"Agent is running a potentially dangerous command: {command}")
                
        try:
            res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60, cwd=str(WORKDIR))
            out = res.stdout + res.stderr
            status = f"Command exited with code {res.returncode}.\n"
            
            # 截取过长输出，防止上下文溢出导致 Token 爆炸
            max_chars = 30000
            if len(out) > max_chars:
                out = out[:max_chars] + f"\n\n... (truncated {len(out) - max_chars} characters, if you need more info ask the user or run a targeted command) ..."
            
            return status + out
        except subprocess.TimeoutExpired:
            return "Command execution timed out after 60s."
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return f"Error executing command: {e}"

    @staticmethod
    def read_file(path: str) -> str:
        """从工作区读取绝对或相对路径的内容"""
        logger.info(f"Tool read_file: {path}")
        p = WORKDIR / path
        if p.is_dir():
            return f"Note: {path} is a directory. To list its contents, use the `list_files` tool. To read a specific file, provide its path."
        if not p.is_file():
            return f"Error: File {path} does not exist."
        try:
            content = p.read_text(encoding="utf-8")
            if len(content) > 50000:
                return content[:50000] + f"\n\n... (file truncated, total {len(content)} chars. Context too large to ingest.) ..."
            return content
        except Exception as e:
            return f"Error reading file {path}: {e}"

    @staticmethod
    def write_file(path: str, content: str) -> str:
        """向工作区写入文件。关键路径文件被覆盖前将触发 HITL。"""
        logger.info(f"Tool write_file: {path}")
        p = WORKDIR / path
        
        # 对于已有文件进行全量覆盖时，如果不是在临时目录，记录警告（现在由 SwarmOrchestrator 在上层统一拦截）
        if p.exists() and "tmp" not in str(p):
            logger.warning(f"Agent is overwriting existing file: {path}")
                
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error writing file {path}: {e}"

    @staticmethod
    def edit_file(path: str, old_text: str, new_text: str) -> str:
        """
        以“补丁”(Patch)的形式精准替换文件的某一小段内容。
        这极大地节省了全量读写造成的 Output Tokens 浪费。
        """
        logger.info(f"Tool edit_file: {path}")
        p = WORKDIR / path
        if not p.is_file():
            return f"Error: File {path} does not exist."
        try:
            content = p.read_text(encoding="utf-8")
            if old_text not in content:
                # Agent 经常因为格式符不匹配导致替换失败，抛出详细信息辅助它重新定位
                return "Error: old_text not found in file. Ensure exact match including whitespace."
            new_content = content.replace(old_text, new_text, 1)
            p.write_text(new_content, encoding="utf-8")
            return f"Successfully updated {path}"
        except Exception as e:
            return f"Error updating file {path}: {e}"

    @staticmethod
    def list_files(path: str) -> str:
        """列出一个目录下的内容概览"""
        logger.info(f"Tool run_files: {path}")
        p = WORKDIR / path
        if not p.is_dir():
            return f"Error: Directory {path} does not exist."
        try:
            # 去除一些无需关心的超大文件夹，防止 Token 消耗殆尽
            res = subprocess.run(f"find '{p}' -maxdepth 2 -not -path '*/.git*' -not -path '*/node_modules*'", shell=True, capture_output=True, text=True)
            out = res.stdout + res.stderr
            return out[:10000]
        except Exception as e:
            return f"Error listing files: {e}"
