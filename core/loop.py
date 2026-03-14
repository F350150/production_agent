import json
import logging
import traceback
from rich.console import Console
from rich.panel import Panel
from rich.status import Status
from rich.markdown import Markdown

from core.llm import LLMProvider
from core.context import ContextManager
from tools.registry import ToolRegistry
from managers.tasks import TaskManager
from managers.messages import MessageBus
from managers.team import TeammateManager
from managers.background import BackgroundManager

console = Console()

logger = logging.getLogger(__name__)

# 全局单例实例化 (依赖注入中心)
TODO = TaskManager()
BUS = MessageBus()
TEAM = TeammateManager(BUS, TODO)
BG = BackgroundManager()

# 构建工具集描述 (不再在模块级别进行，改为动态获取以支持懒加载)
def get_loop_tools():
    """获取主循环专用的工具集（含 task 委派）"""
    tools = ToolRegistry.get_base_tools_schema()
    # 追加仅属于主循环调度的特殊反射工具
    tools.append({
        "name": "task", 
        "description": "Delegate a complex sub-task to a background worker agent (Teammate).",
        "input_schema": {"type": "object", "properties": {"prompt": {"type": "string"}, "agent_type": {"type": "string"}}, "required": ["prompt"]}
    })
    return tools

def get_loop_handlers(todo_manager):
    """获取主循环专用的执行函数映射"""
    handlers = ToolRegistry.get_base_handlers(todo_manager)
    # 绑定特殊的子节点唤起函数
    handlers["task"] = lambda **kw: run_subagent(kw["prompt"], kw.get("agent_type", "Explore"))
    handlers["compress"] = lambda **kw: "Context compressed by Lead Agent."
    return handlers

def run_subagent(prompt: str, agent_type: str = "Explore") -> str:
    """
    【并行协作架构】
    生成一个没有权限访问打字机流、且聚焦于完成特定子任务的短期或中期 Sub-Agent。
    """
    logger.info(f"Subagent '{agent_type}' started with prompt: {prompt[:30]}")
    sub_messages = [
        {"role": "user", "content": f"You are a Sub-Agent of type '{agent_type}'. Your task is:\n{prompt}\n\nExecute tools as needed. When finished summarizing findings, stop."}
    ]
    
    # 动态获取工具
    tools = get_loop_tools()
    handlers = get_loop_handlers(TODO)

    # 子 Agent 同理具备断路器防死循环
    rounds = 0
    while rounds < 15:
        ContextManager.microcompact(sub_messages)
        try:
            # stream=False 保持后台静默
            with console.status(f"[bold blue]Subagent ({agent_type}) is working...", spinner="point"):
                sub_resp = LLMProvider.safe_llm_call(
                    sub_messages,
                    "You are an isolated SubAgent. Reply concisely with factual findings only.",
                    tools=tools,
                    stream=False
                )
        except Exception as e:
            return f"Subagent failed to call LLM: {e}"
            
        sub_messages.append({"role": "assistant", "content": sub_resp.content})
        
        if sub_resp.stop_reason == "tool_use":
            for block in sub_resp.content:
                if block.type == "tool_use":
                    handler = handlers.get(block.name)
                    # 虽然也允许子 Agent 再唤起子孙 Agent (递归)，但要极其小心
                    if block.name == "task":
                        out = run_subagent(block.input["prompt"], block.input.get("agent_type", "Sub-Sub"))
                    else:
                        try:
                            # 传入参数并执行
                            out = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                        except Exception as e:
                            out = f"Error: {e}"
                            
                    sub_messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": block.id, "content": str(out)}]})
        else:
            # 停止原因不是工具调用，代表生成完毕
            final_text = "".join([b.text for b in sub_resp.content if b.type == "text"])
            return f"{agent_type} Agent Completed:\n{final_text}"
        rounds += 1
        
    return "Subagent stopped (Hit 15 iteration limit)."

