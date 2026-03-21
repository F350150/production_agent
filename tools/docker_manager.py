import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class DockerManager:
    """
    Docker 容器管理工具

    【设计意图】
    允许 Agent 管理 Docker 容器生命周期，包括：
    - 列出/启动/停止容器
    - 查看容器日志
    - 在容器内执行命令
    - 使用 docker-compose 部署服务栈
    """

    @staticmethod
    def _run_docker(cmd: str, timeout: int = 30) -> str:
        """执行 docker 命令"""
        try:
            result = subprocess.run(
                f"docker {cmd}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                return f"Docker error: {result.stderr.strip()}"
            return result.stdout.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: docker command timed out after {timeout}s"
        except FileNotFoundError:
            return "Error: Docker CLI not found. Is Docker installed?"
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def ps(all_containers: bool = False) -> str:
        """列出 Docker 容器。all_containers=True 包含已停止的。"""
        logger.info("Tool docker_ps")
        flag = "-a" if all_containers else ""
        return DockerManager._run_docker(f"ps {flag} --format 'table {{{{.ID}}}}\\t{{{{.Names}}}}\\t{{{{.Status}}}}\\t{{{{.Ports}}}}'")

    @staticmethod
    def logs(container: str, tail: int = 50, follow: bool = False) -> str:
        """查看容器日志。tail: 显示最后 N 行。"""
        logger.info(f"Tool docker_logs: {container}")
        tail = min(tail, 200)  # 安全上限
        return DockerManager._run_docker(f"logs --tail {tail} {container}")

    @staticmethod
    def exec_cmd(container: str, command: str) -> str:
        """在指定容器内执行命令"""
        logger.info(f"Tool docker_exec: {container} -> {command}")
        return DockerManager._run_docker(f"exec {container} {command}")

    @staticmethod
    def start(container: str) -> str:
        """启动容器"""
        logger.info(f"Tool docker_start: {container}")
        return DockerManager._run_docker(f"start {container}")

    @staticmethod
    def stop(container: str) -> str:
        """停止容器"""
        logger.info(f"Tool docker_stop: {container}")
        return DockerManager._run_docker(f"stop {container}")

    @staticmethod
    def compose_up(path: str = ".", detach: bool = True) -> str:
        """启动 docker-compose 服务栈"""
        logger.info(f"Tool docker_compose_up: {path}")
        flag = "-d" if detach else ""
        try:
            result = subprocess.run(
                f"docker compose -f {path}/docker-compose.yml up {flag}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return f"Docker Compose error: {result.stderr.strip()}"
            return result.stdout.strip() or "Services started successfully."
        except Exception as e:
            return f"Docker Compose failed: {e}"

    @staticmethod
    def compose_down(path: str = ".") -> str:
        """关闭 docker-compose 服务栈"""
        logger.info(f"Tool docker_compose_down: {path}")
        try:
            result = subprocess.run(
                f"docker compose -f {path}/docker-compose.yml down",
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                return f"Docker Compose error: {result.stderr.strip()}"
            return result.stdout.strip() or "Services stopped successfully."
        except Exception as e:
            return f"Docker Compose down failed: {e}"

    @staticmethod
    def images() -> str:
        """列出本地 Docker 镜像"""
        logger.info("Tool docker_images")
        return DockerManager._run_docker("images --format 'table {{.Repository}}\\t{{.Tag}}\\t{{.Size}}\\t{{.CreatedSince}}'")
