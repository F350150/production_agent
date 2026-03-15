"""
core/llm.py - LLM 交互核心模块 (LangChain 1.0 重构版)

功能：
- 基于 langchain-anthropic 的 ChatAnthropic 标准化接入
- Token 统计与成本追踪（通过 LangChain Callback 自动化）
- LangSmith 追踪内置（无需手动装饰器）
- 保留流式输出的 Rich 终端渲染
"""

import os
import logging
from typing import Optional, List
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from utils.paths import get_env_path
from managers.database import record_token_usage

logger = logging.getLogger(__name__)

# --- 载入环境变量 ---
env_path = get_env_path()
if env_path:
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

API_KEY = os.getenv("ANTHROPIC_API_KEY")
BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
MODEL_ID = os.getenv("MODEL_ID", "claude-sonnet-4-20250514")

if not API_KEY:
    print("\033[91mError: ANTHROPIC_API_KEY is not set in environment or .env file.\033[0m")


class TokenCounterCallback(BaseCallbackHandler):
    """
    Token 用量追踪回调 (Token Counter Callback)

    【设计意图】
    LangChain 1.0 通过 Callback 机制在 LLM 响应完成后自动获取 Token 消耗信息。
    我们将每一次调用的 Input/Output Token 持久化到 SQLite 的 metrics 表中，
    与原来手写的 record_token_usage 保持完全兼容。
    """
    def on_llm_end(self, response, **kwargs):
        """LLM 调用结束时记录 Token 用量"""
        try:
            if response and response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
                if input_tokens or output_tokens:
                    record_token_usage(input_tokens, output_tokens)
        except Exception as e:
            logger.debug(f"Token counter callback error: {e}")


# --- 全局 LLM 实例 ---
token_counter = TokenCounterCallback()


def get_llm(streaming: bool = False) -> ChatAnthropic:
    """
    获取标准化的 ChatAnthropic 实例

    【设计意图】
    统一的 LLM 工厂函数。所有组件（Agent、Swarm、Subagent）都通过此函数获取 LLM，
    确保配置一致性。LangSmith 追踪在 LangChain 1.0 中是自动开启的（只要设置了环境变量），
    无需手动添加 @traceable 装饰器。

    参数：
    - streaming: 是否启用流式输出
    """
    if not API_KEY:
        raise RuntimeError("API client not initialized. Check your ANTHROPIC_API_KEY.")

    kwargs = {
        "model": MODEL_ID,
        "api_key": API_KEY,
        "max_tokens": 8192,
        "streaming": streaming,
        "callbacks": [token_counter],
    }

    # 兼容第三方中转网关
    if BASE_URL and BASE_URL != "https://api.anthropic.com":
        kwargs["base_url"] = BASE_URL

    return ChatAnthropic(**kwargs)


# 预构建的全局实例（供快速访问）
# 非流式版本（用于后台 Agent、Subagent、压缩等）
llm = get_llm(streaming=False)
# 流式版本（用于终端交互的实时打字机效果）
llm_streaming = get_llm(streaming=True)
