"""
core/swarm.py - 多智能体图灵拓扑编排引擎 (LangChain 1.0 / LangGraph 重构版)

================================================================================
                                🎯 架构图拓扑设计
================================================================================

      [ 外部系统: MessageBus/CLI ]                   [ 任务状态: TaskManager ]
             |    ▲                                              |
             ▼    |     1. 消息送入 Summarizer                     ▼
        +-------------------------------------------------------------+
        |                 [ StateGraph: Swarm Engine ]                |
        |                                                             |
        |  +--------------------+                                     |
        |  | summarizer (压缩)  | --------+                           |
        |  +--------------------+         | 2. 路由 (根据 active_agent)|
        |           ▲                     |                           |
        |           |                     ▼                           |
        |           |        +-------------------------+              |
        |           |        |    Role Agents (节点)    |              |
        |  5. 压    |        |  - ProductManager       |              |
        |     缩    |        |  - Architect            |              |
        |     下    |        |  - Coder                |              |
        |     文    |        |  - QA_Reviewer          |              |
        |           |        +-------------------------+              |
        |           |                     |                           |
        |           |                     ▼                           |
        |           |        +-------------------------+              |
        |           +------- |  agent_router (路由器)   |              |
        | 4. 修复后          +-------------------------+              |
        |    返回                         | 3. 处理结果                 |
        |                                 |                           |
        |    +----------------+           | (A: Handoff 交接请求)      |
        |    | diagnose_error | <---------+                           |
        |    +----------------+  (B: 检测到工具执行错误)                 |
        |                                                             |
        |                        (C: 处理完毕) -> END                 |
        +-------------------------------------------------------------+

【设计意图与 LangGraph 教学】
本模块使用 langgraph-swarm 实现多智能体的控制权接力编排。
1. `StateGraph`: 相当于一个超级有限状态机 (FSM)，在内存中维护了一个不断更迭的 `SwarmState` 字典。
2. `Nodes (节点)`: 图上的每一个处理站，例如各个角色（PM/Coder）本质上是打包了 System Prompt 和特定 Tools 的 `create_react_agent` (独立智能子图)。
3. `Edges (边 & 路由)`: 决定当前节点执行完毕后，根据最后的输出，图的状态流该导向哪里的规则。
4. `Handoff (移交机制)`: 让当前 Agent 调用带有 `Command(goto=...` 的移交工具，LangGraph 收到 Command 后会中断当前节点，切换路由路径。
5. `HITL (人机环路护栏)`: 某些工具太危险，通过 `interrupt()` 方法注入到工具函数的执行链中，让底层强行抛出中断异常挂起，等待外界输入。
================================================================================
"""

import logging
import asyncio
import copy
from typing import Optional, Dict, TypedDict, Any, Callable

from rich.console import Console
from rich.markdown import Markdown

# LangChain/LangGraph 核心库
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, RemoveMessage, BaseMessage
from langgraph.prebuilt import create_react_agent
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import interrupt, Command
from langgraph_swarm import create_handoff_tool, SwarmState as BaseSwarmState

# 业务模块依赖
from core.llm import get_llm
from utils.paths import DB_PATH
from tools.registry import ToolRegistry, GOVERNANCE
from core.prompts import prompt_manager
from managers.collector import collector


console = Console()
logger = logging.getLogger(__name__)


# ==============================================================================
# 1. 核心状态与类型定义 (State & Types)
# ==============================================================================

class MessageDict(TypedDict):
    """单条消息的字典表示，主要用于跨进程通讯格式化。"""
    role: str
    content: str
    metadata: Optional[Dict[str, Any]]


class SwarmState(BaseSwarmState):
    """
    Swarm图引擎的全局内存 (Global Memory)
    
    【教学提示】：当某个节点返回 `{"error_count": 1}` 时，LangGraph 底层并不是覆盖整个 State，
    而是调用 State 各字段指定的 "Reducer" (合并函数) 进行更新。基础字段常常是覆盖，而 messages 通常是追加。
    """
    summary: Optional[str] = None
    task_id: Optional[int] = None
    last_handoff_message: Optional[str] = None
    error_count: int = 0


