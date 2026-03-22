"""
core/swarm.py - 多智能体图灵拓扑编排引擎 (LangChain 1.0 / LangGraph 重构版)

【设计意图】
使用 langgraph-swarm 的 create_handoff_tool + create_swarm 替代原来手写的 808 行 Swarm 引擎。
四角色（PM -> Architect -> Coder -> QA）的流转逻辑和 System Prompt 完全保留。

核心变化：
- handover_to 工具 → langgraph-swarm 内置的 create_handoff_tool
- 手动 while True 循环 → LangGraph StateGraph 自动调度
- 上下文序列化 → LangGraph checkpointer 自动持久化
"""

import logging
import asyncio
from typing import Optional, List, Dict, TypedDict, Any, Literal, Callable
from rich.console import Console

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage, RemoveMessage
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm, SwarmState as BaseSwarmState
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, RemoveMessage
from langgraph.graph import START, StateGraph
from core.llm import get_llm
from utils.paths import DB_PATH
from utils.converters import serialize_message_content
import aiosqlite
from tools.registry import ToolRegistry, create_task_tools, GOVERNANCE
from core.prompts import prompt_manager
from managers.collector import collector

console = Console()
logger = logging.getLogger(__name__)


# ==============================================================================
# 状态与类型定义 (State & Types)
# ==============================================================================

class MessageDict(TypedDict):
    """单条消息的字典表示"""
    role: str
    content: str
    metadata: Optional[Dict[str, Any]]

class SwarmState(BaseSwarmState):
    """
    扩展状态：增加总结字段和错误计数。
    """
    summary: Optional[str] = None
    task_id: Optional[int] = None
    last_handoff_message: Optional[str] = None
    error_count: int = 0  # 记录连续错误次数，防止死循环


async def summarize_history(state: SwarmState):
    """
    自动摘要节点 (Summarization Node)
    """
    messages = state.get("messages", [])
    summary = state.get("summary", "")

    # 阈值判断：消息数 > 25 或 总字符数 > 20,000
    if len(messages) < 25 and len(str(messages)) < 20000:
        return {}

    logger.info(f"Summarization triggered: {len(messages)} messages.")
    
    # 1. 提取需要总结的部分（保留最后的 3 条互动）
    to_summarize = messages[:-3]
    recent_messages = messages[-3:]

    # 2. 调用 LLM 生成摘要
    summarize_llm = get_llm(streaming=False)
    
    # 构建总结提示词
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

    # 3. 构造消息列表压缩指令
    # 使用 RemoveMessage 删除旧消息
    delete_ops = [RemoveMessage(id=m.id) for m in to_summarize if hasattr(m, 'id')]
    
    # 使用 HumanMessage 包装摘要，防止某些模型报错 "multiple non-consecutive system messages"
    summary_msg = HumanMessage(
        content=f"[SYSTEM NOTIFICATION: CONTEXT SUMMARY]\n{new_summary}\n[END SUMMARY]"
    )

    # 返回更新：这里 messages 的 reducer (add_messages) 会处理 RemoveMessage
    # 额外处理：确保消息列表中只有一个 SystemMessage (最前面的保留，后面的删除)
    final_messages = delete_ops + [summary_msg] + recent_messages

    # 遍历新消息(合并与删除的真相)：它开始循环检查你提交的right（新消息）。
    # 情况A（ID已存在）：如果新消息的ID在历史记录里找到了。
    #     如果是RemoveMessage：把它加入ids_to_remove黑名单，准备删除。
    #     如果是普通消息：直接替换 / 更新旧消息（这就是修改已有消息的原理）。
    # 情况B（ID不存在）：说明这是一条全新的消息。
    #     如果是RemoveMessage：报错ValueError（试图删除一条不存在的消息）。
    #     如果是普通消息：追加(Append)到列表末尾。
    
    return {
        "summary": new_summary,
        "messages": final_messages
    }


