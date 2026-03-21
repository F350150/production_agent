"""
tools/registry.py - 工具组件注册中心 (LangChain 1.0 重构版)

【设计意图】
使用 LangChain 的 @tool 装饰器自动生成工具 Schema，替代原来手写的 JSON Schema + Handler 映射表。
保留了角色权限分组逻辑（不同角色只能访问特定的工具子集）。

底层工具实现（system_tools.py, web_tools.py 等）完全不变。
"""

import yaml
import logging
from typing import Optional, List, Dict
from pathlib import Path
from langchain_core.tools import tool, BaseTool, StructuredTool

from .system_tools import SystemTools, WORKDIR
from .ast_tools import ASTTools
from .rag_tools import RAGTools
from .web_tools import WebTools
from .docker_tools import DockerTools
from .playwright_tools import PlaywrightTools
from .computer_tools import ComputerTools
from .git_tools import GitTools
from .db_tools import DatabaseTools
from .docker_manager import DockerManager
from .notify_tools import NotifyTools
from .mcp_registry import mcp_registry
from skills.skill_registry import skill_registry

logger = logging.getLogger(__name__)

_TOOL_HANDLERS_REGISTRY: dict = {}


# ==============================================================================
# 基础工具定义（使用 @tool 装饰器自动生成 Schema）
# ==============================================================================

# --- 治理配置加载 ---
GOVERNANCE_CONFIG_PATH = Path(__file__).parent.parent / "config" / "governance.yaml"

