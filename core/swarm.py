import logging
import json
import time
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.status import Status
from rich.table import Table
from rich.markdown import Markdown

from core.llm import LLMProvider
from core.context import ContextManager
from tools.registry import ToolRegistry

console = Console()

logger = logging.getLogger(__name__)


def _serialize_content(content):
    """
    将 Anthropic SDK 返回的 content 列表（可能是 ParsedTextBlock / ToolUseBlock 等对象）
    转为可序列化的普通 dict。
    这是为了兼容第三方 OpenAI-compatible API（如 GLM），它们不接受 Python 对象作为请求体。
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
                # 其他类型新尝试通过 model_dump，否则转字符串
                try:
                    serialized.append(block.model_dump())
                except Exception:
                    serialized.append({"type": "text", "text": str(block)})
        else:
            serialized.append({"type": "text", "text": str(block)})
    return serialized

class SwarmOrchestrator:
    """
    多智能体图灵拓扑编排引擎 (Multi-Agent Swarm Orchestrator)
    
    【设计意图】
    Phase 4: 将单体 Lead Agent 拆解为 `ProductManager`, `Architect`, `Coder`, `QA_Reviewer` 四个专业节点。
    引擎负责维护它们的独立上下文（messages array），并通过解析 `handover_to` 工具的特殊信号，
    来进行 CPU 执行权转移，模拟人类团队流水线的审批与协作。
    """
    
    def __init__(self, bus_manager, todo_manager, interrupt_checker=None):
        self.bus = bus_manager
        self.todo = todo_manager
        self.handlers = ToolRegistry.get_base_handlers(self.todo)
        # interrupt_checker 是一个可调用对象，执行就会检查中断标志。main.py 提供。
        self.interrupt_checker = interrupt_checker or (lambda: None)
        
        # 维护每个角色的独立记忆（Session Context）
        self.agent_contexts = {
            "ProductManager": [],
            "Architect": [],
            "Coder": [],
            "QA_Reviewer": []
        }
        
    def _get_system_prompt(self, role: str) -> str:
        """根据角色绑定定制化的人设（Persona）"""
        base = (
            "You are a cutting-edge Autonomous Principal Agent.\n"
            "SYSTEM KNOWLEDGE:\n"
            "- Dynamic Tools: Any tool starting with 'mcp__' is an external capability discovered via Model Context Protocol. Use them when specialized tasks (filesystem, database, etc.) are required.\n"
            "- Multi-Agent: You are part of a swarm. Use 'handover_to' to pass the baton when your specialty is exhausted.\n"
        )
        if role == "ProductManager":
            return base + "ROLE: Product Manager. Clarify ambiguous user requirements, do internet research, and draft a structured Product Requirement Document (PRD). When done, handover_to 'Architect'."
        elif role == "Architect":
            return base + "ROLE: Architect. Read the PRD, scan the codebase topology using AST/RepoMap or 'mcp__filesystem' tools, and output specific architectural blueprints. When done, handover_to 'Coder'."
        elif role == "Coder":
            return base + "ROLE: Coder. Receive architectural plans and implement precise code diffs. Update TodoTasks (task_update) frequently. When done, handover_to 'QA_Reviewer'."
        elif role == "QA_Reviewer":
            return base + "ROLE: QA Reviewer. Review code written by the Coder. Execute them in a sandbox or via bash to run tests. If they fail, handover_to 'Coder' with detailed logs. If all looks good, handover_to 'User'."
        return base

    def inject_user_message(self, role: str, message: str):
        """外部用户向系统注入需求的第一入口"""
        self.agent_contexts[role].append({"role": "user", "content": message})

    def run_swarm_loop(self, starting_role: str):
        """
        Swarm 核心主干循环。
        引擎交出控制权给 current_role，观察它的思考与行动。
        如果它调用了 `handover_to`，截获信号，切换 current_role。
        """
        current_role = starting_role
        
        while True:
            # 在每次切换节点前检查用户是否按了 Ctrl+C
            self.interrupt_checker()

            if current_role == "User":
                # 流程完结，等待人类再次交互
                print("\n\033[92m[Swarm Engine] Final deliverable handed over to User. Awaiting new instructions.\033[0m")
                break
                
            print(f"\n\033[1;34m=== [Swarm Active Node: {current_role}] ===\033[0m")
            messages = self.agent_contexts[current_role]
            tools = ToolRegistry.get_role_tools(current_role)
            sys_prompt = self._get_system_prompt(current_role)
            
            # --- 压缩器与环境感知的注入 ---
            ContextManager.microcompact(messages)
            def _summary_llm(msgs, sys, stream):
                return LLMProvider.safe_llm_call(msgs, sys, tools=None, stream=stream)
            ContextManager.auto_compact(messages, _summary_llm)
            
            # 如果是 Coder 或 Architect，可以给它们看下环境状态
            if current_role in ["Coder", "Architect"] and len(messages) > 0 and messages[-1]["role"] == "user":
                env_info = []
                if self.todo.list_all() != "No tasks.":
                    env_info.append(f"[ENV: CURRENT TASKS]\n{self.todo.list_all()}")
                
                # 为 Architect 注入基础目录结构，减少“盲目”搜索
                from tools.system_tools import SystemTools
                try:
                    tree = SystemTools.list_files(".")
                    env_info.append(f"[ENV: WORKSPACE TREE]\n{tree}")
                except Exception:
                    pass

                if env_info:
                    base_content = messages[-1].get("content", "")
                    if isinstance(base_content, list):
                        base_content = " ".join([b.get("text", "") for b in base_content if b.get("type") == "text"])
                    messages[-1]["content"] = str(base_content) + "\n\n" + "\n\n".join(env_info)
            # -------------------------------
            
            try:
                # LLM 在此扮演当前 Role
                if not True: # 保持语义，方便阅读。实际逻辑：stream=True 时不需要外部 status
                    pass

                # 执行 LLM 调用
                # 如果是流式，safe_llm_call 内部会处理 UI
                if True: # Swarm 默认开启流式，safe_llm_call 内部自持 rule
                    response = LLMProvider.safe_llm_call(messages, sys_prompt, tools=tools, stream=True)
            except Exception as e:
                logger.error(f"Swarm LLM failure: {e}")
                console.print(Panel(f"[bold red]Fatal Error in LLM API:[/bold red]\n{e}", title="CRITICAL ERROR", border_style="red"))
                break

            messages.append({"role": "assistant", "content": _serialize_content(response.content)})
            
            if response.stop_reason == "tool_use":
                results = []
                handover_triggered = False
                next_role = None
                handover_msg = ""
                
                for block in response.content:
                    if block.type == "tool_use":
                        # 获取工具元数据（检查是否是危险操作）
                        tool_meta = next((t for t in tools if t["name"] == block.name), {})
                        is_destructive = tool_meta.get("is_destructive", False)
                        
                        if is_destructive:
                            console.print("\n")
                            console.print(Panel(
                                f"[bold white]Parameters:[/bold white] {json.dumps(block.input, indent=2, ensure_ascii=False)}",
                                title="[bold red]⚠️ SAFETY GUARD: APPROVAL REQUIRED[/bold red]", 
                                subtitle=f"Agent [bold cyan]{current_role}[/bold cyan] -> Tool [bold red]{block.name}[/bold red]",
                                border_style="yellow",
                                padding=(1, 2)
                            ))
                            confirm = console.input("[bold red]Allow this action? (y/n): [/bold red]").strip().lower()
                            if confirm != 'y':
                                output = "User denied the execution of this destructive tool for safety reasons."
                                console.print(f"[bold red]✘ Action Denied by User.[/bold red]")
                                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
                                continue

                        handler = self.handlers.get(block.name)
                        try:
                            output = handler(**block.input) if handler else f"Unknown tool: {block.name}"
                        except Exception as e:
                            output = f"Error: {e}"
                            
                        # 拦截交接信号
                        if isinstance(output, str) and output.startswith("__HANDOVER_SIGNAL__::"):
                            parts = output.split("::")
                            if len(parts) >= 3:
                                next_role = parts[1]
                                handover_msg = parts[2]
                                handover_triggered = True
                                console.print(Panel(
                                    f"[bold white]{handover_msg}[/bold white]",
                                    title=f"[bold green]🤝 Handover: {current_role} ➔ {next_role}[/bold green]",
                                    border_style="green",
                                    padding=(1, 2)
                                ))
                                output = f"Handover triggered for {next_role} successfully."
                        
                        if not handover_triggered:
                            # 更加商务/极客的工具调用展示
                            cmd_display = f"[bold white]{block.name}[/bold white]([dim]{json.dumps(block.input, ensure_ascii=False)}[/dim])"
                            console.print(f"[bold cyan]▶[/bold cyan] {cmd_display}")
                            # 缩进显示结果摘要
                            summary = str(output)[:400].replace("\n", " ") + ("..." if len(str(output)) > 400 else "")
                            console.print(f"  [italic blue]↳ {summary}[/italic blue]")
                            
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
                        
                # 无论是否交接，都要闭环当前 tool 的 response 给目前的 Agent
                messages.append({"role": "user", "content": results})
                
                if handover_triggered and next_role:
                    # 将交接信息写入 Inbox，并强行注入目标 Agent 的上下文
                    self.bus.send(sender=current_role, recipient=next_role, content=handover_msg, msg_type="handover")
                    
                    if next_role in self.agent_contexts:
                        handover_text = (
                            f"[SYSTEM: HANDOVER FROM {current_role}]\n"
                            f"{current_role} has yielded control to you. Here are their instructions:\n"
                            f"{handover_msg}\n"
                            f"Please take over and continue the workflow."
                        )
                        self.agent_contexts[next_role].append({"role": "user", "content": handover_text})
                    
                    # 轮转指针！！！
                    current_role = next_role
            else:
                # Agent 自己思考完并没有调用 handover，停顿了。
                # 在典型的多智能体 Swarm 中，如果不交接，说明它需要等用户反馈。
                print(f"\n\033[95m[{current_role}] Yielding back to user without explicit handover.\033[0m")
                break
                
        return current_role # 返回最后掌权的 Agent