class UIState:
    """内部传递 UI 打印状态的跟踪器"""
    def __init__(self, starting_role: str):
        self.final_role = starting_role
        self.streamed_response = False
        self.last_printed_role = None


# ==============================================================================
# 2. 图级别功能节点 (System Nodes)
# ==============================================================================

async def summarize_history(state: SwarmState) -> dict:
    """自动摘要节点 (Summarization Node)"""
    messages = state.get("messages", [])
    summary = state.get("summary", "")

    if len(messages) < 25 and len(str(messages)) < 20000:
        return {}

    logger.info(f"Summarization triggered: {len(messages)} messages.")
    to_summarize = messages[:-3]
    recent_messages = messages[-3:]

    summarize_llm = get_llm(streaming=False)
    summary_history_str = "\n".join([f"{m.type}: {m.content}" for m in to_summarize])
    prompt = (
        f"You are a context manager. Below is a long conversation history.\n"
        f"Existing Summary: {summary or 'None'}\n\n"
        f"NEW CONVERSATION TO ADD:\n{summary_history_str}\n\n"
        f"Please provide a new, updated summary that captures all key decisions, "
        f"task progress, and technical designs. Be concise but thorough."
    )
    
    response = await summarize_llm.ainvoke([HumanMessage(content=prompt)])
    new_summary = response.content

    delete_ops = [RemoveMessage(id=m.id) for m in to_summarize if hasattr(m, 'id')]
    summary_msg = HumanMessage(
        content=f"[SYSTEM NOTIFICATION: CONTEXT SUMMARY]\n{new_summary}\n[END SUMMARY]"
    )

    return {
        "summary": new_summary,
        "messages": delete_ops + [summary_msg] + recent_messages
    }


async def diagnose_error(state: SwarmState) -> dict:
    """自主错误诊断节点 (Error Repair Node)"""
    messages = state.get("messages", [])
    error_count = state.get("error_count", 0)
    
    if error_count > 3:
        return {"messages": [AIMessage(content="Self-healing failed after 3 attempts. Please check manually.")]}
        
    last_tool_msg = next((m for m in reversed(messages) if m.type == "tool"), None)
    if not last_tool_msg:
        return {"error_count": error_count + 1}
        
    error_text = str(last_tool_msg.content)
    logger.warning(f"Self-healing triggered for error: {error_text[:100]}...")

    llm = get_llm(streaming=False)
    repair_prompt = (
        f"The agent encountered an error while executing a tool:\n\n"
        f"ERROR: {error_text}\n\n"
        f"Please analyze this error. If it's a missing dependency, environment issue, or syntax error, "
        f"provide a specific bash command to fix it (e.g., 'pip install ...' or 'mkdir ...').\n"
        f"Only provide the command if you are confident. Otherwise, explain the cause briefly."
    )
    
    response = await llm.ainvoke([HumanMessage(content=repair_prompt)])
    repair_msg = AIMessage(content=f"[SELF-HEALING DIAGNOSIS]\n{response.content}\n[END DIAGNOSIS]")
    
    return {
        "messages": [repair_msg],
        "error_count": error_count + 1
    }


# ==============================================================================
# 3. 编排器主类 (Swarm Orchestrator)
# ==============================================================================

