import logging
import asyncio
from typing import List, Optional, Dict, Any, TypedDict, Literal
from managers.database import get_db_conn, DB_LOCK, record_token_usage
from utils.paths import DB_PATH
from utils.converters import serialize_message_content
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


# ==============================================================================
# 类型定义 (Types)
# ==============================================================================

class TeammateInfo(TypedDict):
    """队友信息字典"""
    name: str
    role: str
    status: Literal["idle", "working", "error"]
    last_task: Optional[str]

# ==============================================================================
# 工具函数 (Utilities)
# ==============================================================================

class TeammateManager:
    """
    后台团队成员管理器 (TeammateManager) Async Edition

    【设计意图】
    Lead Agent 面临复杂问题时可能会分身乏术。
    通过这个类，主管可以"招募"多个打工 Agent 在独立的 asyncio Task 中并行 work。
    这个管理器主要负责维护这些后台打工机器人的生命周期和当前状态字典。

    【增强功能】
    - 真正的后台 Agent 执行：每个 teammate 在 asyncio.Task 中运行
    - 独立的上下文和工具集
    - 通过 MessageBus 与主 Agent 通信
    - 基于 LangGraph create_react_agent 的稳健执行
    """
    def __init__(self, bus, task_mgr):
        from managers.messages import MessageBus
        from managers.tasks import TaskManager
        self.bus = bus
        self.task_mgr = task_mgr
        # 活跃的 Agent Task (asyncio.Task)
        self.active_tasks = {}
        # Agent 上下文存储（每个队友有自己的对话历史）
        self.agent_contexts = {}

    def _set_status(self, name: str, status: str):
        """原子级状态更新：防止状态幻读"""
        with DB_LOCK:
            get_db_conn().execute("UPDATE teammates SET status = ? WHERE name = ?", (status, name))
            get_db_conn().commit()

    def _get_system_prompt_for_role(self, role: str) -> str:
        """为后台子 Agent 生成系统提示词"""
        base = "You are a background sub-agent specialist. Work efficiently and report findings concisely.\n"

        role_prompts = {
            "Explore": base + "ROLE: Explorer. Your job is to search and gather information from the codebase, documentation, or web. Focus on finding specific answers to questions.",
            "Research": base + "ROLE: Researcher. Your job is to conduct in-depth research on technical topics, find best practices, and gather information from various sources.",
            "Test": base + "ROLE: Tester. Your job is to run tests, verify functionality, and report bugs or issues found.",
            "CodeReview": base + "ROLE: Code Reviewer. Your job is to review code for quality, security, best practices, and potential improvements.",
            "Document": base + "ROLE: Documenter. Your job is to generate documentation, comments, and explanations for code and systems."
        }

        return role_prompts.get(role, base + f"ROLE: {role}. Execute your assigned task efficiently.")

    async def _run_teammate_agent(self, name: str, role: str, prompt: str, max_rounds: int = 15):
        """
        【后台 Agent 执行核心】基于 LangGraph 的子图执行模式
        """
        from core.llm import get_llm
        
        try:
            # 1. 初始化工具与模型
            tools = self._get_tools_for_role(role)
            sys_prompt = self._get_system_prompt_for_role(role)
            llm = get_llm(streaming=False)
            
            # 2. 创建 React Sub-Graph
            agent = create_react_agent(llm, tools, prompt=sys_prompt)
            
            # 3. 使用全局 SQLite Checkpointer 进行持久化
            async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
                config = {
                    "configurable": {"thread_id": f"teammate_{name}"},
                    "recursion_limit": max_rounds
                }
                
                # 执行任务
                logger.info(f"Teammate {name} ({role}) executing in LangGraph...")
                input_msg = {"messages": [HumanMessage(content=prompt)]}
                
                # ainvoke 会自动处理 checkpointing
                state = await agent.ainvoke(input_msg, config=config)
                
                # 4. 提取结果
                final_messages = state.get("messages", [])
                final_text = "No output."
                if final_messages:
                    last_msg = final_messages[-1]
                    if hasattr(last_msg, "content"):
                        final_text = str(last_msg.content)

                # 5. 反馈回消息总线
                self.bus.send(
                    sender=name,
                    recipient="User",
                    content=f"### [Teammate Report: {name}]\n{final_text}",
                    msg_type="message",
                    metadata={"role": role}
                )
                
                self.agent_contexts[name] = final_messages
                logger.info(f"Teammate {name} task finalized and persisted.")

        except Exception as e:
            logger.error(f"Teammate {name} execution failed: {e}")
            self.bus.send(
                sender=name,
                recipient="User",
                content=f"### [Teammate FAILED: {name}]\nError: {e}",
                msg_type="error"
            )

        finally:
            # 清理：更新状态并移除 Task 引用
            self._set_status(name, "idle")
            if name in self.active_tasks:
                del self.active_tasks[name]

    def _get_tools_for_role(self, role: str) -> list:
        """为不同角色分配不同的工具集"""
        from tools.registry import ToolRegistry

        base_tools = ToolRegistry.get_base_tools_schema()

        # 根据角色限制可用工具
        role_tool_map = {
            "Explore": ["read_file", "list_files", "get_repo_map", "index_codebase", "semantic_search_code"],
            "Research": ["web_search", "fetch_url", "read_file"],
            "Test": ["run_bash", "sandbox_bash", "read_file"],
            "CodeReview": ["read_file", "get_repo_map"],
            "Document": ["read_file", "list_files", "write_file"]
        }

        allowed = role_tool_map.get(role, [])
        # 允许所有 MCP 工具
        return [t for t in base_tools if t["name"] in allowed or t["name"].startswith("mcp__")]

    def spawn(self, name: str, role: str, prompt: str) -> str:
        """
        唤起一个新的后台常驻打工节点。
        现在会在独立 asyncio.Task 中真正执行 Agent。
        """
        with DB_LOCK:
            row = get_db_conn().execute("SELECT * FROM teammates WHERE name = ?", (name,)).fetchone()
            if row:
                return f"Teammate {name} already exists."
            get_db_conn().execute(
                "INSERT INTO teammates (name, role, status) VALUES (?, ?, ?)",
                (name, role, "starting")
            )
            get_db_conn().commit()

        # 创建并启动后台 Task
        task = asyncio.create_task(
            self._run_teammate_agent(name, role, prompt),
            name=f"Teammate-{name}"
        )

        self.active_tasks[name] = task

        self._set_status(name, "working")

        logger.info(f"Teammate {name} ({role}) spawned and running in background thread")
        return f"Teammate {name} ({role}) spawned and working in background."

    def stop(self, name: str) -> str:
        """
        停止指定的后台 Agent
        """
        if name not in self.active_tasks:
            return f"Teammate {name} is not active."

        # 取消 asyncio 任务
        self.active_tasks[name].cancel()
        self._set_status(name, "stopped")
        del self.active_tasks[name]
        return f"Teammate {name} has been cancelled."

    def get_status(self, name: str) -> str:
        """获取特定 Agent 的状态"""
        with DB_LOCK:
            row = get_db_conn().execute("SELECT status FROM teammates WHERE name = ?", (name,)).fetchone()
        if not row:
            return f"Teammate {name} not found."

        is_running = name in self.active_tasks and not self.active_tasks[name].done()
        return f"Teammate {name}: {row['status']} (running: {is_running})"

    def list_all(self) -> str:
        """获取整个团队的工位快照表"""
        with DB_LOCK:
            rows = get_db_conn().execute("SELECT * FROM teammates").fetchall()
        if not rows: return "No teammates."
        lines = [f"Team: default"]
        for m in rows:
            is_running = m["name"] in self.active_tasks and not self.active_tasks[m["name"]].done()
            status_icon = "▶" if is_running else "⏸"
            lines.append(f"  {status_icon} {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list:
        with DB_LOCK:
            rows = get_db_conn().execute("SELECT name FROM teammates").fetchall()
        return [m["name"] for m in rows]
