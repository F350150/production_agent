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
import json
from typing import Optional, Callable
from rich.console import Console

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from core.llm import get_llm
from utils.paths import DB_PATH
import aiosqlite
from tools.registry import ToolRegistry, create_task_tools

console = Console()
logger = logging.getLogger(__name__)


# ==============================================================================
# 角色 System Prompt 定义（原样迁移自旧版 swarm.py）
# ==============================================================================

BASE_PROMPT = (
    "You are a cutting-edge Autonomous Principal Agent operating in a multi-agent swarm.\n\n"
    "=== SYSTEM KNOWLEDGE ===\n"
    "- Dynamic Tools: Any tool starting with 'mcp__' is an external capability discovered via Model Context Protocol.\n"
    "- Multi-Agent: You are part of a swarm. Use handoff tools to pass the baton when your specialty is exhausted.\n"
    "- Context Isolation: Each agent has their own conversation history. Handover summaries are preserved.\n"
    "- Task Tracking: Always maintain tasks using task_create, task_update, task_list tools.\n"
)

ROLE_PROMPTS = {
    "ProductManager": BASE_PROMPT + """
=== ROLE: Product Manager ===

【核心职责】
你负责需求澄清、产品规划和工作流协调。你代表用户与系统之间的第一道沟通桥梁。
你是智能路由器——根据用户需求的复杂度，选择最高效的处理路径。

【快速路由规则 — 必须严格遵守】
收到用户消息后，立即判断复杂度：

🟢 简单操作型请求（如：列出目录、读文件、运行命令、查看代码）：
   → 不要废话，不要解释你的局限性，不要创建任务列表
   → 直接调用 transfer_to_coder，简要说明用户要做什么

🔵 信息检索型请求（如：查新闻、搜 API 文档、研究背景）：
   → 直接使用 web_search 或 fetch_url 工具完成
   → 整理好输出直接回给用户或移交给相关同事

🟡 中等复杂请求（如：修改某个现有功能、修复 bug、添加简单特性）：
   → 简要分析需求 → 直接 transfer_to_coder，附带清晰指令

🔴 复杂产品级需求（如：设计新系统、重构架构、多模块联动开发）：
   → 完整 PRD 流程 → 任务拆解 → transfer_to_architect

【决策流程（仅针对 🔴 级别）】
1. 需求分析：理解用户的模糊需求，必要时通过 web_search 研究背景信息
2. 需求澄清：如果需求不明确，主动向用户提出问题
3. 任务拆解：将大需求拆解为可执行的任务列表（使用 task_create）
4. PRD 起草：输出结构化的产品需求文档

【移交时机】
- 🟢🟡 级别：立即 transfer_to_coder
- 🔴 级别：PRD 完成后 transfer_to_architect

【★ 最重要的一条规则 ★】
永远不要向用户说"我没有这个工具"或"我无法直接操作"。
你有队友！立即 handoff 给能做这件事的队友。用户不关心内部分工细节。
""",

    "Architect": BASE_PROMPT + """
=== ROLE: Architect ===

【核心职责】
你负责系统架构设计、技术选型和实现路径规划。你从 PRD 出发，产出可落地的技术方案。

【决策流程】
1. 需求理解：仔细阅读 ProductManager 提供的 PRD
2. 现状扫描：使用 get_repo_map 了解现有代码结构
3. 依赖分析：通过 index_codebase 和 semantic_search_code 找到相关模块
4. 方案设计：制定详细的架构方案

【审批机制】
完成架构方案后，使用 transfer_to_productmanager 提交审批。
获批后，使用 transfer_to_coder 移交。

【注意事项】
- 保持方案的可实施性，避免过度设计
- 考虑现有代码的扩展性
""",

    "Coder": BASE_PROMPT + """
=== ROLE: Coder ===

【核心职责】
你负责代码实现、调试和修改。你严格按照 Architect 提供的方案编写高质量代码。

【决策流程】
1. 方案理解：阅读 Architect 提供的架构方案
2. 代码实现：使用 read_file, edit_file, write_file, run_bash
3. 进度更新：频繁使用 task_update 更新任务状态

【移交时机】
当所有任务完成且代码可运行时，使用 transfer_to_qa_reviewer 移交。

【注意事项】
- 不要偏离 Architect 的设计方案
- 实现遇到困难时，使用 transfer_to_architect 寻求指导
""",

    "QA_Reviewer": BASE_PROMPT + """
=== ROLE: QA Reviewer ===

【核心职责】
你负责代码审查、功能测试和质量保证。你是系统上线前的最后一道防线。
现在你还配备了实时信息检索能力。

【决策流程】
1. 需求背景：如果你不了解当前的系统、环境或最新的外部背景（如新闻、文档、API版本），请先使用 web_search 或 fetch_url 进行研究。
2. 代码审查：使用 read_file 查看修改的代码
3. 功能测试：使用 run_bash 或 sandbox_bash 执行测试
4. 质量评估：检查性能、安全性、代码风格
5. 解决问题：如果遇到环境问题（如 400 错误、库缺失），尝试使用搜索寻找解决方案。不要仅仅报告失败。

【移交机制】
- 通过测试：直接向用户回复交付清单（不再移交）
- 测试失败：使用 transfer_to_coder 附上详细问题报告
""",
}


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

        # 兼容旧版：保留 agent_contexts 用于 session 持久化
        self.agent_contexts = {}
        self.current_role = "ProductManager"

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

            # 创建角色 Agent
            agent = create_react_agent(
                llm,
                role_tools,
                prompt=ROLE_PROMPTS.get(role, BASE_PROMPT),
                name=role,
            )
            agents.append(agent)

        # 创建 Swarm 编排图, 这里的 "interrupt_before" 就是人类在环(HITL)审批的关键参数
        # 当流转到 QA_Reviewer 时自动挂起，等待用户 approval。
        return create_swarm(agents, default_active_agent="ProductManager")

    def inject_user_message(self, role: str, message: str):
        """
        外部用户向系统注入需求的第一入口

        【兼容旧版 API】
        保持与 main.py 和 streamlit_app.py 的接口一致
        """
        self.current_role = role
        # agent_contexts 用于 session 持久化的兼容
        if role not in self.agent_contexts:
            self.agent_contexts[role] = []
        self.agent_contexts[role].append({"role": "user", "content": message})

    async def run_swarm_loop(self, starting_role: str = "ProductManager", callback: Callable = None):
        """
        执行 Swarm 编排循环 (异步版本)

        【设计意图】
        使用 LangGraph 的 astream 模式运行 Swarm。
        自动处理角色切换、工具并发调用和状态持久化。

        返回最终的活跃角色名。
        """
        self.callback = callback

        # 获取最近一条用户消息
        user_messages = self.agent_contexts.get(starting_role, [])
        if not user_messages:
            return starting_role

        last_user_msg = user_messages[-1]
        if isinstance(last_user_msg, dict):
            content = last_user_msg.get("content", "")
        else:
            content = str(last_user_msg)

        # 构建 LangGraph 输入
        input_msg = {"messages": [HumanMessage(content=content)]}
        config = {
            "configurable": {"thread_id": "swarm_main"},
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
                                
                    # LLM 生成工具调用意图
                    elif kind == "on_tool_start" and not name.startswith("_"):
                        inputs = event["data"].get("input", {})
                        # LangGraph 有时内部事件不带清晰的 inputs，尽力提取
                        input_str = str(inputs)[:150]
                        console.print(f"\n  [bold white]> {name}[/bold white]: [dim]{input_str}...[/dim]")
                        if callback:
                            callback("tool_use", {"name": name, "input": inputs})

                    # 工具执行结束返回结果
                    elif kind == "on_tool_end" and not name.startswith("_"):
                        output = event["data"].get("output", "")
                        result_preview = str(output)[:200]
                        if result_preview:
                            console.print(f"  [dim]  ↳ {result_preview}...[/dim]")
                        if callback and isinstance(output, str):
                            callback("tool_result", {"output": str(output)[:300]})

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
                        DANGEROUS_TOOLS = ["run_bash", "write_file", "edit_file", "sandbox_bash"]
                        for tc in last_msg.tool_calls:
                            t_name = tc.get("name", "")
                            tool_names.append(t_name)
                            if t_name in DANGEROUS_TOOLS:
                                is_dangerous = True
                    
                    if is_dangerous:
                        console.print(f"\n[bold red]❗ Security Stop: Agent is attempting dangerous operation: {', '.join(tool_names)}[/bold red]")
                        choice = input("\033[93mApprove execution? [Y/n]: \033[0m").strip().lower()
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
                        elif kind == "on_tool_start" and not name.startswith("_"):
                            inputs = event["data"].get("input", {})
                            console.print(f"\n  [bold white]> {name}[/bold white]: [dim]{str(inputs)[:150]}...[/dim]")
                        elif kind == "on_tool_end" and not name.startswith("_"):
                            output = event["data"].get("output", "")
                            result_preview = str(output)[:200]
                            if result_preview:
                                console.print(f"  [dim]  ↳ {result_preview}...[/dim]")

                    # 再次获取最新状态以查看是否还有挂起的下一步
                    state = await app.aget_state(config)
                
                print()

                # 获取最终状态并更新 agent_contexts
                final_state = await app.aget_state(config)
                if final_state and final_state.values:
                    final_messages = final_state.values.get("messages", [])
                    # 提取最终的 AI 响应用于兼容旧版 session 持久化
                    for msg in reversed(final_messages):
                        if isinstance(msg, AIMessage) and msg.content:
                            if final_role not in self.agent_contexts:
                                self.agent_contexts[final_role] = []
                            self.agent_contexts[final_role].append({
                                "role": "assistant",
                                "content": msg.content
                            })
                            break

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


# ==============================================================================
# 兼容层：保留旧版 _serialize_content 供其他模块使用
# ==============================================================================

def _serialize_content(content):
    """
    将消息内容序列化为普通 dict（兼容层）

    【设计意图】
    在 LangChain 1.0 中，消息对象自带序列化能力。
    但为了兼容尚未完全迁移的模块，保留此函数。
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    serialized = []
    for block in content:
        if isinstance(block, dict):
            serialized.append(block)
        elif hasattr(block, "type"):
            if block.type == "text":
                serialized.append({"type": "text", "text": getattr(block, "text", "")})
            elif block.type == "tool_use":
                serialized.append({
                    "type": "tool_use",
                    "id": getattr(block, "id", ""),
                    "name": getattr(block, "name", ""),
                    "input": getattr(block, "input", {})
                })
            elif block.type == "tool_result":
                serialized.append({
                    "type": "tool_result",
                    "tool_use_id": getattr(block, "tool_use_id", ""),
                    "content": getattr(block, "content", "")
                })
            else:
                try:
                    serialized.append(block.model_dump())
                except Exception:
                    serialized.append({"type": "text", "text": str(block)})
        else:
            serialized.append({"type": "text", "text": str(block)})
    return serialized
