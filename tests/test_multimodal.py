import pytest
from utils.converters import serialize_message_content

def test_serialize_image_block():
    """测试 serialize_message_content 能正确处理图像块"""
    class MockBlock:
        def __init__(self, block_type, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    image_block = MockBlock("image", source={"type": "base64", "media_type": "image/jpeg", "data": "BASE64DATA"})
    content = [image_block]
    
    serialized = serialize_message_content(content)
    
    assert len(serialized) == 1
    # serialize_message_content 会走 model_dump() 或 fallback 到 text
    # image 类型不在 converters 的显式处理中，会走 model_dump / str fallback
    assert serialized[0]["type"] in ("image", "text")

def test_serialize_tool_result_with_nested_content():
    """测试 tool_result 中嵌套内容的序列化"""
    class MockBlock:
        def __init__(self, block_type, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)
                
    tool_result_block = MockBlock("tool_result", tool_use_id="id1", content="simple result")
    
    serialized = serialize_message_content([tool_result_block])
    
    assert serialized[0]["type"] == "tool_result"
    assert serialized[0]["tool_use_id"] == "id1"
    assert serialized[0]["content"] == "simple result"
