import os
from pathlib import Path

# ==============================================================================
# 路径管理器 (Path Manager)
# 
# 用于解耦生产环境中的各种物理路径。
# 无论是在 repo 根目录运行，还是作为一个包安装后在任意目录运行，都能正确找到配置和数据。
# ==============================================================================

# 1. 软件包根目录 (Package Root) - production_agent 源码所在的目录
PACKAGE_ROOT = Path(__file__).parent.parent.absolute()

# 2. 当前工作空间 (Workspace) - 用户运行 Agent 的目录
# 这是存放 .env, .team/ 数据, 历史记录, 以及 Agent 操作代码的首选位置
WORKSPACE_DIR = Path(os.getcwd()).absolute()

# 3. 数据与持久化目录
TEAM_DIR = WORKSPACE_DIR / ".team"
DB_PATH = TEAM_DIR / ".team_db.sqlite"

# 确保关键目录存在
def ensure_dirs():
    TEAM_DIR.mkdir(parents=True, exist_ok=True)

# 4. 环境变量文件定位逻辑
def get_env_path():
    """
    优先级：
    1. 当前工作目录下的 .env
    2. HOME 目录下的 .production_agent.env (可选)
    3. 软件包根目录下的 .env (开发测试常用)
    """
    local_env = WORKSPACE_DIR / ".env"
    if local_env.exists():
        return local_env
    
    home_env = Path.home() / ".production_agent.env"
    if home_env.exists():
        return home_env
        
    package_env = PACKAGE_ROOT / ".env"
    if package_env.exists():
        return package_env
        
    return None

# 5. 杂项文件
LOG_FILE = WORKSPACE_DIR / ".agent_trace.log"
HISTORY_FILE = WORKSPACE_DIR / ".agent_history"
