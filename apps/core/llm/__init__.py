"""
统一 LLM 客户端（OpenAI 兼容格式）

用法::

    from apps.core.llm import LLMClient, LLMError, LLMTimeoutError

    client = LLMClient(ai_model_config, read_timeout=60)
    result = client.chat([{'role': 'user', 'content': 'Hi'}], max_tokens=1)
    result = await client.achat(messages)
    async for delta in client.astream(messages):
        print(delta.content, delta.finish_reason)
"""
from .client import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    LLMClient,
    LLMError,
    LLMTimeoutError,
    StreamDelta,
    extract_content,
)
from .config import (
    PROVIDER_DEFAULT_BASE_URLS,
    LLMConfig,
    build_chat_url,
    build_headers,
    resolve_base_url,
)
from .langchain import chat_openai_kwargs, resolve_temperature

__all__ = [
    'DEFAULT_CONNECT_TIMEOUT', 'DEFAULT_READ_TIMEOUT',
    'LLMClient', 'LLMError', 'LLMTimeoutError', 'StreamDelta', 'extract_content',
    'PROVIDER_DEFAULT_BASE_URLS', 'LLMConfig', 'build_chat_url', 'build_headers', 'resolve_base_url',
    'chat_openai_kwargs', 'resolve_temperature',
]
