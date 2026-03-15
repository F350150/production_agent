"""
tools/registry.py - 工具组件注册中心 (LangChain 1.0 重构版)

【设计意图】
使用 LangChain 的 @tool 装饰器自动生成工具 Schema，替代原来手写的 JSON Schema + Handler 映射表。
保留了角色权限分组逻辑（不同角色只能访问特定的工具子集）。

底层工具实现（system_tools.py, web_tools.py 等）完全不变。
"""

from typing import Optional, List
from pathlib import Path
from langchain_core.tools import tool, BaseTool, StructuredTool

from .system_tools import SystemTools, WORKDIR
from .ast_tools import ASTTools
from .rag_tools import RAGTools
from .web_tools import WebTools
from .docker_tools import DockerTools
from .playwright_tools import PlaywrightTools
from .computer_tools import ComputerTools
from .mcp_registry import mcp_registry
from skills.skill_registry import skill_registry


# ==============================================================================
# 基础工具定义（使用 @tool 装饰器自动生成 Schema）
# ==============================================================================

# --- 文件系统工具 ---

@tool
async def run_bash(command: str) -> str:
    """Execute a bash command on the local system."""
    import asyncio
    return await asyncio.to_thread(SystemTools.run_bash, command)

@tool
async def read_file(path: str) -> str:
    """Read the contents of a file."""
    import asyncio
    return await asyncio.to_thread(SystemTools.read_file, path)

@tool
async def write_file(path: str, content: str) -> str:
    """Write entire content to a file. Subject to HITL if file exists."""

@tool
def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Replace exact text snippet in an existing file."""
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


# --- Computer Use 工具 ---

@tool
def computer_screenshot() -> dict:
    """Capture a screenshot of the entire computer screen."""
    return ComputerTools.screenshot()

@tool
def mouse_move(x: int, y: int) -> str:
    """Move the system mouse to (x, y) coordinates."""
    return ComputerTools.mouse_move(x, y)

@tool
def mouse_click(button: str = "left") -> str:
    """Click the mouse at current position."""
    return ComputerTools.mouse_click(button)

@tool
def key_type(text: str) -> str:
    """Type text into the current system focus."""
    return ComputerTools.key_type(text)


# --- 上下文管理工具 ---

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
        Spawn a new background sub-agent in an isolated context to work on a specific prompt.
        Roles available: 'Explore', 'Research', 'Test', 'CodeReview', 'Document'.
        Name must be unique. The sub-agent will run concurrently and report back its findings.
        """
        import asyncio
        import nest_asyncio
        nest_asyncio.apply()
        
        # 由于 spawn 现在是一个 sync wrapper for an async task creation (asyncio.create_task),
        # 这意味着在标准环境下，LangGraph 会在自己的 event loop 执行 tools。
        # 已经将其实现为 a sync interface spawning a task into the running loop
        return team_manager.spawn(name, role, prompt)

    @tool
    def subagent_status() -> str:
        """Check the status of all dynamically spawned sub-agents."""
        return team_manager.list_all()

    return [spawn_subagent, subagent_status]


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
    def get_all_tools(todo_manager=None, team_manager=None) -> List[BaseTool]:
        """获取所有 LangChain 工具实例"""
        ToolRegistry._ensure_initialized()

        tools = [
            run_bash, read_file, write_file, edit_file, list_files,
            get_repo_map, index_codebase, semantic_search_code,
            web_search, fetch_url, sandbox_bash,
            browser_open, browser_screenshot, browser_click, browser_type, browser_scroll,
            computer_screenshot, mouse_move, mouse_click, key_type,
            compress,
        ]

        if todo_manager:
            tools.extend(create_task_tools(todo_manager))
            
        if team_manager:
            tools.extend(create_team_tools(team_manager))

        return tools

    @staticmethod
    def get_role_tools(role: str, todo_manager=None, team_manager=None) -> List[BaseTool]:
        """
        根据角色下发工具子集

        【设计意图】
        不同角色有不同的职责边界。PM 不能编辑代码，Coder 不能审批设计。
        通过白名单过滤避免 LLM 的幻觉和越权。
        """
        ToolRegistry._ensure_initialized()

        role_allowed = {
            "ProductManager": [
                "web_search", "fetch_url", "compress",
                "task_create", "task_update", "task_claim", "task_list",
                "browser_open", "browser_screenshot", "computer_screenshot",
                "spawn_subagent", "subagent_status",
            ],
            "Architect": [
                "get_repo_map", "index_codebase", "semantic_search_code",
                "read_file", "list_files", "compress",
                "task_create", "task_update", "task_claim", "task_list",
                "spawn_subagent", "subagent_status",
            ],
            "Coder": [
                "read_file", "write_file", "edit_file", "run_bash", "list_files", "compress",
                "task_update", "task_claim", "task_list",
                "browser_open", "browser_screenshot", "browser_click", "browser_type", "browser_scroll",
                "computer_screenshot", "mouse_move", "mouse_click", "key_type",
            ],
            "QA_Reviewer": [
                "sandbox_bash", "read_file", "write_file", "run_bash", "compress",
                "task_update", "task_claim", "task_list",
                "browser_open", "browser_screenshot", "computer_screenshot",
                "web_search", "fetch_url",
            ],
        }

        all_tools = ToolRegistry.get_all_tools(todo_manager, team_manager)
        allowed_names = role_allowed.get(role, [])

        if not allowed_names:
            return all_tools  # 未知角色返回全部

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
    def get_base_handlers(todo_manager):
        """兼容旧接口：返回工具名 -> 执行函数的映射"""
        all_tools = ToolRegistry.get_all_tools(todo_manager)
        return {t.name: (lambda tool=t: lambda **kw: tool.invoke(kw))(t) for t in all_tools}