def agent_loop(messages: list):
    """
    全自动推理执行循环 (ReAct Engine Loop)
    """
    rounds_without_todo = 0
    consecutive_errors = 0
    
    # 动态获取工具
    tools = get_loop_tools()
    handlers = get_loop_handlers(TODO)
    
    while True:
        # 上下文整理：清理无用 token 和连续的 user 发言
        ContextManager.microcompact(messages)
        
        # 强制上下文折叠逻辑：防止聊天轮次太长爆破额度
        # 我们传入用于总结的 LLM 回调函数
        def _summary_llm(msgs, sys, stream):
            return LLMProvider.safe_llm_call(msgs, sys, tools=None, stream=stream)
        ContextManager.auto_compact(messages, _summary_llm)

        # ====== 环境状态透视区 ======
        if messages[-1]["role"] == "user":
            base_content = messages[-1].get("content", "")
            if isinstance(base_content, list):
                base_content = " ".join([b.get("text", "") for b in base_content if b.get("type") == "text"])
                
            injected_env = ""
            # 投喂未尽事宜
            if TODO.list_all() != "No tasks.":
                injected_env += f"\n[ENV: CURRENT TASKS]\n{TODO.list_all()}\n"
            # 投喂收割到的后台任务输出
            bg_res = BG.drain()
            if bg_res:
                injected_env += f"\n[ENV: BACKGROUND RESULTS]\n{bg_res}\n"
                
            if injected_env:
                messages[-1]["content"] = str(base_content) + injected_env
        # ==========================

        system_prompt = (
            "You are a cutting-edge Autonomous Principal Software Engineer Agent (Lead)."
            "You have tools. DO NOT hallucinate. Formulate multi-step plans if needed, update TODO list, use tools, and finally reply to the user.\n"
            "For heavy code reading use get_repo_map and index_codebase -> semantic_search_code.\n"
            "For unknown library errors use web_search.\n"
            "For experimental dependencies use sandbox_bash."
        )

        try:
            # 生产环境特色：流式体验
            # 如果是流式，safe_llm_call 内部会处理 UI (rule + typing)
            response = LLMProvider.safe_llm_call(messages, system_prompt, tools=tools, stream=True)
        except Exception as e:
            logger.error(f"Core loop LLM failure: {e}")
            logger.error(traceback.format_exc())
            console.print(Panel(f"[bold red]Fatal Error in LLM API:[/bold red]\n{e}", title="LEAD AGENT ERROR", border_style="red"))
            break

        # 将生成的这一轮对话送入记忆
        from core.swarm import _serialize_content
        messages.append({"role": "assistant", "content": _serialize_content(response.content)})

        if response.stop_reason == "tool_use":
            results = []
            used_todo = False
            manual_compress = False
            had_tool_error = False
            
            for block in response.content:
                if block.type == "tool_use":
                    if block.name == "compress":
                        manual_compress = True
                        
                    # HITL 安全查杀
                    tool_meta = next((t for t in tools if t["name"] == block.name), {})
                    if tool_meta.get("is_destructive"):
                        console.print(Panel(
                            f"[bold yellow]HITL INTERCEPT:[/bold yellow] Lead Agent wants to use [bold red]{block.name}[/bold red]\n"
                            f"[bold white]Input:[/bold white] {json.dumps(block.input, indent=2, ensure_ascii=False)}",
                            title="SAFETY CHECK", border_style="yellow"
                        ))
                        if console.input("[bold red]Allow? (y/n): [/bold red]").strip().lower() != 'y':
                            output = "Execution denied by user."
                            console.print("[bold red]X Denied.[/bold red]")
                            results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
                            continue

                    handler = TOOL_HANDLERS.get(block.name)
                    try:
                        output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                        # 监测到工具执行报 Error
                        if str(output).startswith("Error:"):
                            had_tool_error = True
                    except Exception as e:
                        output = f"Error: {e}"
                        had_tool_error = True
                        
                    # 给用户视觉反馈，它调用了什么工具
                    console.print(f"[bold cyan]>[/bold cyan] [bold white]{block.name}[/bold white]: [dim]{str(output)[:200]}...[/dim]")
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
                    if block.name == "TodoWrite":
                        used_todo = True
                        
            # --------- 熔断器 (Circuit Breaker) ---------
            # 场景：大模型自己没意识到在原地打转，不断重试一个错误的工具长达半小时
            if had_tool_error:
                consecutive_errors += 1
                if consecutive_errors >= 4:
                    print(f"\n\033[91m[Circuit Breaker] Agent generated {consecutive_errors} consecutive tool errors.\033[0m")
                    print("\033[93mThis might be an infinite loop. Continuing will consume more API tokens.\033[0m")
                    choice = input("\033[91mContinue execution? [y/N]: \033[0m").strip().lower()
                    if choice != 'y':
                        print("Agent suspended. Session Context will be saved upon exit.")
                        return # 强行跳出主循环，挂起 Agent
                    # 人类特许通行，清空累积计数
                    consecutive_errors = 0
            else:
                consecutive_errors = 0
            # ---------------------------------------------
            
            # --- 主动指导与纠偏 (Nagging Mechanism) ---
            rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
            if TODO.list_all() != "No tasks." and rounds_without_todo >= 3:
                results.append({"type": "text", "text": "SYSTEM NAG: You have open tasks but haven't updated them recently. Please review tasks and update status!"})
                rounds_without_todo = 0
                
            messages.append({"role": "user", "content": results})
            
            if manual_compress:
                print("\n\033[94m[Agent triggered manual memory compression. Forgetting deep context past this milestone.]\033[0m")
                ContextManager.perform_full_compression(messages, TODO.list_all())
                
        else:
            # 推理和行动阶段均已结束，等待下一次人类的指令
            break