async def diagnose_error(state: SwarmState):
    """
    自主错误修复节点 (Error Repair Node)
    
    【核心逻辑】
    当检测到工具执行报错（如 stderr, ModuleNotFoundError）时触发。
    利用 LLM 分析错误原因并建议补救措施。
    """
    messages = state.get("messages", [])
    error_count = state.get("error_count", 0)
    # 终极杀手锏：熔断机制 (Circuit Breaker)
    # 如果连续报错超过 3 次，放弃治疗。
    if error_count > 3:
        # 强行塞入一条 AI 文本消息，伪装成任务完成，骗过调度员让整个图走向 END，防止 API 费用被抽干
        return {"messages": [AIMessage(content="Self-healing failed after 3 attempts. Please check manually.")]}
        
    # 提取错误上下文
    last_tool_msg = next((m for m in reversed(messages) if m.type == "tool"), None)
    if not last_tool_msg:
        # 大模型在胡言乱语（没调工具却报了错），没法修。直接给胡闹计数器加 1。
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
    
    repair_msg = AIMessage(
        content=f"[SELF-HEALING DIAGNOSIS]\n{response.content}\n[END DIAGNOSIS]"
    )
    
    return {
        "messages": [repair_msg],
        "error_count": error_count + 1
    }


# System Prompts are now managed in core/prompts.py via PromptManager


# ==============================================================================
# Swarm 编排器（基于 LangGraph）
# ==============================================================================

