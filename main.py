import logging
import signal
import sys
import os
from pathlib import Path
import asyncio

# 确保当前目录在 sys.path 中，使得跨目录运行 python main.py 也能通过顶级包名导入
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import readline  # noqa: F401 — 仅 import 即可让 input() 自动获得方向键历史功能 (macOS/Linux)
import rlcompleter  # noqa: F401 — Tab 补全支持
from utils.paths import LOG_FILE, HISTORY_FILE
from managers.database import get_db_conn, save_session, load_session, clear_session, print_cost_report, close_db
from core import BUS, TODO
from core.swarm import SwarmOrchestrator, console
from core.llm import TokenCounterCallback, MODEL_ID
from tools.mcp_registry import mcp_registry
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# 生产环境标准的日志追踪：除了 Console 外，还往文件里写
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
    ]
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# readline 历史文件：在进程间持久化命令历史
# ─────────────────────────────────────────────────────────
try:
    if os.path.exists(HISTORY_FILE):
        readline.read_history_file(str(HISTORY_FILE))
    readline.set_history_length(500)  # 最多记住 500 条
except (FileNotFoundError, PermissionError):
    pass
except Exception as e:
    print(f"\033[90m[Warning: Failed to load history: {e}]\033[0m")

# ─────────────────────────────────────────────────────────
# Tab 补全支持 (Completion)
# ─────────────────────────────────────────────────────────
CLI_COMMANDS = ["/clear", "/cost", "/history", "exit", "quit", "q"]

def command_completer(text, state):
    """简单的 readline 补全逻辑"""
    options = [i for i in CLI_COMMANDS if i.startswith(text)]
    if state < len(options):
        return options[state]
    else:
        return None

readline.set_completer(command_completer)
if "libedit" in readline.__doc__:
    readline.parse_and_bind("bind ^I rl_complete")
else:
    readline.parse_and_bind("tab: complete")

# ─────────────────────────────────────────────────────────
# 中断标志：用于区分 "Ctrl+C 中止当前 Agent 循环" 与 "彻底退出程序"
# ─────────────────────────────────────────────────────────
_interrupt_requested = False

def _signal_handler(sig, frame):
    """
    【Ctrl+C 软中断机制】
    第一次按 Ctrl+C：仅设置中断标志，等待当前 Agent 轮次安全收尾，不中断整个程序。
    再次按 Ctrl+C：如果标志已被设置还没被清（即 Agent 正在长时间运行），则强制退出。
    """
    global _interrupt_requested
    if _interrupt_requested:
        # 连续两次 Ctrl+C => 真的想退出
        print("\n\033[91m[Double Ctrl+C detected. Force quitting...]\033[0m")
        raise KeyboardInterrupt
    _interrupt_requested = True
    print("\n\033[93m[Ctrl+C received] Agent will pause after current step. Press Ctrl+C again to force quit.\033[0m")

# 注册为 SIGINT 处理器，替换默认的 "直接抛出 KeyboardInterrupt" 行为
signal.signal(signal.SIGINT, _signal_handler)


def _check_interrupt():
    """在 Swarm 每个节点之间检查是否被用户软中断"""
    global _interrupt_requested
    if _interrupt_requested:
        _interrupt_requested = False
        raise InterruptedError("User interrupted the swarm loop.")


def cleanup(swarm=None):
    """
    统一的资源清理与持久化函数。
    确保在程序退出（无论是通过 q、Ctrl+D 还是异常）时，MCP 进程和数据库都能安全关闭。
    """
    print("\n[bold blue]Finalizing resources...[/bold blue]")
    try:
        # 2. 持久化交互历史
        readline.write_history_file(str(HISTORY_FILE))
        print("\033[90m[History saved]\033[0m")
        
        # 3. 关闭所有 MCP 后台进程
        mcp_registry.shutdown()
        print("\033[90m[MCP servers shutdown completed]\033[0m")
        
        # 4. 关闭数据库连接
        close_db()
        print("\033[90m[Database connection closed]\033[0m")
    except Exception as e:
        print(f"\033[91m[Cleanup error: {e}]\033[0m")

