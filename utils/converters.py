"""
utils/converters.py - 数据格式转换与序列化工具

【设计意图】
将不同 LLM SDK 或框架（Anthropic, LangChain）返回的复杂内容对象统一序列化为标准 Python 类型。
解耦 core/swarm.py 和 managers/team.py 中的冗余逻辑。
"""

def serialize_message_content(content):
    """
    将消息内容（可能是列表或复杂对象）序列化为标准 dict 列表或字符串。
    
    参数：
    - content: 消息内容内容块
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
            # 处理 Anthropic 风格的消息块
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
                    # Pydantic 模型或其他具有 model_dump 方法的对象
                    serialized.append(block.model_dump())
                except Exception:
                    serialized.append({"type": "text", "text": str(block)})
        else:
            serialized.append({"type": "text", "text": str(block)})
            
    return serialized
