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
from typing import Optional
from dotenv import load_dotenv

from langchain_anthropic import ChatAnthropic
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel

from utils.paths import get_env_path
from managers.database import record_token_usage

logger = logging.getLogger(__name__)

# --- 载入环境变量 ---
env_path = get_env_path()
if env_path:
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Cloud 配置 (Anthropic)
API_KEY = os.getenv("ANTHROPIC_API_KEY")
BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
MODEL_ID = os.getenv("MODEL_ID", "claude-3-5-sonnet-20241022")

# Local 配置 (vLLM / Ollama / LoRA)
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
LOCAL_BASE_URL = os.getenv("LOCAL_BASE_URL", "http://localhost:8000/v1")
LOCAL_MODEL_ID = os.getenv("LOCAL_MODEL_ID", "qwen-7b-lora")
LORA_ADAPTER_PATH = os.getenv("LORA_ADAPTER_PATH", "")

if not USE_LOCAL_LLM and not API_KEY:
    print("\033[91mError: ANTHROPIC_API_KEY is not set. To use local models, set USE_LOCAL_LLM=true.\033[0m")


class TokenCounterCallback(BaseCallbackHandler):
    """
    Token 用量追踪回调 (Token Counter Callback)
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


def get_llm(streaming: bool = False) -> BaseChatModel:
    """
    获取标准化的 LLM 实例 (支持云端与本地)

    【设计意图】
    1. 默认使用 Anthropic 云端模型以保证稳定性。
    2. 若开启 USE_LOCAL_LLM，则通过 ChatOpenAI 接口连接本地服务 (vLLM 或 Ollama)。
    3. 本地模式支持通过 LORA_ADAPTER_PATH 指定微调后的模型。
    """
    if USE_LOCAL_LLM:
        if ChatOpenAI is None:
            raise ImportError("USE_LOCAL_LLM is true but 'langchain-openai' is not installed. Please run 'pip install langchain-openai'.")
        # 使用本地兼容 OpenAI 的后端 (vLLM / Ollama)
        logger.info(f"Using Local LLM at {LOCAL_BASE_URL} with model {LOCAL_MODEL_ID}")
        return ChatOpenAI(
            model=LOCAL_MODEL_ID,
            openai_api_key="local-placeholder",
            openai_api_base=LOCAL_BASE_URL,
            max_tokens=8192,
            streaming=streaming,
            callbacks=[token_counter],
        )

    # 默认路径：Anthropic Cloud
    if not API_KEY:
        raise RuntimeError("API client not initialized. Check your ANTHROPIC_API_KEY.")

    kwargs = {
        "model": MODEL_ID,
        "api_key": API_KEY,
        "max_tokens": 8192,
        "streaming": streaming,
        "callbacks": [token_counter],
    }

    if BASE_URL and BASE_URL != "https://api.anthropic.com":
        kwargs["base_url"] = BASE_URL

    return ChatAnthropic(**kwargs)


# 预构建的全局实例
llm = get_llm(streaming=False)
llm_streaming = get_llm(streaming=True)