def load_governance():
    """从 yaml 加载治理配置"""
    if not GOVERNANCE_CONFIG_PATH.exists():
        return {}
    try:
        with open(GOVERNANCE_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load governance config: {e}")
        return {}

GOVERNANCE = load_governance()
SANDBOX_ENFORCED = GOVERNANCE.get("sandbox_settings", {}).get("force_docker_sandbox", False)

# --- 文件系统工具 (带沙箱增强) ---

@tool
async def run_bash(command: str) -> str:
    """Execute a bash command on the local system (or in a Docker sandbox if enforced)."""
    import asyncio
    from .docker_tools import DOCKER_AVAILABLE
    
    if SANDBOX_ENFORCED:
        # Check if Docker is actually running
        docker_running = False
        if DOCKER_AVAILABLE:
            try:
                import docker
                docker.from_env().ping()
                docker_running = True
            except:
                docker_running = False
        
        if not docker_running:
            msg = "⚠️ Sandbox Enforced but Docker is NOT running. "
            if not DOCKER_AVAILABLE:
                msg += "Please install docker SDK: pip install docker"
            else:
                msg += "Please start your Docker Desktop/Daemon."
            
            # 允许在这种情况下尝试本地执行（带警告），否则系统完全不可用
            logger.warning(msg + f" Falling back to LOCAL for: {command}")
            return f"{msg}\n[EMERGENCY LOCAL FALLBACK]\n" + await asyncio.to_thread(SystemTools.run_bash, command)
            
        logger.info(f"Enforcing Sandbox for run_bash: {command}")
        return await asyncio.to_thread(DockerTools.sandbox_bash, command, "python:3.11-slim", WORKDIR)
    
    return await asyncio.to_thread(SystemTools.run_bash, command)

@tool
async def read_file(path: str) -> str:
    """Read the contents of a file."""
    import asyncio
    return await asyncio.to_thread(SystemTools.read_file, path)

@tool
async def write_file(path: str, content: str) -> str:
    """Write entire content to a file. Subject to HITL if file exists."""
    import asyncio
    # 注意：write_file 在沙箱中较难实现同步回宿主机，目前优先保留宿主机写入（由 HITL 保护）
    return await asyncio.to_thread(SystemTools.write_file, path, content)

@tool
async def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace exact text snippet in an existing file. Runs in sandbox if enforced."""
    import asyncio
    if SANDBOX_ENFORCED:
        # 在沙箱中执行 Python 脚本来安全修改文件
        # 使用环境变量传递内容，避免引号转义地狱
        py_code = """
import os
from pathlib import Path
path = Path(os.environ['EDIT_PATH'])
old = os.environ['EDIT_OLD']
new = os.environ['EDIT_NEW']
if not path.exists():
    print(f'ERROR: File {path} not found')
    exit(1)
content = path.read_text(encoding='utf-8', errors='replace')
if old in content:
    path.write_text(content.replace(old, new), encoding='utf-8')
    print('SUCCESS')
else:
    print('ERROR: old_text not found')
"""
        # 我们需要修改 sandbox_bash 来支持环境变量，或者通过 sh -c 传递
        # 简单起见，这里先用 printf 构造环境变量再执行
        env_prefix = f"export EDIT_PATH='{path}' EDIT_OLD='{old_text}' EDIT_NEW='{new_text}' && "
        cmd = f"python3 -c \"{py_code}\""
        return await asyncio.to_thread(DockerTools.sandbox_bash, env_prefix + cmd, "python:3.11-slim", WORKDIR)
    
    return SystemTools.edit_file(path, old_text, new_text)

@tool
def list_files(path: str) -> str:
    """List files in a directory up to depth 2."""
    return SystemTools.list_files(path)


# --- AST 工具 ---

@tool
def get_repo_map(path: str) -> str:
    """Get an AST syntax skeleton map of up to 20 files in a directory to fast-read code structure."""
    return ASTTools.get_repo_map(path, WORKDIR)


# --- RAG 向量搜索工具 ---

@tool
def index_codebase(path: str) -> str:
    """Scan and chunk code files into VectorDB instance for semantic search."""
    return RAGTools.index_codebase(path, WORKDIR)

@tool
def semantic_search_code(query: str, n_results: int = 5) -> str:
    """Search the indexed RAG VectorDB for relevant code snippets using natural language."""
    return RAGTools.semantic_search_code(query, n_results, WORKDIR)


# --- Web 工具 ---

@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search DuckDuckGo to find information, documentation, or answers on the internet."""
    import asyncio
    return await asyncio.to_thread(WebTools.web_search, query, max_results)

@tool
async def fetch_url(url: str) -> str:
    """Fetch and extract readable text content from any webpage."""
    import asyncio
    return await asyncio.to_thread(WebTools.fetch_url, url)


# --- Docker 沙箱工具 ---

@tool
async def sandbox_bash(command: str, image: str = "python:3.11-slim") -> str:
    """Execute a safe shell command inside a disposable Docker container."""
    import asyncio
    return await asyncio.to_thread(DockerTools.sandbox_bash, command, image, WORKDIR)


# --- Playwright 浏览器工具 ---

@tool
async def browser_open(url: str) -> str:
    """Open a URL in a real browser and wait for load."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_open, url)

@tool
async def browser_screenshot() -> dict:
    """Capture a screenshot of the current browser page. Returns an image block."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_screenshot)

@tool
async def browser_full_screenshot() -> dict:
    """Capture full page screenshot including scrollable content."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_full_screenshot)

@tool
async def browser_click(selector: str) -> str:
    """Click an element on the page using a CSS selector."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_click, selector)

@tool
async def browser_type(selector: str, text: str) -> str:
    """Type text into an input field on the page."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_type, selector, text)

@tool
async def browser_scroll(direction: str = "down") -> str:
    """Scroll the browser page up or down."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_scroll, direction)

@tool
async def browser_new_tab(url: str = "") -> str:
    """Open a new browser tab, optionally navigating to a URL."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_new_tab, url)

@tool
async def browser_switch_tab(index: int) -> str:
    """Switch to a browser tab by index (0-based)."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_switch_tab, index)

@tool
async def browser_close_tab(index: int = -1) -> str:
    """Close a browser tab. -1 closes current tab."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_close_tab, index)

@tool
async def browser_list_tabs() -> str:
    """List all open browser tabs with titles and URLs."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_list_tabs)

@tool
async def browser_fill_form(fields_json: str) -> str:
    """Fill multiple form fields. fields_json: '{"#username": "admin", "#password": "123"}'"""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_fill_form, fields_json)

@tool
async def browser_get_text(selector: str = "body") -> str:
    """Get plain text content of a page element. Default: entire body."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_get_text, selector)

@tool
async def browser_save_cookies(path: str = "/tmp/browser_cookies.json") -> str:
    """Save browser cookies to file for session persistence."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_save_cookies, path)

