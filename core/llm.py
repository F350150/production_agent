"""
core/llm.py - LLM 交互核心模块 (LangChain 1.0 重构版)

功能：
- 基于 langchain-anthropic 的 ChatAnthropic 标准化接入
- 基于 langchain-openai 的通用 OpenAI 协议大模型接入（支持 Qwen / DeepSeek）
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

# --- 总控策略配置 ---
# 通过 LLM_PROVIDER 来控制使用哪家大模型。默认 anthropic，可改为 openai。
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()

# 1. Cloud 配置 (Anthropic专属)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
ANTHROPIC_MODEL_ID = os.getenv("MODEL_ID", "claude-3-5-sonnet-20241022")

# 2. Cloud 配置 (通用 OpenAI 兼容协议，可用于阿里 Qwen, 智谱, 一言, DeepSeek等)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL_ID = os.getenv("OPENAI_MODEL_ID", "gpt-4o")

# 3. Local 配置 (vLLM / Ollama / 局域网微小模型推断加速)
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
LOCAL_BASE_URL = os.getenv("LOCAL_BASE_URL", "http://localhost:8000/v1")
LOCAL_MODEL_ID = os.getenv("LOCAL_MODEL_ID", "qwen-7b-lora")
LORA_ADAPTER_PATH = os.getenv("LORA_ADAPTER_PATH", "")

# 动态计算供外部 UI (main.py / streamlit) 渲染用的活动 MODEL_ID
if USE_LOCAL_LLM:
    MODEL_ID = LOCAL_MODEL_ID
elif LLM_PROVIDER == "openai":
    MODEL_ID = OPENAI_MODEL_ID
else:
    MODEL_ID = ANTHROPIC_MODEL_ID

# 提示缺失的关键凭证
if LLM_PROVIDER == "anthropic" and not USE_LOCAL_LLM and not ANTHROPIC_API_KEY:
    print("\033[91mError: ANTHROPIC_API_KEY is not set. To use local models, set USE_LOCAL_LLM=true.\033[0m")
elif LLM_PROVIDER == "openai" and not USE_LOCAL_LLM and not OPENAI_API_KEY:
    print("\033[91mError: OPENAI_API_KEY is not set. To use local models, set USE_LOCAL_LLM=true.\033[0m")


class TokenCounterCallback(BaseCallbackHandler):
    """
    Token 用量追踪回调 (Token Counter Callback)
    无缝接管无论来自 Anthropic 还是 OpenAI (Qwen) 的 Token 结算返回。
    """
    def on_llm_end(self, response, **kwargs):
        """LLM 调用结束时记录 Token 用量"""
        try:
            if response and response.llm_output:
                usage = response.llm_output.get("token_usage", {})
                
                # 由于不同厂商的 usage 字典 Key 命名规范不同，需要双重捕获
                input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
                
                if input_tokens or output_tokens:
                    record_token_usage(input_tokens, output_tokens)
        except Exception as e:
            logger.debug(f"Token counter callback error: {e}")


# --- 全局 LLM 实例回调器 ---
token_counter = TokenCounterCallback()


def get_llm(streaming: bool = False) -> BaseChatModel:
    """
    获取标准化的 LLM 实例引擎 (支持云端各厂商与本地大满贯)

    【路由策略】
    1. USE_LOCAL_LLM 拥有最高权重。如果开启，强制直连 localhost 算力端点。
    2. LLM_PROVIDER="openai" 走通用标准协议（百炼 Qwen / 腾讯混元 / DeepSeek）。
    3. LLM_PROVIDER="anthropic" 走 Claude 专用协议及其原生高级功能。
    """
    
    # --- 路由 1: 局域网本地模型 ---
    if USE_LOCAL_LLM:
        if ChatOpenAI is None:
            raise ImportError("USE_LOCAL_LLM is true but 'langchain-openai' is not installed. Please run 'pip install langchain-openai'.")
        logger.info(f"Using Local LLM at {LOCAL_BASE_URL} with model {LOCAL_MODEL_ID}")
        return ChatOpenAI(
            model=LOCAL_MODEL_ID,
            openai_api_key="local-placeholder",
            openai_api_base=LOCAL_BASE_URL,
            max_tokens=8192,
            streaming=streaming,
            callbacks=[token_counter],
        )

    # --- 路由 2: Qwen / DeepSeek / 通用大模型 ---
    if LLM_PROVIDER == "openai":
        if ChatOpenAI is None:
            raise ImportError("LLM_PROVIDER is openai but 'langchain-openai' is not installed. Please pip install langchain-openai")
        if not OPENAI_API_KEY:
            raise RuntimeError("API client not initialized. Check your OPENAI_API_KEY in .env")
        
        logger.info(f"Using OpenAI Compatible API. Model: {OPENAI_MODEL_ID} At {OPENAI_BASE_URL}")
        return ChatOpenAI(
            model=OPENAI_MODEL_ID,
            openai_api_key=OPENAI_API_KEY,
            openai_api_base=OPENAI_BASE_URL,
            max_tokens=8192,
            streaming=streaming,
            callbacks=[token_counter],
        )

    # --- 路由 3: Anthropic 家族 (默认) ---
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("API client not initialized. Check your ANTHROPIC_API_KEY in .env")

    kwargs = {
        "model": getattr(os, "environ", {}).get("MODEL_ID", ANTHROPIC_MODEL_ID), # 兼容老 .env 格式
        "api_key": ANTHROPIC_API_KEY,
        "max_tokens": 8192,
        "streaming": streaming,
        "callbacks": [token_counter],
    }

    if ANTHROPIC_BASE_URL and ANTHROPIC_BASE_URL != "https://api.anthropic.com":
        kwargs["base_url"] = ANTHROPIC_BASE_URL

    return ChatAnthropic(**kwargs)


try:
    # 预构建的全局懒加载实例
    llm = get_llm(streaming=False)
except RuntimeError as e:
    # 当没提供 key 时不应该在导包时报错崩溃，而是推迟到运行时拦截
    logger.warning(f"Error initializing static llm: {e}")
    llm = None
    
try:
    llm_streaming = get_llm(streaming=True)
except RuntimeError:
    llm_streaming = None
