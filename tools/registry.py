from pathlib import Path
from tools.system_tools import SystemTools, WORKDIR
from tools.ast_tools import ASTTools
from tools.rag_tools import RAGTools
from tools.web_tools import WebTools
from tools.docker_tools import DockerTools
from tools.mcp_registry import mcp_registry
from skills.skill_registry import skill_registry

class ToolRegistry:
    """
    工具组件注册中心 (Tool Registry)
    
    【设计意图】
    集中式管控。LLM 需要两个东西才能调用工具：
    1. TOOLS_SCHEMA: Json 描述，告诉大模型这个工具能干什么、入参是什么。
    2. TOOL_HANDLERS: 实际的 Python 闭包/函数反射映射表，当大模型下发指令后，靠它路由分发到真实代码上。
    
    提取此处使得主循环 (loop) 的代码极为清爽，所有新能力的添加只要修改这里即可。
    此处不包含 `task` (委派子任务) 核心工具，因为其依赖循环 import，会在 loop 初始化时动态注册。

    【扩展机制】
    - MCP 层：初始化时读取 MCP_SERVERS 环境变量，自动将外部 MCP 服务的工具并入基础工具集。
    - Skill 层：自动扫描 skills/builtin/ 目录，将多步驄技能封装为单一的 use_skill 工具。
    """
    
    # 标记是否已完成单例初始化
    _initialized: bool = False
    
    @classmethod
    def _ensure_initialized(cls):
        """
        懒加载初始化：首次调用时启动 MCP 客户端和 Skill 扫描器。
        采用懒加载（而非模块导入时），是为了避免在没有配置 .env 的环境下 import 时就抛错。
        """
        if not cls._initialized:
            mcp_registry.initialize()
            skill_registry.initialize()
            cls._initialized = True

    @staticmethod
    def get_base_tools_schema():
        ToolRegistry._ensure_initialized()
        base = [
            {"name": "run_bash", "description": "Execute a shell command on the host (Subject to HITL intercept).", "is_destructive": True,
             "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
            {"name": "read_file", "description": "Read file contents from the workspace.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "write_file", "description": "Write entire content to a file. Subject to HITL if file exists.", "is_destructive": True,
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
            {"name": "edit_file", "description": "Replace exact text snippet in an existing file.", "is_destructive": True,
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
            {"name": "list_files", "description": "List files in a directory up to depth 2.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
             
            # AST
            {"name": "get_repo_map", "description": "Get an AST syntax skeleton map of up to 20 files in a directory to fast-read code structure.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
             
            # RAG
            {"name": "index_codebase", "description": "Scan and chunk code files into VectorDB instance for semantic search.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
            {"name": "semantic_search_code", "description": "Search the indexed RAG VectorDB for relevant code snippets using natural language.",
             "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "n_results": {"type": "integer"}}, "required": ["query"]}},
             
            # Web
            {"name": "web_search", "description": "Search DuckDuckGo to find information, documentation, or answers on the internet.",
             "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer"}}, "required": ["query"]}},
            {"name": "fetch_url", "description": "Fetch and extract readable text content from any webpage.",
             "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
             
            # Docker
            {"name": "sandbox_bash", "description": "Execute a safe shell command inside a disposable Docker container.",
             "input_schema": {"type": "object", "properties": {"command": {"type": "string"}, "image": {"type": "string"}}, "required": ["command"]}},
             
            # Task Management
            {"name": "task_create", "description": "Create a new task in the team's task list.",
             "input_schema": {"type": "object", "properties": {"subject": {"type": "string"}, "description": {"type": "string"}}, "required": ["subject"]}},
            {"name": "task_update", "description": "Update the status or dependencies of an existing task.",
             "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "blocked"]}, "add_blocked_by": {"type": "array", "items": {"type": "integer"}}}, "required": ["task_id"]}},
            {"name": "task_list", "description": "List all tasks and their current status.",
             "input_schema": {"type": "object", "properties": {}, "required": []}},
             
            # Context
            {"name": "compress", "description": "Manually signal that you have completed a major milestone, forcing the system to wipe and summarize the context window.",
             "input_schema": {"type": "object", "properties": {}, "required": []}},
             
            # Swarm Orchestration
            {"name": "handover_to", "description": "Yield control and pass the workflow to another specialized Agent. Provide the target agent name and instructions for what they should do next.",
             "input_schema": {"type": "object", "properties": {"agent_name": {"type": "string", "enum": ["ProductManager", "Architect", "Coder", "QA_Reviewer", "User"]}, "instructions": {"type": "string"}}, "required": ["agent_name", "instructions"]}}
        ]
        
        # 动态并入 MCP 工具（若未配置 MCP_SERVERS 则返回空列表，无副作用）
        base.extend(mcp_registry.get_mcp_tools_schema())
        
        # 动态并入 Skill 工具（若没有加载任何技能则跳过）
        skill_schema = skill_registry.get_skill_tool_schema()
        if skill_schema:
            base.append(skill_schema)
        
        return base

    @staticmethod
    def get_role_tools(role: str):
        """根据不同的角色下发不同的工具子集，避免 LLM 幻觉和乱用权限"""
        schemas = ToolRegistry.get_base_tools_schema()
        
        # 🛡️ 增强：自动为 MCP 动态工具打上危险标记（如果工具名包含 write/edit/delete/save 等）
        DESTRUCTIVE_KEYWORDS = ["write", "edit", "delete", "remove", "save", "move", "create"]
        for s in schemas:
            if s["name"].startswith("mcp__"):
                # 检查原始工具名（去掉 mcp__server__ 前缀）
                original_name = s["name"].split("__")[-1].lower()
                if any(k in original_name for k in DESTRUCTIVE_KEYWORDS):
                    s["is_destructive"] = True

        role_map = {
            "ProductManager": ["web_search", "fetch_url", "handover_to", "task_create", "task_update", "task_list", "compress", "use_skill"],
            "Architect": ["get_repo_map", "index_codebase", "semantic_search_code", "read_file", "list_files", "handover_to", "task_create", "task_update", "task_list", "compress", "use_skill"],
            "Coder": ["read_file", "write_file", "edit_file", "run_bash", "list_files", "handover_to", "task_update", "task_list", "compress"],
            "QA_Reviewer": ["sandbox_bash", "read_file", "write_file", "run_bash", "handover_to", "task_update", "task_list", "compress", "use_skill"]
        }
        allowed = role_map.get(role)
        if allowed:
            # 授权：角色原有的内置工具 + 所有的 MCP 动态发现工具
            return [s for s in schemas if s["name"] in allowed or s["name"].startswith("mcp__")]
        
        # 兜底：如果是不在列表中的角色，默认可以看到所有工具
        return schemas

    @staticmethod
    def get_base_handlers(todo_manager):
        """传入外界的 TodoList 状态机完成绑定"""
        handlers = {
            "run_bash":             lambda **kw: SystemTools.run_bash(kw["command"]),
            "read_file":            lambda **kw: SystemTools.read_file(kw["path"]),
            "write_file":           lambda **kw: SystemTools.write_file(kw["path"], kw["content"]),
            "edit_file":            lambda **kw: SystemTools.edit_file(kw["path"], kw["old_text"], kw["new_text"]),
            "list_files":           lambda **kw: SystemTools.list_files(kw["path"]),
            "get_repo_map":         lambda **kw: ASTTools.get_repo_map(kw["path"], WORKDIR),
            "index_codebase":       lambda **kw: RAGTools.index_codebase(kw["path"], WORKDIR),
            "semantic_search_code": lambda **kw: RAGTools.semantic_search_code(kw["query"], kw.get("n_results", 5), WORKDIR),
            "web_search":           lambda **kw: WebTools.web_search(kw["query"], kw.get("max_results", 5)),
            "fetch_url":            lambda **kw: WebTools.fetch_url(kw["url"]),
            "sandbox_bash":         lambda **kw: DockerTools.sandbox_bash(kw["command"], kw.get("image", "python:3.11-slim"), WORKDIR),
            "task_create":          lambda **kw: todo_manager.create(kw["subject"], kw.get("description", "")),
            "task_update":          lambda **kw: todo_manager.update(kw["task_id"], status=kw.get("status"), add_blocked_by=kw.get("add_blocked_by")),
            "task_list":            lambda **kw: todo_manager.list_all(),
            "handover_to":          lambda **kw: f"__HANDOVER_SIGNAL__::{kw.get('agent_name', 'User')}::{kw.get('instructions', 'Please follow up.')}"
        }
        
        # 并入 MCP 工具 handlers（若未配置 MCP_SERVERS 则返回空字典）
        handlers.update(mcp_registry.get_mcp_handlers())
        
        # 并入 Skill handler（use_skill工具）
        handlers["use_skill"] = skill_registry.get_skill_handler(handlers)
        
        return handlers
