import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from utils.generate_completion import generate_completion

@pytest.mark.asyncio
async def test_generate_completion():
    """Test the generate_completion function."""
    # Mock the AsyncClient and its generate method
    mock_response = MagicMock()
    mock_response.response = "This is a test response"
    
    mock_client = AsyncMock()
    mock_client.generate.return_value = mock_response
    
    with patch("utils.generate_completion.AsyncClient", return_value=mock_client):
        with patch("utils.generate_completion.get_default_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.model = "test-model"
            mock_get_model.return_value = mock_model
            
            # Test with just prompt
            result = await generate_completion("Test prompt")
            assert result == "This is a test response"
            mock_client.generate.assert_called_with(
                model="test-model",
                prompt="Test prompt",
                think=False
            )
            
            # Reset mocks
            mock_client.reset_mock()
            
            # Test with system and prompt
            result = await generate_completion("Test prompt", system="System instruction", think=True)
            assert result == "This is a test response"
            mock_client.generate.assert_called_with(
                model="test-model",
                prompt="System instruction\n\nTest prompt",
                think=True
            )

@pytest.mark.asyncio
async def test_generate_completion_error_handling():
    """Test error handling in the generate_completion function."""
    mock_client = AsyncMock()
    mock_client.generate.side_effect = Exception("Test error")
    
    with patch("utils.generate_completion.AsyncClient", return_value=mock_client):
        with patch("utils.generate_completion.get_default_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.model = "test-model"
            mock_get_model.return_value = mock_model
            
            with pytest.raises(RuntimeError) as excinfo:
                await generate_completion("Test prompt")
            
            assert "Failed to generate completion" in str(excinfo.value)
