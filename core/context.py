"""
core/context.py - 上下文控制与窗口压缩器 (LangChain 1.0 重构版)

【设计意图】
使用 LangChain 的 trim_messages 工具替代手写的三级压缩机制。
保留 auto_compact 和 manual compress 的业务语义，但底层实现更加标准化。
"""

import logging
import json
from typing import List

from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage, 
    trim_messages, RemoveMessage
)

logger = logging.getLogger(__name__)


class ContextManager:
    """
    上下文控制与窗口压缩器 (Context Management) - LangChain 版本

    【设计意图】
    利用 LangChain 的 trim_messages 实现智能裁剪，
    同时保留手动压缩（compress 工具触发）的能力。
    """

    @staticmethod
    def trim_context(messages: List[BaseMessage], llm=None, max_tokens: int = 50000) -> List[BaseMessage]:
        """
        智能上下文裁剪（替代原来的 microcompact + auto_compact）

        【设计意图】
        LangChain 的 trim_messages 能根据 Token 数量智能保留最近的消息，
        同时确保消息序列的完整性（不会截断到一半）。
        """
        try:
            if llm:
                return trim_messages(
                    messages,
                    max_tokens=max_tokens,
                    strategy="last",
                    token_counter=llm,
                    include_system=True,
                    start_on="human",
                )
            else:
                # 退路方案：按消息条数裁剪
                if len(messages) > 40:
                    # 保留系统消息 + 最近 20 条
                    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
                    recent = messages[-20:]
                    return system_msgs + recent
                return messages
        except Exception as e:
            logger.warning(f"trim_context fallback: {e}")
            if len(messages) > 40:
                return messages[:1] + messages[-20:]
            return messages

    @staticmethod
    def perform_full_compression(messages: list, current_task_info: str):
        """
        全量清理：供 `compress` 工具触发。
        彻底遗忘细枝末节，仅把"当前进行到哪"强行灌输给一张白纸。

        【保持兼容】此方法同时支持原始 dict 格式和 LangChain Message 格式。
        """
        messages.clear()
        messages.append(
            HumanMessage(
                content=f"[SYSTEM RESTART]\nWe have just compressed history.\n"
                        f"Current tasks state:\n{current_task_info}\nPlease resume your work."
            )
        )