class SwarmOrchestrator:
    """
    多智能体图灵拓扑编排引擎 (LangGraph Swarm 版本)

    【设计意图】
    使用 langgraph-swarm 实现角色控制权自动流转。
    每个角色是一个独立的 ReAct Agent，通过 handoff_tool 实现 "接力棒" 传递。
    LangGraph 的 StateGraph 自动处理状态管理和循环控制。
    """

    def __init__(self, bus_manager, todo_manager, team_manager=None, interrupt_checker=None):
        self.bus = bus_manager
        self.todo = todo_manager
        self.team = team_manager
        self.interrupt_checker = interrupt_checker or (lambda: None)
        self.callback = None
        self.sqlite_conn = None

        # 构建 Swarm 应用 (未编译，在 run 阶段绑定 checkpointer)
        self._app_uncompiled = self._build_swarm()

        self.current_role = "ProductManager"
        self.latest_messages = []

    def _build_swarm(self):
        """
        构建四角色 Swarm 拓扑

        【设计意图】
        每个角色拥有：
        1. 自己的 System Prompt（定义职责边界）
        2. 按权限过滤的工具集
        3. 到其他角色的 handoff 工具（实现控制权转移）
        """
        llm = get_llm(streaming=False)

        # 为每个角色创建 handoff 工具
        agents = []
        role_names = ["ProductManager", "Architect", "Coder", "QA_Reviewer"]

        for role in role_names:
            # 获取角色专属工具
            role_tools = ToolRegistry.get_role_tools(role, self.todo, self.team)

            # 添加 handoff 工具（可以移交到其他角色）
            handoff_targets = [r for r in role_names if r != role]
            for target in handoff_targets:
                role_tools.append(
                    create_handoff_tool(agent_name=target)
                )

            # 获取角色动态提示词
            prompt = prompt_manager.get_prompt(role)

            # 创建角色 Agent
            agent = create_react_agent(
                llm,
                role_tools,
                prompt=prompt,
                name=role,
            )
            agents.append(agent)

        # --- 手动构建图 (使用扩展的 SwarmState) ---
        builder = StateGraph(SwarmState)

        # 核心增强：所有的入口都先经过 summarizer 减少token使用
        builder.add_node("summarizer", summarize_history)
        builder.set_entry_point("summarizer")

        # 3. 添加角色节点 (带消息清理包装)
        def agent_node_wrapper(agent_runnable):
            async def _n(state: SwarmState):
                # 关键修复：Anthropic 不允许非连续或多个系统消息
                # 我们移除历史中所有的 SystemMessage。
                # 由于 create_react_agent 内部会重新注入其初始 prompt (通常为 SystemMessage)，
                # 这样就保证了消息序列中始终只有一个、且是最新的 SystemMessage。
                messages = state.get("messages", [])
                filtered_messages = [m for m in messages if not isinstance(m, SystemMessage)]
                
                # 额外保护：如果 messages 为空（理论不应），赋予一个初始消息
                if not filtered_messages and "active_agent" in state:
                    # 避免空列表进入 React Agent
                    pass 

                return await agent_runnable.ainvoke({**state, "messages": filtered_messages})
            return _n

        for role, agent in zip(role_names, agents):
            builder.add_node(role, agent_node_wrapper(agent))

        # 4. 添加错误诊断节点
        builder.add_node("diagnoser", diagnose_error)
        
        # 5. 定义路由逻辑
        
        # --- 路由 1: 汇总节点后的路由 ---
        def summarizer_router(state: SwarmState) -> str:
            return state.get("active_agent", "ProductManager")
        
        builder.add_conditional_edges("summarizer", summarizer_router, path_map=role_names)

        # --- 路由 2: Agent 节点后的路由 (核心：自愈、移交与结束控制) ---
        from langgraph.graph import END
        def agent_router(state: SwarmState):
            messages = state.get("messages", [])
            active_agent = state.get("active_agent", "ProductManager")
            if not messages:
                return END
            
            last_msg = messages[-1]
            
            # 1. 检测工具执行错误 -> 进入诊断自愈
            if last_msg.type == "tool":
                is_error_status = getattr(last_msg, "status", "") == "error"
                content_str = str(last_msg.content)
                if is_error_status or content_str.startswith("Error:") or content_str.startswith("Exception:"):
                    return "diagnoser"
            # =====================================================================
            # 2. 检测角色移交 (Handoff)
            # 【架构意图】：拦截 Agent 发出的跨角色移交指令。
            # 中断当前 Agent 的内部执行循环，将状态流转至 summarizer 进行上下文压缩和重新路由。
            # =====================================================================
            if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
                # 【核心拦截逻辑】：阻止 React Agent 内部自动执行该移交工具。
                # 强制中断当前控制流，将下一目标节点显式指定为 "summarizer" (汇总节点)。
                #
                # 架构考量：
                # 1. 上下文控制：交由 summarizer 压缩前置 Agent 的对话历史，避免后续接收节点的 Token 超限。
                # 2. 集中调度：压缩完成后，将由 summarizer_router 读取状态中更新的 active_agent 字段，实现向目标 Agent 的重新分发。
                if any(tc.get("name", "").startswith("transfer_to_") for tc in last_msg.tool_calls):
                    return "summarizer"
                # 【注】：若未匹配到移交指令（即调用的是普通业务工具），则跳过此拦截。
                # LangGraph 底层封装的 React Agent 将按默认逻辑接管并执行该工具，
                # 并在其内部循环直到生成最终回复，无需在此层路由干预。
            
            # 3. 如果是普通文本回复 -> 检查是否真的有有效内容才结束
            # 关键修复：防止 agent 刚完成工具调用（如 web_search）后，
            # 生成空或很短的 AIMessage 就被误判为"最终答复"
            if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
                content = last_msg.content if hasattr(last_msg, 'content') else ""
                content_str = str(content).strip() if content else ""
                
                # 检查最近消息中是否有 tool_result（说明刚执行完工具）
                has_preceding_tool_result = any(
                    getattr(m, 'type', '') == 'tool' 
                    for m in messages[-5:-1]
                )
                
                # 关键修复：如果刚执行完工具但 AI 回复太短（< 50 字），
                # 路由回 active_agent 强制它重新处理工具结果并生成完整总结。
                # 之前路由到 summarizer 只会压缩上下文，不会让 agent 生成新回复。
                if has_preceding_tool_result and (not content_str or len(content_str) < 50):
                    logger.info(f"Post-tool reply too short ({len(content_str)} chars). Routing back to {active_agent} for analysis.")
                    return active_agent
                
                if content_str and len(content_str) >= 10:
                    return END
            
            # 默认兜底：回 summarizer 检查
            return "summarizer"

        # path_map 必须包含所有可能的路由目标（包括各角色名，用于 post-tool 回路由）
        all_destinations = {r: r for r in role_names}
        all_destinations.update({"diagnoser": "diagnoser", "summarizer": "summarizer", END: END})
        
        for role in role_names:
            builder.add_conditional_edges(
                role, 
                agent_router, 
                all_destinations
            )
        
        # 诊断完成后回主流程
        builder.add_edge("diagnoser", "summarizer")
        
        return builder

    def get_mermaid_graph(self):
        """
        导出当前的 Mermaid 拓扑图，用于 UI 可视化
        """
        try:
            # 编译一个临时 application 来生成图
            app = self._app_uncompiled.compile()
            return app.get_graph().draw_mermaid()
        except Exception as e:
            return f"Error generating graph: {e}"

    def inject_user_message(self, role: str, message: str):
        """
        向 Swarm 注入用户指令
        """
        # 1. 发送到 inbox (持久化)
        self.bus.send(
            sender="User",
            recipient=role,
            content=message,
            msg_type="message"
        )

    async def run_swarm_loop(self, starting_role: str = "ProductManager", thread_id: str = "swarm_main", callback: Callable = None, user_message: str = None):
        """
        执行 Swarm 编排循环 (异步版本)

        【设计意图】
        使用 LangGraph 的 astream 模式运行 Swarm。
        自动处理角色切换、工具并发调用和状态持久化。

        返回最终的活跃角色名。
        """
        self.callback = callback

        # 构建 LangGraph 输入
        input_msg = None
        if user_message:
            input_msg = {"messages": [HumanMessage(content=user_message)]}

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 50,  # 替代原来的熔断器
        }

        try:
            # 动态绑定 Async Checkpointer
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            async with AsyncSqliteSaver.from_conn_string(str(DB_PATH)) as checkpointer:
                # 编译图并进入流处理, 设置拦截点 (HITL) 到所有角色之后
                # 这样当 AI 想要调用工具时，我们可以捕获到状态进行审核
                role_names = ["ProductManager", "Architect", "Coder", "QA_Reviewer"]
                app = self._app_uncompiled.compile(
                    checkpointer=checkpointer,
                    interrupt_after=role_names
                )
                
                final_role = starting_role
                current_tool_call = None
                _streamed_response = False  # 追踪是否有实质性文本被流式输出

                # astream_events 支持追踪 LangChain 底层的 Token 流
                async for event in app.astream_events(input_msg, config=config, version="v2"):
                    kind = event["event"]
                    name = event["name"]

                    # 追踪节点/角色切换
                    if kind == "on_chain_start" and name in ["ProductManager", "Architect", "Coder", "QA_Reviewer"]:
                        final_role = name
                        console.print(f"\n[bold cyan]➔ Active Agent: {name}[/bold cyan]")
                        if callback:
                            callback("node_start", {"role": name})

                    # 追踪 Token 流式输出 (真实打字机效果)
                    elif kind == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        if hasattr(chunk, "content") and chunk.content:
                            # 仅处理字符串内容
                            if isinstance(chunk.content, str):
                                # 使用基础 print 实现不换行打字机效果
                                print(chunk.content, end="", flush=True)
                                if len(chunk.content.strip()) > 0:
                                    _streamed_response = True
                                
                    # LLM 生成工具调用意图
                    elif kind == "on_tool_start" and not name.startswith("_"):
                        inputs = event["data"].get("input", {})
                        # LangGraph 有时内部事件不带清晰的 inputs，尽力提取
                        input_str = str(inputs)[:150]
                        console.print(f"\n  [bold white]> {name}[/bold white]: [dim]{input_str}...[/dim]")
                        if callback:
                            callback("tool_use", {"name": name, "input": inputs})
                        # 工具开始后，重置流式标记（下一轮回复需要重新追踪）
                        _streamed_response = False

                    # 工具执行结束返回结果
                    elif kind == "on_tool_end" and not name.startswith("_"):
                        output = event["data"].get("output", "")
                        result_preview = str(output)[:500]
                        if result_preview:
                            console.print(f"  [dim]  ↳ {result_preview}...[/dim]")
                        if callback and isinstance(output, str):
                            callback("tool_result", {"output": str(output)[:800]})

                # 换行收尾
                print()

                # ==== 处理中断 (Human-in-the-Loop) - 精准工具拦截逻辑 ====
                state = await app.aget_state(config)
                while state.next:
                    # 获取中断产生的节点（通常是刚刚执行完的角色）
                    # 在 interrupt_after 下，state.next 是下一个要执行的节点
                    
                    # 检查最后一条消息是否有危险工具调用
                    last_msg = state.values.get("messages", [])[-1] if state.values.get("messages") else None
                    is_dangerous = False
                    tool_names = []
                    
                    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                        # 从治理配置读取危险工具列表
                        dangerous_list = GOVERNANCE.get("dangerous_tools", ["run_bash", "write_file", "edit_file", "sandbox_bash"])
                        for tc in last_msg.tool_calls:
                            t_name = tc.get("name", "")
                            tool_names.append(t_name)
                            if t_name in dangerous_list:
                                is_dangerous = True
                    
                    if is_dangerous:
                        console.print(f"\n[bold red]❗ Security Stop: Agent is attempting dangerous operation: {', '.join(tool_names)}[/bold red]")
                        choice = await asyncio.to_thread(input, "\033[93mApprove execution? [Y/n]: \033[0m")
                        choice = choice.strip().lower()
                        if choice == 'n':
                            console.print("[bold red]❌ Denied. Interaction ended.[/bold red]")
                            break
                        console.print(f"[bold green]✅ Approved. Resuming...[/bold green]")
                    
                    # 恢复图执行。如果是通过 Command 恢复，使用 None 标识直接进入 state.next 执行
                    resume_input = None
                    async for event in app.astream_events(resume_input, config=config, version="v2"):
                        kind = event["event"]
                        name = event["name"]

                        if kind == "on_chain_start" and name in ["ProductManager", "Architect", "Coder", "QA_Reviewer"]:
                            final_role = name
                            console.print(f"\n[bold cyan]➔ Active Agent: {name}[/bold cyan]")
                            if callback:
                                callback("node_start", {"role": name})
                        elif kind == "on_chat_model_stream":
                            chunk = event["data"]["chunk"]
                            if hasattr(chunk, "content") and isinstance(chunk.content, str):
                                print(chunk.content, end="", flush=True)
                                if len(chunk.content.strip()) > 0:
                                    _streamed_response = True
                        elif kind == "on_tool_start" and not name.startswith("_"):
                            inputs = event["data"].get("input", {})
                            console.print(f"\n  [bold white]> {name}[/bold white]: [dim]{str(inputs)[:150]}...[/dim]")
                            _streamed_response = False
                        elif kind == "on_tool_end" and not name.startswith("_"):
                            output = event["data"].get("output", "")
                            result_preview = str(output)[:200]
                            if result_preview:
                                console.print(f"  [dim]  ↳ {result_preview}...[/dim]")

                    # 再次获取最新状态以查看是否还有挂起的下一步
                    state = await app.aget_state(config)
                
                print()

                # 获取最终状态
                final_state = await app.aget_state(config)
                if final_state and final_state.values:
                    final_messages = final_state.values.get("messages", [])
                    self.latest_messages = final_messages

                    # ====== 关键修复：兜底显示最终 AI 回复 ======
                    # 如果流式输出未捕获到实质性文本（常见于 interrupt_after 导致的中断边界、
                    # 或 create_react_agent 子图内部事件不被外层 astream_events 暴露的情况），
                    # 我们从 final_state 提取最后一条 AIMessage 并手动渲染。
                    if not _streamed_response and final_messages:
                        from rich.markdown import Markdown
                        for msg in reversed(final_messages):
                            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                                content = msg.content
                                if isinstance(content, list):
                                    text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
                                    content = "\n".join(text_parts)
                                content = str(content).strip()
                                if content and len(content) > 10:
                                    console.print()
                                    console.rule(f"[bold magenta]{final_role} Response")
                                    console.print(Markdown(content))
                                    console.rule()
                                    console.print()
                                break
                    
                    # Record trajectory for LoRA fine-tuning
                    if final_messages:
                        try:
                            collector.record_session(
                                session_id=thread_id,
                                messages=final_messages,
                                metadata={"final_role": final_role}
                            )
                        except Exception as e:
                            logger.error(f"Failed to record trajectory: {e}")

            self.current_role = final_role
            if callback:
                callback("info", f"Workflow complete. Active role: {final_role}")

            return final_role

        except Exception as e:
            logger.error(f"Swarm execution error: {e}")
            if callback:
                callback("info", f"Swarm error: {e}")
            console.print(f"[bold red]Swarm Error: {e}[/bold red]")
            return starting_role