async def main():
    """
    终端互动入口 (REPL: Read-Eval-Print-Loop)
    
    【使用指南】
    - 直接打字给 Agent 下达指令（支持上/下键调出历史命令）
    - 输入 /cost 查询消费与账单
    - 输入 /clear 清理默认历史以节约 Token
    - 输入 /history 查看当前 REPL 输入历史
    - 输入 q 或 exit 退出，状态与上下文将持久化通过 SQLite 保留
    - 执行中按 Ctrl+C：中止当前 Agent 轮次并返回 REPL 提示符
    - 再按一次 Ctrl+C：强制退出
    """
    welcome_txt = Text.assemble(
        (" Production Autonomous Software Engineer Agent ", "bold white on blue"),
        (f"\n [LangChain 1.0 + LangGraph Swarm | {MODEL_ID}] ", "cyan italic")
    )
    console.print(Panel(welcome_txt, border_style="blue", expand=False))

    cmd_table = Table(show_header=False, box=None)
    cmd_table.add_row("[bold magenta]/clear[/bold magenta]", "Clear the current session history.")
    cmd_table.add_row("[bold magenta]/cost[/bold magenta]", "View LLM token usage and estimated cost.")
    cmd_table.add_row("[bold magenta]/history[/bold magenta]", "Show your recent input history.")
    cmd_table.add_row("[bold red]q / exit[/bold red]", "Quit and gracefully save session state.")
    cmd_table.add_row("[bold yellow]Ctrl+C[/bold yellow]", "Interrupt agent mid-run.")
    
    console.print(Panel(cmd_table, title="[bold white]Available Commands[/bold white]", border_style="cyan", expand=False))

    swarm = None

    try:
        while True:
            global _interrupt_requested
            _interrupt_requested = False  # 每次回到 REPL 提示符都清除中断标志

            try:
                query = input("\n\033[92mLead Agent >> \033[0m")
                if not query.strip():
                    continue

                if query.strip().lower() in ['exit', 'quit', 'q']:
                    break

                # 懒加载：仅在用户第一次输入时初始化 Swarm 引擎
                if swarm is None:
                    with console.status("[bold blue]Firing up Swarm Engine & Discovering Tools...", spinner="earth"):
                        # 提前触发工具发现，让用户看到连接过程
                        from tools.registry import ToolRegistry
                        ToolRegistry._ensure_initialized()

                        # 初始化 TEAM 管理器（用于后台子 Agent）
                        from core import TEAM as team_manager

                        swarm = SwarmOrchestrator(BUS, TODO, team_manager=team_manager, interrupt_checker=_check_interrupt)
                        # 每个新 session 使用唯一的 thread_id，确保 checkpoint 互不干扰
                        import uuid
                        session_thread_id = f"swarm_{uuid.uuid4().hex[:8]}"

                if query.strip() == "/clear":
                    clear_session("swarm_modular")
                    from core import TEAM as team_manager
                    swarm = SwarmOrchestrator(BUS, TODO, team_manager=team_manager, interrupt_checker=_check_interrupt)
                    import uuid
                    session_thread_id = f"swarm_{uuid.uuid4().hex[:8]}"
                    print("\033[33m[Session successfully cleared. Starting fresh.]\033[0m")
                    continue

                if query.strip() == "/cost":
                    print_cost_report()
                    continue

                if query.strip() == "/history":
                    # 打印最近 20 条命令历史
                    length = readline.get_current_history_length()
                    start = max(1, length - 19)
                    hist_table = Table(title="📜 Recent Command History", show_header=False)
                    for i in range(start, length + 1):
                        hist_table.add_row(f"{i}", readline.get_history_item(i))
                    console.print(hist_table)
                    continue

                # 拦截：查询是否有后台子节点 (Subagent) 刚做完任务发来的信件
                inbox_msgs = BUS.read_inbox("User")
                if inbox_msgs:
                    reports = "\n\n".join([f"--- 📬 BACKGROUND AGENT REPORT FROM {m['from']} ---\n{m['content']}" for m in inbox_msgs])
                    query = f"{reports}\n\n--- USER INSTRUCTION ---\n{query}"
                    console.print(f"\n[bold cyan]📬 Fetched {len(inbox_msgs)} subagent report(s) from MessageBus and injected into context.[/bold cyan]")

                try:
                    # 开始由引擎接管，执行并发异步循环。
                    final_role = await swarm.run_swarm_loop("ProductManager", thread_id=session_thread_id, user_message=query)

                    # 不再依赖 agent_contexts，直接信任终端流式输出
                    console.print(f"\n[dim][{final_role}] Yielding back to user.[/dim]")
                except (InterruptedError, KeyboardInterrupt):
                    # 无论是自定义拦截还是直接 Ctrl+C，都在这里安全着陆并返回提示符
                    console.print("\n[bold yellow]⚠ Interaction interrupted. Returning to prompt...[/bold yellow]")

            except KeyboardInterrupt:
                # 捕获在 input() 状态下的 Ctrl+C
                print("\n[Use 'q' or 'exit' to quit]")
                continue
            except EOFError:
                print("\nEOF detected.")
                break
            except Exception as e:
                logger.error(f"Uncaught REPL exception: {e}")
                import traceback
                traceback.print_exc()
                break
    finally:
        cleanup(swarm)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
