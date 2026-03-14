import os
import time
import logging
import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv
from utils.paths import get_env_path
from managers.database import record_token_usage

logger = logging.getLogger(__name__)

# --- 载入环境变量 ---
env_path = get_env_path()
if env_path:
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv() # 尝试默认位置
API_KEY = os.getenv("ANTHROPIC_API_KEY")
BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
MODEL_ID = os.getenv("MODEL_ID", "claude-3-5-sonnet-20241022")

# 如果没有配置 key，提示用户
if not API_KEY:
    print("\033[91mError: ANTHROPIC_API_KEY is not set in environment or .env file.\033[0m")
    
client = Anthropic(api_key=API_KEY, base_url=BASE_URL) if API_KEY else None

class LLMProvider:
    """
    大语言模型通信驱动层 (LLM Provider)
    
    【设计意图】
    生产环境中直接调用 API 是不可靠的（网络波动、触碰速率限制等）。
    此处封装了带指数退避的重试机制（Exponential Backoff Retry），
    同时无缝集成了 `stream=True` 的终端打字机效果，并且在数据回包时自动将消费记录（Token Usage）
    挂载入全局 SQLite 中。
    """
    
    @staticmethod
    def safe_llm_call(messages: list, system_prompt: str, tools: list = None, stream: bool = False, max_retries: int = 3):
        """带有退避重试和打字机流式输出的统一调用入口"""
        if not client:
            raise RuntimeError("API client not initialized. Check your ANTHROPIC_API_KEY.")
            
        kwargs = {
            "model": MODEL_ID,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        for attempt in range(max_retries):
            try:
                if stream:
                    from rich.console import Console
                    from rich.markdown import Markdown
                    from rich.live import Live
                    from rich.padding import Padding
                    rich_console = Console()
                    
                    # 打印装饰线
                    rich_console.print()
                    rich_console.rule("[bold magenta]Agent Reasoning / Thought")
                    
                    full_text = ""
                    # 使用 Live 来平稳展现 Markdown，防止频繁重绘导致的 ANSI 爆炸
                    with Live("", console=rich_console, refresh_per_second=8, vertical_overflow="visible") as live:
                        with client.messages.stream(**kwargs) as stream_ctx:
                            for text in stream_ctx.text_stream:
                                full_text += text
                                # 实时展现 Markdown 效果 (比原生的 print 更稳健且美观)
                                live.update(Markdown(full_text))
                    
                    rich_console.rule() 
                    rich_console.print()
                    
                    final_msg = stream_ctx.get_final_message()
                    if hasattr(final_msg, "usage"):
                        record_token_usage(final_msg.usage.input_tokens, final_msg.usage.output_tokens)
                    return final_msg
                else:
                    # 后台子系统/Teammates 默认静默通信
                    resp = client.messages.create(**kwargs)
                    if hasattr(resp, "usage"):
                        record_token_usage(resp.usage.input_tokens, resp.usage.output_tokens)
                    return resp
                    
            except (anthropic.APIError, anthropic.RateLimitError) as e:
                # 触发限流或网络错误，指数退避
                if attempt == max_retries - 1:
                    logger.error(f"LLM API failed after {max_retries} attempts. Error: {e}")
                    raise
                wait = 2 ** attempt
                logger.warning(f"API Error ({e}), retrying in {wait}s...")
                time.sleep(wait)