@tool
async def browser_load_cookies(path: str = "/tmp/browser_cookies.json") -> str:
    """Load cookies from file to restore login session."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_load_cookies, path)

@tool
async def browser_download(url: str, save_path: str = "/tmp/") -> str:
    """Download a file from URL to local path."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_download, url, save_path)

@tool
async def browser_pdf_extract(url: str) -> str:
    """Open a PDF URL and extract text content."""
    import asyncio
    return await asyncio.to_thread(PlaywrightTools.browser_pdf_extract, url)


# --- Computer Use 工具 ---

@tool
def computer_screenshot() -> dict:
    """Capture a screenshot of the entire computer screen."""
    return ComputerTools.screenshot()

@tool
def screenshot_region(x: int, y: int, width: int, height: int) -> dict:
    """Capture a specific region of the screen (x, y, width, height). Use for targeted screenshot to save tokens."""
    return ComputerTools.screenshot_region(x, y, width, height)

@tool
def ocr_screen(region: str = "") -> str:
    """OCR the screen to extract text. Works even if LLM doesn't support vision. region format: 'x,y,w,h' or empty for fullscreen."""
    return ComputerTools.ocr_screen(region if region else None)

@tool
def screen_record(duration: int = 3, fps: int = 4) -> str:
    """Record screen as GIF animation. duration: seconds (max 10), fps: frames per second (max 8). Returns file path."""
    return ComputerTools.screen_record(duration, fps)

@tool
def mouse_move(x: int, y: int) -> str:
    """Move the system mouse to (x, y) coordinates."""
    return ComputerTools.mouse_move(x, y)

@tool
def mouse_click(button: str = "left") -> str:
    """Click the mouse at current position. button: left/right/middle."""
    return ComputerTools.mouse_click(button)

@tool
def mouse_double_click(x: int = -1, y: int = -1) -> str:
    """Double-click the mouse. Specify (x, y) or use (-1, -1) for current position."""
    return ComputerTools.mouse_double_click(x if x >= 0 else None, y if y >= 0 else None)

@tool
def mouse_drag(x1: int, y1: int, x2: int, y2: int) -> str:
    """Drag from (x1, y1) to (x2, y2). Useful for moving files, resizing windows."""
    return ComputerTools.mouse_drag(x1, y1, x2, y2)

@tool
def mouse_scroll(clicks: int = -3) -> str:
    """Scroll mouse wheel. Positive = up, negative = down."""
    return ComputerTools.mouse_scroll(clicks)

@tool
def key_type(text: str) -> str:
    """Type text into the current system focus."""
    return ComputerTools.key_type(text)

@tool
def key_combo(keys: str) -> str:
    """Execute keyboard shortcut. Format: 'cmd+c', 'ctrl+shift+f', 'alt+tab'. Supports: cmd, ctrl, alt, shift, enter, esc, tab, space, etc."""
    return ComputerTools.key_combo(keys)


# --- Git 版本控制工具 ---

@tool
def git_status() -> str:
    """Show current git repository status (modified/staged/untracked files)."""
    return GitTools.status()

@tool
def git_diff(file: str = "", staged: bool = False) -> str:
    """Show file changes diff. file: optional specific file. staged: only staged changes."""
    return GitTools.diff(file, staged)

@tool
def git_log(n: int = 10) -> str:
    """Show last N git commits."""
    return GitTools.log(n)

@tool
def git_blame(file: str, start_line: int = 1, end_line: int = 50) -> str:
    """Show line-by-line authorship for a file (who changed what and when)."""
    return GitTools.blame(file, start_line, end_line)

@tool
def git_commit(message: str, add_all: bool = True) -> str:
    """Commit changes to git. add_all: whether to 'git add -A' first."""
    return GitTools.commit(message, add_all)

@tool
def git_create_branch(branch_name: str) -> str:
    """Create and switch to a new git branch."""
    return GitTools.create_branch(branch_name)

@tool
def git_create_pr(title: str, body: str = "") -> str:
    """Create a GitHub Pull Request using gh CLI."""
    return GitTools.create_pr(title, body)


# --- 数据库工具 ---

@tool
def db_connect(uri: str, alias: str = "default") -> str:
    """Connect to a database. uri examples: 'sqlite:///test.db', 'postgresql://user:pass@host/db'."""
    return DatabaseTools.connect(uri, alias)

