"""
OpenAI 兼容格式的统一 LLM 客户端

- chat():   同步调用（httpx.Client）
- achat():  异步调用（httpx.AsyncClient）
- astream(): 异步流式调用，逐条 yield StreamDelta(content, finish_reason)
- provider 为 bedrock_claude 时，路由到 apps.requirement_analysis.bedrock_adapter.BedrockAdapter

所有网络/协议错误统一抛出 LLMError（超时为其子类 LLMTimeoutError）。
"""
import asyncio
import json
import logging
from typing import Any, AsyncIterator, Dict, List, NamedTuple, Optional

import httpx

from .config import LLMConfig, build_chat_url, build_headers

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT = 10.0
DEFAULT_READ_TIMEOUT = 120.0
SAMPLING_KEYS = ('max_tokens', 'temperature', 'top_p')


class LLMError(Exception):
    """LLM 调用统一异常"""

    def __init__(self, message: str, status_code: Optional[int] = None, body: Optional[str] = None,
                 provider: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.body = body
        self.provider = provider


class LLMTimeoutError(LLMError):
    """LLM 调用超时"""


class StreamDelta(NamedTuple):
    content: str
    finish_reason: Optional[str]


class LLMClient:
    """OpenAI 兼容客户端"""

    def __init__(self, config, read_timeout: float = DEFAULT_READ_TIMEOUT,
                 connect_timeout: float = DEFAULT_CONNECT_TIMEOUT, auto_version: bool = True,
                 transport=None):
        """
        Args:
            config: AIModelConfig / AIServiceConfig / dict / LLMConfig
            read_timeout: 读取超时（秒）
            connect_timeout: 连接超时（秒）
            auto_version: base_url 未带 /vN 时是否自动补 /v1，见 build_chat_url
            transport: 可选的 httpx transport（测试时注入 httpx.MockTransport）
        """
        self.config = LLMConfig.from_obj(config)
        self.read_timeout = read_timeout
        self.connect_timeout = connect_timeout
        self.auto_version = auto_version
        self.transport = transport

    # ------------------------------------------------------------------ #
    # 请求构建
    # ------------------------------------------------------------------ #
    @property
    def url(self) -> str:
        base_url = self.config.resolved_base_url
        if not base_url:
            raise LLMError('未配置 API Base URL', provider=self.config.provider)
        return build_chat_url(base_url, auto_version=self.auto_version)

    @property
    def headers(self) -> dict:
        return build_headers(self.config.api_key)

    @property
    def timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=max(self.connect_timeout, 60.0),
            pool=max(self.connect_timeout, 60.0),
        )

    def _client_kwargs(self) -> dict:
        kwargs = {'timeout': self.timeout, 'http2': False}
        if self.transport is not None:
            kwargs['transport'] = self.transport
        return kwargs

    def build_payload(self, messages: List[Dict[str, Any]], stream: bool = False,
                      defaults=SAMPLING_KEYS, **params) -> dict:
        """
        构建请求体。

        Args:
            defaults: 需要从配置回填的采样参数键（max_tokens/temperature/top_p 的子集）；
                      传 () 表示只发送显式传入的参数（如测试连接时不带 temperature）
            params: 显式参数，非 None 值覆盖配置；其他键（tools/tool_choice/stream 等）原样透传
        """
        cfg = self.config
        payload = {'model': params.pop('model', None) or cfg.model_name, 'messages': messages}
        for key in SAMPLING_KEYS:
            value = params.pop(key, None)
            if value is None and key in defaults:
                value = getattr(cfg, key)
            if value is not None:
                payload[key] = value
        payload.update({k: v for k, v in params.items() if v is not None})
        if stream:
            payload['stream'] = True
        return payload

    # ------------------------------------------------------------------ #
    # 错误处理
    # ------------------------------------------------------------------ #
    def _check_response(self, status_code: int, text: str):
        if status_code != 200:
            logger.error(f"LLM API 返回错误: Status={status_code}, Body={text[:2000]}")
            raise LLMError(f'{status_code} - {text}', status_code=status_code, body=text,
                           provider=self.config.provider)

    def _wrap_exception(self, e: Exception) -> LLMError:
        if isinstance(e, LLMError):
            return e
        if isinstance(e, httpx.TimeoutException):
            return LLMTimeoutError(f'请求超时: {repr(e)}', provider=self.config.provider)
        return LLMError(str(e) or repr(e), provider=self.config.provider)

    @staticmethod
    def _parse_json(text: str, provider: str) -> dict:
        try:
            return json.loads(text)
        except (TypeError, ValueError) as e:
            raise LLMError(f'响应不是合法 JSON: {e}', body=text, provider=provider)

    # ------------------------------------------------------------------ #
    # Bedrock
    # ------------------------------------------------------------------ #
    async def _bedrock_call(self, messages, max_tokens=None) -> dict:
        from apps.requirement_analysis.bedrock_adapter import BedrockAdapter
        try:
            return await BedrockAdapter.call(self.config.source, messages, max_tokens)
        except Exception as e:
            raise LLMError(str(e) or repr(e), provider=self.config.provider)

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #
    def chat(self, messages: List[Dict[str, Any]], **params) -> dict:
        """同步调用，返回 OpenAI 格式响应 dict"""
        if self.config.is_bedrock:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(self._bedrock_call(messages, params.get('max_tokens')))
            raise LLMError('同步 chat() 不能在事件循环中调用 Bedrock，请使用 achat()',
                           provider=self.config.provider)

        url = self.url
        payload = self.build_payload(messages, **params)
        logger.info(f"LLM 同步请求: url={url}, model={payload.get('model')}")
        try:
            with httpx.Client(**self._client_kwargs()) as client:
                response = client.post(url, headers=self.headers, json=payload)
            self._check_response(response.status_code, response.text)
            return self._parse_json(response.text, self.config.provider)
        except Exception as e:
            raise self._wrap_exception(e)

    async def achat(self, messages: List[Dict[str, Any]], **params) -> dict:
        """异步调用，返回 OpenAI 格式响应 dict"""
        if self.config.is_bedrock:
            return await self._bedrock_call(messages, params.get('max_tokens'))

        url = self.url
        payload = self.build_payload(messages, **params)
        logger.info(f"LLM 异步请求: url={url}, model={payload.get('model')}, "
                    f"max_tokens={payload.get('max_tokens')}, temperature={payload.get('temperature')}")
        try:
            async with httpx.AsyncClient(**self._client_kwargs()) as client:
                response = await client.post(url, headers=self.headers, json=payload)
            self._check_response(response.status_code, response.text)
            return self._parse_json(response.text, self.config.provider)
        except Exception as e:
            raise self._wrap_exception(e)

    async def astream(self, messages: List[Dict[str, Any]], **params) -> AsyncIterator[StreamDelta]:
        """异步流式调用（SSE），逐条 yield StreamDelta"""
        if self.config.is_bedrock:
            from apps.requirement_analysis.bedrock_adapter import BedrockAdapter
            try:
                async for chunk in BedrockAdapter.call_stream(self.config.source, messages, None,
                                                             params.get('max_tokens')):
                    yield StreamDelta(chunk, None)
            except Exception as e:
                raise LLMError(str(e) or repr(e), provider=self.config.provider)
            yield StreamDelta('', 'stop')
            return

        url = self.url
        payload = self.build_payload(messages, stream=True, **params)
        try:
            async with httpx.AsyncClient(**self._client_kwargs()) as client:
                async with client.stream('POST', url, headers=self.headers, json=payload) as response:
                    if response.status_code != 200:
                        body = (await response.aread()).decode('utf-8', errors='replace')
                        self._check_response(response.status_code, body)

                    async for line in response.aiter_lines():
                        if not line.strip() or not line.startswith('data: '):
                            continue
                        data_str = line[6:]
                        if data_str.strip() == '[DONE]':
                            break
                        try:
                            chunk_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk_data.get('choices') or []
                        if not choices:
                            continue
                        choice = choices[0]
                        content = (choice.get('delta') or {}).get('content') or ''
                        finish_reason = choice.get('finish_reason')
                        if content or finish_reason:
                            yield StreamDelta(content, finish_reason)
        except Exception as e:
            raise self._wrap_exception(e)


def extract_content(response: dict) -> str:
    """从 OpenAI 格式响应中取出首条消息文本"""
    try:
        return response['choices'][0]['message'].get('content') or ''
    except (KeyError, IndexError, TypeError, AttributeError):
        return ''
