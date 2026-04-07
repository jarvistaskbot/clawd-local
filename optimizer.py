"""
optimizer.py — Optimizes user prompts via OpenAI before sending to Claude.
When OPENAI_ENABLED=false, returns prompt unchanged.
"""

import logging

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_ENABLED, MAX_OPTIMIZED_PROMPT_LENGTH

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a prompt optimizer. The user wants you to improve their request "
    "so it gets better results from an AI assistant. "
    "Rewrite it as a direct, specific, actionable instruction. "
    "Do NOT explain what you did, do NOT add headers like 'Prompt:' or 'Audit Prompt:', "
    "do NOT add markdown formatting around the prompt. "
    "Just return the improved instruction text directly, ready to be executed."
)


async def optimize_prompt(user_message: str, conversation_context: str = "") -> str:
    if not OPENAI_ENABLED or not OPENAI_API_KEY:
        return user_message

    trimmed = user_message[:MAX_OPTIMIZED_PROMPT_LENGTH]

    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if conversation_context:
            messages.append({"role": "system", "content": f"Conversation context: {conversation_context}"})
        messages.append({"role": "user", "content": trimmed})

        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=500,
        )
        optimized = response.choices[0].message.content.strip()
        if optimized:
            return optimized
        return user_message
    except Exception as e:
        logger.warning("OpenAI optimization failed, using original prompt: %s", e)
        return user_message