@tool
def db_query(sql: str, alias: str = "default") -> str:
    """Execute SQL query and return results as table."""
    return DatabaseTools.query(sql, alias)

@tool
def db_schema(table: str = "", alias: str = "default") -> str:
    """Inspect database schema. Empty table = list all tables."""
    return DatabaseTools.schema(table, alias)

@tool
def db_explain(sql: str, alias: str = "default") -> str:
    """Analyze SQL query execution plan for performance optimization."""
    return DatabaseTools.explain(sql, alias)


# --- Docker 管理工具 ---

@tool
def docker_ps(all_containers: bool = False) -> str:
    """List Docker containers. all_containers: include stopped ones."""
    return DockerManager.ps(all_containers)

@tool
def docker_logs(container: str, tail: int = 50) -> str:
    """View container logs. tail: how many lines."""
    return DockerManager.logs(container, tail)

@tool
def docker_exec(container: str, command: str) -> str:
    """Execute a command inside a Docker container."""
    return DockerManager.exec_cmd(container, command)

@tool
def docker_start(container: str) -> str:
    """Start a Docker container."""
    return DockerManager.start(container)

@tool
def docker_stop(container: str) -> str:
    """Stop a Docker container."""
    return DockerManager.stop(container)

@tool
def docker_compose_up(path: str = ".") -> str:
    """Start docker-compose service stack."""
    return DockerManager.compose_up(path)

@tool
def docker_compose_down(path: str = ".") -> str:
    """Stop docker-compose service stack."""
    return DockerManager.compose_down(path)

@tool
def docker_images() -> str:
    """List local Docker images."""
    return DockerManager.images()


# --- 通知推送工具 ---

@tool
def notify_macos(title: str, message: str) -> str:
    """Send macOS native notification with sound."""
    return NotifyTools.notify_macos(title, message)

@tool
def notify_email(to: str, subject: str, body: str) -> str:
    """Send email notification. Requires SMTP_SERVER, SMTP_USER, SMTP_PASS env vars."""
    return NotifyTools.notify_email(to, subject, body)

@tool
def notify_webhook(url: str, message: str = "", payload: str = "") -> str:
    """Send webhook notification to Slack/Discord/Lark. Either message or JSON payload."""
    return NotifyTools.notify_webhook(url, payload if payload else None, message)

@tool
def notify_say(message: str, voice: str = "Samantha") -> str:
    """macOS text-to-speech. Voice options: Samantha(EN), Ting-Ting(CN), Alex(EN)."""
    return NotifyTools.notify_say(message, voice)

@tool
def compress() -> str:
    """Manually signal that you have completed a major milestone, forcing the system to wipe and summarize the context window."""
    return "Context compressed by Agent."


# ==============================================================================
# 任务管理工具（需要运行时绑定 TaskManager 实例）
# ==============================================================================

def create_task_tools(todo_manager):
    """
    创建绑定了 TaskManager 的任务管理工具集

    【设计意图】
    任务工具需要访问 todo_manager 实例，因此不能在模块级别直接定义。
    通过工厂函数在运行时创建闭包绑定。
    """

    @tool
    def task_create(subject: str, description: str = "", required_role: str = "") -> str:
        """Create a new task in the team's task list. Optionally specify which agent (ProductManager, Architect, Coder, QA_Reviewer) should handle it."""
        return todo_manager.create(subject, description, required_role or None)

    @tool
    def task_update(task_id: int, status: str = "", add_blocked_by: list = None) -> str:
        """Update the status (pending/in_progress/completed/blocked) or dependencies of an existing task."""
        return todo_manager.update(task_id, status=status or None, add_blocked_by=add_blocked_by)

    @tool
    def task_claim(task_id: int, agent_role: str = "") -> str:
        """Claim a task for the current agent to work on."""
        return todo_manager.claim(task_id, "current_agent", agent_role or None)

    @tool
    def task_list() -> str:
        """List all tasks and their current status."""
        return todo_manager.list_all()

    return [task_create, task_update, task_claim, task_list]

# ==============================================================================
# 团队/子代理管理工具（需要运行时绑定 TeammateManager 实例）
# ==============================================================================