class SwarmOrchestrator:
    """多智能体图灵网络编排中心"""

    def __init__(self, bus_manager, todo_manager, team_manager=None, interrupt_checker=None):
        self.bus = bus_manager
        self.todo = todo_manager
        self.team = team_manager
        self.callback = None
        self.role_names = ["ProductManager", "Architect", "Coder", "QA_Reviewer"]
        self._app_uncompiled = self._build_graph()
        self.latest_messages = []

    # ================= 3.1 实例化与装配相关 ================= #

    def _wrap_sync_tool(self, original_func: Callable, tool_name: str) -> Callable:
        """封装同步危险工具的执行闭包"""
        def sync_wrap(*args, **kwargs):
            resp = interrupt({"tool": tool_name, "args": kwargs or args, "message": f"Agent 请求执行危险操作: {tool_name}"})
            if resp == "deny":
                return f"❌ 操作被用户拒绝: {tool_name}"
            return original_func(*args, **kwargs)
        return sync_wrap

    def _wrap_async_tool(self, original_coro: Callable, tool_name: str) -> Callable:
        """封装异步危险工具的执行闭包"""
        async def async_wrap(*args, **kwargs):
            resp = interrupt({"tool": tool_name, "args": kwargs or args, "message": f"Agent 请求执行危险操作: {tool_name}"})
            if resp == "deny":
                return f"❌ 操作被用户拒绝: {tool_name}"
            return await original_coro(*args, **kwargs)
        return async_wrap

    def _wrap_dangerous_tools(self, role_tools: list) -> list:
        """为设定名单中的危险工具注入 interrupt() 中断检查层"""
        dangerous_list = GOVERNANCE.get("dangerous_tools", ["run_bash", "write_file", "edit_file", "sandbox_bash"])
        wrapped_tools = []
        
        for t in role_tools:
            t_name = getattr(t, 'name', str(t))
            if t_name in dangerous_list:
                wt = copy.copy(t)
                if getattr(wt, 'func', None):
                    wt.func = self._wrap_sync_tool(wt.func, t_name)
                if getattr(wt, 'coroutine', None):
                    wt.coroutine = self._wrap_async_tool(wt.coroutine, t_name)
                wrapped_tools.append(wt)
            else:
                wrapped_tools.append(t)
                
        return wrapped_tools

    def _create_role_agents(self, llm) -> list:
        """生成独立拥有系统提示词和对应工具组的 Agent"""
        agents = []
        for role in self.role_names:
            raw_tools = ToolRegistry.get_role_tools(role, self.todo, self.team)
            for target in [r for r in self.role_names if r != role]:
                raw_tools.append(create_handoff_tool(agent_name=target))
                
            wrapped = self._wrap_dangerous_tools(raw_tools)
            prompt = prompt_manager.get_prompt(role)
            agents.append(create_react_agent(llm, wrapped, prompt=prompt, name=role))
            
        return agents

    # ================= 3.2 路由助手 ================= #

    def _wrap_agent_node(self, agent_runnable):
        """安检门：去除 SystemMessage 以免遭到严格的基础模型 SDK 拦截屏蔽"""
        async def _n(state: SwarmState):
            messages = state.get("messages", [])
            filtered = [m for m in messages if not isinstance(m, SystemMessage)]
            return await agent_runnable.ainvoke({**state, "messages": filtered})
        return _n

    def _route_from_summarizer(self, state: SwarmState) -> str:
        """通用状态返还"""
        return state.get("active_agent", "ProductManager")

    def _check_tool_error(self, last_msg: BaseMessage) -> Optional[str]:
        """检查工具是否遇到错误从而需要诊断"""
        if last_msg.type == "tool":
            content_str = str(last_msg.content)
            is_error = getattr(last_msg, "status", "") == "error"
            if is_error or content_str.startswith("Error:") or content_str.startswith("Exception:"):
                return "diagnoser"
        return None

    def _check_handoff(self, last_msg: BaseMessage) -> Optional[str]:
        """检查是否有意图移交给其他智能体"""
        if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
            if any(tc.get("name", "").startswith("transfer_to_") for tc in last_msg.tool_calls):
                return "summarizer"
        return None

    def _check_text_response(self, last_msg: BaseMessage, messages: list, active_agent: str) -> Optional[str]:
        """检查是否只是文本回复，并防止偷懒空刷"""
        if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
            content_str = str(getattr(last_msg, 'content', '') or '').strip()
            has_tool_history = any(getattr(m, 'type', '') == 'tool' for m in messages[-5:-1])
            
            if has_tool_history and len(content_str) < 50:
                logger.info(f"Post-tool reply too short. Routing back to {active_agent}.")
                return active_agent
            
            if len(content_str) >= 10:
                return END
        return None

    def _route_from_agent(self, state: SwarmState) -> str:
        """主干智能路由：通过串联各个轻量子检查器极大降低圈复杂度"""
        messages = state.get("messages", [])
        if not messages:
            return END
            
        last_msg = messages[-1]
        active = state.get("active_agent", "ProductManager")
        
        return (
            self._check_tool_error(last_msg) or
            self._check_handoff(last_msg) or
            self._check_text_response(last_msg, messages, active) or
            "summarizer"
        )

    def _build_graph(self) -> StateGraph:
        """组合并串联所有的节点和边图逻辑"""
        agents = self._create_role_agents(get_llm(streaming=False))
        builder = StateGraph(SwarmState)

        builder.add_node("summarizer", summarize_history)
        builder.set_entry_point("summarizer")
        builder.add_node("diagnoser", diagnose_error)

        for role, agent in zip(self.role_names, agents):
            builder.add_node(role, self._wrap_agent_node(agent))

        builder.add_conditional_edges("summarizer", self._route_from_summarizer, path_map=self.role_names)
        
        all_destinations = {r: r for r in self.role_names}
        all_destinations.update({"diagnoser": "diagnoser", "summarizer": "summarizer", END: END})
        
        for role in self.role_names:
            builder.add_conditional_edges(role, self._route_from_agent, all_destinations)
        
        builder.add_edge("diagnoser", "summarizer")
        
        return builder

    def get_mermaid_graph(self):
        try:
            return self._app_uncompiled.compile().get_graph().draw_mermaid()
        except Exception as e:
            return f"Error generating graph: {e}"

    def inject_user_message(self, role: str, message: str):
        self.bus.send(sender="User", recipient=role, content=message, msg_type="message")

    # ==============================================================================
    # 4. 执行控制室 (Execution Engine)
    # ==============================================================================

    def _handle_chain_start(self, name: str, ui: UIState):
        """处理内部 Graph 节点激活事件"""
        if name in self.role_names:
            ui.final_role = name
            if name != ui.last_printed_role:
                console.print(f"\n[bold cyan]➔ Active Agent: {name}[/bold cyan]")
                ui.last_printed_role = name
                if self.callback:
                    self.callback("node_start", {"role": name})

    def _handle_chat_stream(self, chunk: Any, ui: UIState):
        """处理模型思考时的打字机文字渲染"""
        if hasattr(chunk, "content") and isinstance(chunk.content, str):
            print(chunk.content, end="", flush=True)
            if len(chunk.content.strip()) > 0:
                ui.streamed_response = True

    def _handle_tool_start(self, name: str, data: dict, ui: UIState):
        """处理新工具被大模型唤醒"""
        if name.startswith("_"): return
        inputs = data.get("input", {})
        input_str = str(inputs)[:150]
        console.print(f"\n  [bold white]> {name}[/bold white]: [dim]{input_str}...[/dim]")
        if self.callback:
            self.callback("tool_use", {"name": name, "input": inputs})
        ui.streamed_response = False

    def _handle_tool_end(self, name: str, data: dict):
        """处理工具结果成功回传"""
        if name.startswith("_"): return
        output = data.get("output", "")
        preview = str(output)[:500]
        if preview:
            console.print(f"  [dim]  ↳ {preview}...[/dim]")
        if self.callback and isinstance(output, str):
            self.callback("tool_result", {"output": str(output)[:800]})

    async def _process_stream_events(self, stream_generator, ui: UIState):
        """通过查表机制替代大量 if-elif 的巨型分支处理器，极大优化圈复杂度"""
        handlers = {
            "on_chain_start": lambda e: self._handle_chain_start(e["name"], ui),
            "on_chat_model_stream": lambda e: self._handle_chat_stream(e["data"]["chunk"], ui),
            "on_tool_start": lambda e: self._handle_tool_start(e["name"], e["data"], ui),
            "on_tool_end": lambda e: self._handle_tool_end(e["name"], e["data"])
        }
        
        async for event in stream_generator:
            handler = handlers.get(event["event"])
            if handler:
                handler(event)

    # ------------------ HITL 人机环路模块 ------------------

    def _get_active_interrupt(self, tasks: list) -> Optional[dict]:
        """搜寻当前挂起待审查的重要异常"""
        for task in tasks:
            for intr in task.interrupts:
                return intr.value
        return None

    async def _prompt_user_approval(self, info: dict) -> str:
        """独立的系统输入阻塞循环提取"""
        console.print(f"\n[bold red]❗ Security Stop: {info.get('message', 'Unknown Action')}[/bold red]")
        console.print(f"  参数: {info.get('args', {})}")
        
        while True:
            choice = await asyncio.to_thread(input, "\033[93mApprove execution? [Y/n]: \033[0m")
            choice = choice.strip().lower()
            
            if choice in ['y', 'yes', '']:
                console.print("[bold green]✅ Approved. Resuming...[/bold green]")
                return "approve"
            if choice in ['n', 'no']:
                console.print("[bold red]❌ Denied. Interaction ended.[/bold red]")
                return "deny"
                
            console.print("[bold yellow]Invalid input. Please enter 'y' to approve or 'n' to deny.[/bold yellow]")

    async def _handle_hitl_approval(self, state: BaseSwarmState) -> tuple[bool, Optional[str]]:
        """安全审批核心逻辑，判断是否被 interrupt 堵截并询问人类"""
        if not state.tasks:
            return False, None
            
        info = self._get_active_interrupt(state.tasks)
        if not info:
            return False, None
            
        resume_value = await self._prompt_user_approval(info)
        return True, resume_value

    # ------------------ 收尾输出渲染 ------------------

    def _extract_final_text(self, msg: AIMessage) -> str:
        """从杂乱的格式中抽取最底层的回复文本"""
        content = msg.content
        if isinstance(content, list):
            text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            content = "\n".join(text_parts)
        return str(content).strip()

    def _render_final_response(self, messages: list, ui: UIState):
        """兜底措施：应对因为打字机事件未被暴露，而错过了大段文本渲染的问题"""
        if ui.streamed_response or not messages:
            return
            
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                text = self._extract_final_text(msg)
                if len(text) > 10:
                    console.print()
                    console.rule(f"[bold magenta]{ui.final_role} Response")
                    console.print(Markdown(text))
                    console.rule()
                    console.print()
                break

    # ------------------ 主系统循环 ------------------

    async def run_swarm_loop(
        self, 
        starting_role: str = "ProductManager", 
        thread_id: str = "swarm_main", 
        callback: Callable = None, 
        user_message: str = None
    ) -> str:
        """▶️ 编排层：驱动这艘智能代理宇宙飞船的最强引力中心"""
        self.callback = callback
        input_msg = {"messages": [HumanMessage(content=user_message)]} if user_message else None
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
        ui = UIState(starting_role)

        try:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
                app = self._app_uncompiled.compile(checkpointer=checkpointer)

                await self._process_stream_events(app.astream_events(input_msg, config=config, version="v2"), ui)
                print()

                state = await app.aget_state(config)
                while state.next:
                    needs_resume, resume_value = await self._handle_hitl_approval(state)
                    if not needs_resume:
                        break
                        
                    await self._process_stream_events(
                        app.astream_events(Command(resume=resume_value), config=config, version="v2"), ui
                    )
                    state = await app.aget_state(config)
                print()

                final_state = await app.aget_state(config)
                if final_state and final_state.values:
                    self.latest_messages = final_state.values.get("messages", [])
                    self._render_final_response(self.latest_messages, ui)
                    
                    if self.latest_messages:
                        try:
                            collector.record_session(session_id=thread_id, messages=self.latest_messages, metadata={"final_role": ui.final_role})
                        except Exception as e:
                            logger.error(f"Failed to record trajectory: {e}")

            if self.callback:
                self.callback("info", f"Workflow complete. Active role: {ui.final_role}")

            return ui.final_role

        except Exception as e:
            logger.error(f"Swarm execution error: {e}")
            if self.callback:
                self.callback("info", f"Swarm error: {e}")
            console.print(f"[bold red]Swarm Error: {e}[/bold red]")
            return starting_role
