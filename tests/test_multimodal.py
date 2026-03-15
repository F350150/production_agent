import pytest
from core.swarm import _serialize_content

def test_serialize_image_block():
    """测试 _serialize_content 能正确处理图像块"""
    class MockBlock:
        def __init__(self, block_type, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    image_block = MockBlock("image", source={"type": "base64", "media_type": "image/jpeg", "data": "BASE64DATA"})
    content = [image_block]
    
    serialized = _serialize_content(content)
    
    assert len(serialized) == 1
    assert serialized[0]["type"] == "image"
    assert serialized[0]["source"]["data"] == "BASE64DATA"

def test_serialize_tool_result_with_image():
    """测试 tool_result 中嵌套图像块的序列化"""
    class MockBlock:
        def __init__(self, block_type, **kwargs):
            self.type = block_type
            for k, v in kwargs.items():
                setattr(self, k, v)
                
    image_block = MockBlock("image", source={"type": "base64", "media_type": "image/jpeg", "data": "IMG"})
    tool_result_block = MockBlock("tool_result", tool_use_id="id1", content=[image_block])
    
    serialized = _serialize_content([tool_result_block])
    
    assert serialized[0]["type"] == "tool_result"
    assert isinstance(serialized[0]["content"], list)
    assert serialized[0]["content"][0]["type"] == "image"
    assert serialized[0]["content"][0]["source"]["data"] == "IMG"
