import pytest
from unittest.mock import MagicMock, patch
import anthropic
from production_agent.core.llm import LLMProvider

@pytest.fixture
def mock_client():
    with patch("production_agent.core.llm.client") as mock:
        yield mock

def test_llm_provider_safe_call_success(mock_client):
    """测试成功的 LLM 调用"""
    # 模拟响应对象
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="Hello AI")]
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5
    
    mock_client.messages.create.return_value = mock_response
    
    # patch record_token_usage
    with patch("production_agent.core.llm.record_token_usage") as mock_record:
        # safe_llm_call 是静态方法
        response = LLMProvider.safe_llm_call(messages=[{"role": "user", "content": "hi"}], system_prompt="sys")
        assert response == mock_response
        mock_record.assert_called_once_with(10, 5)

def test_llm_provider_retry_logic(mock_client):
    """测试重试逻辑"""
    # 模拟第一次失败，第二次成功
    mock_response = MagicMock()
    mock_response.content = [MagicMock(type="text", text="Recovered")]
    mock_response.usage.input_tokens = 1
    mock_response.usage.output_tokens = 1
    
    mock_client.messages.create.side_effect = [
        anthropic.APIError(message="Error", request=MagicMock(), body=None),
        mock_response
    ]
    
    with patch("time.sleep"): # 避免测试变慢
        with patch("production_agent.core.llm.record_token_usage"):
            response = LLMProvider.safe_llm_call(messages=[{"role": "user", "content": "hi"}], system_prompt="sys")
            assert response == mock_response
            assert mock_client.messages.create.call_count == 2
