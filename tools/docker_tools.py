import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

class DockerTools:
    """
    运行环境安全隔离层 (Runtime Docker Sandbox)
    
    【设计意图】
    让 Agent 在一台只活了几秒钟的临时独立虚拟机中乱跑代码，防止破坏宿主机本地物理根目录。
    这对进行黑盒分析、依赖测试非常有用且免去挂马风险。
    """
    
    @staticmethod
    def sandbox_bash(command: str, image: str = "python:3.11-slim", workdir: Path = None) -> str:
        """
        利用 docker 官方原生 SDK 调起后台 daemon 进行执行，包含 Volume 挂载能力
        使得沙盒容器内部能够识别外层的代码目录块。
        """
        logger.info(f"Tool sandbox_bash: {command} in {image}")
        if not DOCKER_AVAILABLE:
            return "Error: Docker SDK not installed. Please run: pip install docker"
        
        try:
            client = docker.from_env()
        except Exception as e:
            return f"Error connecting to Docker Daemon (is it running?): {e}"
            
        try:
            # remove=True 保证即用即毁，不占磁盘空间
            output_bytes = client.containers.run(
                image,
                command=["sh", "-c", command],
                volumes={str(workdir.absolute()): {'bind': '/workspace', 'mode': 'rw'}},
                working_dir='/workspace',
                detach=False,
                remove=True,
                stdout=True,
                stderr=True
            )
            # 兜底：处理非常规字符与超大日志流
            return output_bytes.decode('utf-8', errors='replace')[:50000]
        except docker.errors.ContainerError as e:
            logger.error(f"Sandbox container error: {e}")
            return f"Sandbox execution failed (Exit Code {e.exit_status}):\n{e.stderr.decode('utf-8', errors='replace')[:50000]}"
        except Exception as e:
            logger.error(f"Sandbox failed: {e}")
            return f"Sandbox failed: {e}"
