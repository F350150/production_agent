import logging
import json

logger = logging.getLogger(__name__)

class ContextManager:
    """
    上下文控制与窗口压缩器 (Context Management)
    
    【设计意图】
    由于大模型对长上下文敏感（虽然能吃几十万 Token，但是价格极其昂贵且容易“迷失”），
    本模块利用三级压缩机制控制 Token 开支并保持记忆敏锐度：
    1. microcompact: 毫秒级的实时修剪。
    2. auto_compact: 周期性历史折叠器（当历史记录过长时，总结旧案子，保留新记录）。
    3. manual compress: 供模型主动调用的重启清理器。
    """
    
    @staticmethod
    def microcompact(messages: list):
        """
        微观清理：主要为了擦除图片等多媒体冗余数据，
        并在连续多次人类发言时进行融合，防止数组序列化错误。
        """
        for m in messages:
            content = m.get("content")
            if isinstance(content, list):
                # Anthropic 返回的 block 是对象 (有 .type 属性)，而我们自己 append 的往往是 dict (有 .get 方法)
                new_content = []
                for b in content:
                    if hasattr(b, "type"):
                        if b.type != "image":
                            new_content.append(b)
                    elif isinstance(b, dict):
                        if b.get("type") != "image":
                            new_content.append(b)
                    else:
                        new_content.append(b)
                m["content"] = new_content

        # 融合连续的 user messages (注意：Anthropic API 虽然允许列表内的 tool_result，但最顶层最好合并)
        i = 0
        while i < len(messages) - 1:
            # 如果两个都是纯文本的 User Message，合并它们
            if messages[i]["role"] == "user" and messages[i+1]["role"] == "user" and isinstance(messages[i]["content"], str) and isinstance(messages[i+1]["content"], str):
                messages[i]["content"] += "\n" + messages[i+1]["content"]
                del messages[i+1]
            else:
                i += 1

    @staticmethod
    def auto_compact(messages: list, llm_callable):
        """
        自动折叠机制 (Auto Compact)。
        如果对话回合过多（超过 30 个 block），自动通过回溯总结压缩历史。
        """
        # 阈值设定 30 条。达到时压缩。
        if len(messages) > 30:
            logger.info(f"Auto-compact triggered (history size: {len(messages)}).")
            
            # 保留第一个引导消息（往往包含核心目标）和最后 8 条（核心近况）
            first_msg = messages[0] if messages else None
            recent_msgs = messages[-8:] if len(messages) > 8 else []
            history_to_compress = messages[1:-8] if len(messages) > 9 else []
            
            if not history_to_compress:
                return

            prompt = (
                "Please provide a concise summary of the key decisions, accomplishments, "
                "and used tools from the following conversation history. "
                "This summary will replace the history to save context space.\n\n"
            ) + json.dumps(history_to_compress, default=str)
            
            summary_msg = [{"role": "user", "content": prompt}]
            
            try:
                # 使用传入的 llm 回调获取总结
                summary_resp = llm_callable(summary_msg, "You are a helpful summarizer.", stream=False)
                summary_text = (
                    "--- [AUTO-SUMMARY OF PREVIOUS HISTORY] ---\n"
                    f"{summary_resp.content[0].text}\n"
                    "--- [END OF SUMMARY] ---"
                )
                
                # 重新构造消息列表
                new_messages = []
                if first_msg:
                    new_messages.append(first_msg)
                
                new_messages.append({"role": "user", "content": summary_text})
                new_messages.extend(recent_msgs)
                
                # 原地更新 messages
                messages.clear()
                messages.extend(new_messages)
                logger.info(f"Auto-compact complete. New history size: {len(messages)}")
                
            except Exception as e:
                logger.error(f"Auto-compact failed: {e}")
                
    @staticmethod
    def perform_full_compression(messages: list, current_task_info: str):
        """
        全量清理：供 `compress` 工具触发。
        彻底遗忘细枝末节，仅把“当前进行到哪”强行灌输给一张白纸。
        """
        messages.clear()
        messages.append({
            "role": "user",
            "content": f"[SYSTEM RESTART]\nWe have just compressed history.\nCurrent tasks state:\n{current_task_info}\nPlease resume your work."
        })