def create_team_tools(team_manager):
    """
    创建绑定了 TeammateManager 的工具集，用于动态 Spawn Subagents
    """
    
    @tool
    def spawn_subagent(name: str, role: str, prompt: str) -> str:
        """
        Spawn a new background sub-agent (LangGraph-backed) in an isolated context to work on a specific prompt.
        Roles available: 'Explore', 'Research', 'Test', 'CodeReview', 'Document'.
        Name must be unique. Progress is persisted in SQLite via thread_id: teammate_{name}.
        The sub-agent will run concurrently and report back its findings.
        """
        return team_manager.spawn(name, role, prompt)

    @tool
    def subagent_status() -> str:
        """Check the status of all dynamically spawned sub-agents."""
        return team_manager.list_all()

    return [spawn_subagent, subagent_status]


# ==============================================================================
# 技能工具（use_skill - 封装多个基础工具调用的高级技能）
# ==============================================================================

@tool
async def use_skill(skill_name: str, parameters: dict) -> str:
    """
    Execute a pre-built multi-step skill that orchestrates multiple tools internally.
    Available skills are registered in the SkillRegistry.
    
    Skills provide high-level operations like:
    - debug_explain: Parse error tracebacks and suggest fixes
    - generate_test: Generate pytest test cases from functions
    - api_design_review: Analyze API design quality
    - dependency_analysis: Analyze import/call graphs
    - code_migration: Migrate code between frameworks
    """
    handlers = _TOOL_HANDLERS_REGISTRY
    if not handlers:
        return "Error: Tool handlers not initialized. Please restart the agent."
    
    skill_schema = skill_registry.get_skill_tool_schema()
    if not skill_schema:
        return "Error: No skills available."
    
    skill_names = skill_registry.get_skill_names()
    if skill_name not in skill_names:
        return f"Error: Unknown skill '{skill_name}'. Available: {skill_names}"
    
    skill_handler = skill_registry.get_skill_handler(handlers)
    try:
        return skill_handler(skill_name=skill_name, parameters=parameters)
    except Exception as e:
        logger.error(f"[use_skill] Error executing skill '{skill_name}': {e}")
        return f"Error executing skill '{skill_name}': {e}"


# ==============================================================================
# 工具注册表类（保留角色权限分组逻辑）
# ==============================================================================

