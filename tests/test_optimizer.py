import os
import sys
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_optimize_returns_string_when_disabled():
    """When OPENAI_ENABLED=false, original message is returned unchanged."""
    import optimizer
    with patch.object(optimizer, "OPENAI_ENABLED", False):
        result = asyncio.get_event_loop().run_until_complete(
            optimizer.optimize_prompt("hello world")
        )
        assert result == "hello world"


def test_optimize_returns_string_when_no_api_key():
    """When OPENAI_API_KEY is empty, original message is returned unchanged."""
    import optimizer
    with patch.object(optimizer, "OPENAI_ENABLED", True), \
         patch.object(optimizer, "OPENAI_API_KEY", ""):
        result = asyncio.get_event_loop().run_until_complete(
            optimizer.optimize_prompt("hello world")
        )
        assert result == "hello world"


def test_optimize_graceful_on_api_error():
    """When OpenAI raises an exception, original message is returned."""
    import optimizer
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

    with patch.object(optimizer, "OPENAI_ENABLED", True), \
         patch.object(optimizer, "OPENAI_API_KEY", "sk-test"), \
         patch.object(optimizer, "AsyncOpenAI", return_value=mock_client):
        result = asyncio.get_event_loop().run_until_complete(
            optimizer.optimize_prompt("hello world")
        )
        assert result == "hello world"


def test_optimize_trims_long_input():
    """Input longer than MAX_OPTIMIZED_PROMPT_LENGTH gets trimmed before sending."""
    import optimizer
    mock_choice = MagicMock()
    mock_choice.message.content = "optimized"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch.object(optimizer, "OPENAI_ENABLED", True), \
         patch.object(optimizer, "OPENAI_API_KEY", "sk-test"), \
         patch.object(optimizer, "MAX_OPTIMIZED_PROMPT_LENGTH", 10), \
         patch.object(optimizer, "AsyncOpenAI", return_value=mock_client):
        long_input = "a" * 100
        result = asyncio.get_event_loop().run_until_complete(
            optimizer.optimize_prompt(long_input)
        )
        # Check that the message sent to OpenAI was trimmed
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        user_msg = [m for m in messages if m["role"] == "user"][0]
        assert len(user_msg["content"]) == 10
        assert result == "optimized"