class ToolRegistry:
    """
    工具组件注册中心 (Tool Registry) - LangChain 版本

    【设计意图】
    沿用原有的角色权限分组逻辑，但底层改用 LangChain @tool 对象。
    不同角色只能访问特定的工具子集，防止 LLM 越权操作。
    """

    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls):
        """懒加载初始化 MCP 和 Skill 系统"""
        if not cls._initialized:
            mcp_registry.initialize()
            skill_registry.initialize()
            cls._initialized = True

    @staticmethod
    def _create_mcp_tools() -> List[BaseTool]:
        """将 MCP schemas 转换为 LangChain StructuredTool"""
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, Field
        
        mcp_schemas = mcp_registry.get_mcp_tools_schema()
        mcp_handlers = mcp_registry.get_mcp_handlers()
        
        mcp_tools = []
        for schema in mcp_schemas:
            tool_name = schema.get("name")
            if not tool_name or tool_name not in mcp_handlers:
                continue
            
            handler = mcp_handlers[tool_name]
            description = schema.get("description", "")
            input_schema = schema.get("input_schema", {"type": "object", "properties": {}})
            
            # 从 input_schema 构建 Pydantic 模型
            properties = input_schema.get("properties", {})
            field_definitions = {}
            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "string")
                field_definitions[param_name] = (str, Field(description=param_info.get("description", "")))
            
            class ToolArgs(BaseModel):
                """动态创建的 MCP 工具参数模型"""
                pass
            
            for name, (typ, field) in field_definitions.items():
                ToolArgs.__fields__[name] = (typ, field)
            
            def make_func(h):
                def call(**kwargs):
                    return h(**kwargs)
                return call
            
            try:
                tool = StructuredTool(
                    name=tool_name,
                    description=description,
                    args_schema=ToolArgs,
                    func=make_func(handler),
                )
                mcp_tools.append(tool)
                logger.debug(f"[ToolRegistry] Added MCP tool: {tool_name}")
            except Exception as e:
                logger.warning(f"[ToolRegistry] Failed to create MCP tool '{tool_name}': {e}")
        
        return mcp_tools

    @staticmethod
    def get_all_tools(todo_manager=None, team_manager=None) -> List[BaseTool]:
        """获取所有 LangChain 工具实例"""
        ToolRegistry._ensure_initialized()

        tools = [
            run_bash, read_file, write_file, edit_file, list_files,
            get_repo_map, index_codebase, semantic_search_code,
            web_search, fetch_url, sandbox_bash,
            browser_open, browser_screenshot, browser_full_screenshot,
            browser_click, browser_type, browser_scroll,
            browser_new_tab, browser_switch_tab, browser_close_tab, browser_list_tabs,
            browser_fill_form, browser_get_text,
            browser_save_cookies, browser_load_cookies, browser_download, browser_pdf_extract,
            computer_screenshot, screenshot_region, ocr_screen, screen_record,
            mouse_move, mouse_click, mouse_double_click, mouse_drag, mouse_scroll,
            key_type, key_combo,
            git_status, git_diff, git_log, git_blame, git_commit, git_create_branch, git_create_pr,
            db_connect, db_query, db_schema, db_explain,
            docker_ps, docker_logs, docker_exec, docker_start, docker_stop,
            docker_compose_up, docker_compose_down, docker_images,
            notify_macos, notify_email, notify_webhook, notify_say,
            compress, use_skill,
        ]

        # 添加 MCP 工具
        mcp_tools = ToolRegistry._create_mcp_tools()
        tools.extend(mcp_tools)

        if todo_manager:
            tools.extend(create_task_tools(todo_manager))
            
        if team_manager:
            tools.extend(create_team_tools(team_manager))

        return tools

    @staticmethod
    def get_role_tools(role: str, todo_manager=None, team_manager=None) -> List[BaseTool]:
        """
        根据角色下发工具子集 (基于 governance.yaml 配置)
        """
        ToolRegistry._ensure_initialized()

        if not _TOOL_HANDLERS_REGISTRY:
            ToolRegistry.get_base_handlers(todo_manager, team_manager)

        # 优先读取动态配置
        rbac = GOVERNANCE.get("role_permissions", {})
        allowed_names = rbac.get(role, [])

        # 如果配置中有 'base_tools'，则合并基础工具
        if "base_tools" in allowed_names:
            base_set = ["compress", "task_update", "task_claim", "task_list", "subagent_status"]
            allowed_names = list(set(allowed_names + base_set))

        all_tools = ToolRegistry.get_all_tools(todo_manager, team_manager)
        
        # 如果动态配置为空，使用硬编码兜底
        if not allowed_names:
            role_allowed_fallback = {
                "ProductManager": ["web_search", "fetch_url", "compress", "task_create", "task_update", "task_claim", "task_list"],
                "Architect": ["get_repo_map", "index_codebase", "read_file", "list_files", "compress"],
                "Coder": ["read_file", "write_file", "edit_file", "run_bash", "list_files", "compress"],
                "QA_Reviewer": ["sandbox_bash", "read_file", "run_bash", "compress", "web_search"],
            }
            allowed_names = role_allowed_fallback.get(role, [])

        if not allowed_names:
            return all_tools

        return [t for t in all_tools if t.name in allowed_names]

    # ---- 兼容层：保留旧 API 供未迁移的模块使用 ----

    @staticmethod
    def get_base_tools_schema():
        """兼容旧接口：返回工具的 JSON Schema 格式"""
        tools = ToolRegistry.get_all_tools()
        schemas = []
        for t in tools:
            schema = {
                "name": t.name,
                "description": t.description,
                "input_schema": t.args_schema.model_json_schema() if t.args_schema else {"type": "object", "properties": {}, "required": []},
            }
            if t.name in ["run_bash", "write_file", "edit_file"]:
                schema["is_destructive"] = True
            schemas.append(schema)
        return schemas

    @staticmethod
    def get_base_handlers(todo_manager, team_manager=None):
        """兼容旧接口：返回工具名 -> 执行函数的映射，同时更新全局处理器注册表供 use_skill 使用"""
        all_tools = ToolRegistry.get_all_tools(todo_manager, team_manager)
        handlers = {t.name: (lambda tool=t: lambda **kw: tool.invoke(kw))(t) for t in all_tools}
        _TOOL_HANDLERS_REGISTRY.update(handlers)
        return handlers
