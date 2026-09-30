"""apps.core.llm 统一 LLM 客户端：URL/请求体构建、同步/异步/流式调用、错误归一化、Bedrock 路由"""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.core.llm import (
    LLMClient, LLMConfig, LLMError, LLMTimeoutError, build_chat_url, chat_openai_kwargs,
    resolve_base_url, resolve_temperature,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def _config(**kwargs):
    defaults = dict(api_key='sk-test', base_url='https://llm.example.com', model_name='m1',
                    model_type='deepseek', max_tokens=100, temperature=0.5, top_p=0.9)
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestUrlAndPayload:
    @pytest.mark.parametrize('base_url,auto_version,expected', [
        ('https://api.deepseek.com', True, 'https://api.deepseek.com/v1/chat/completions'),
        ('https://api.deepseek.com/', False, 'https://api.deepseek.com/chat/completions'),
        ('https://open.bigmodel.cn/api/paas/v4', True, 'https://open.bigmodel.cn/api/paas/v4/chat/completions'),
        ('https://x.com/v1/chat/completions', True, 'https://x.com/v1/chat/completions'),
    ])
    def test_build_chat_url(self, base_url, auto_version, expected):
        assert build_chat_url(base_url, auto_version=auto_version) == expected

    def test_resolve_base_url_defaults(self):
        assert resolve_base_url('siliconflow', None) == 'https://api.siliconflow.cn/v1'
        assert resolve_base_url('deepseek', 'https://custom') == 'https://custom'
        assert resolve_base_url('unknown', '') is None

    def test_config_from_obj_prefers_model_type_and_ignores_non_str(self):
        mock = MagicMock()
        mock.model_type = 'bedrock_claude'
        assert LLMConfig.from_obj(mock).is_bedrock
        assert LLMConfig.from_obj({'provider': 'openai'}).provider == 'openai'
        assert LLMConfig.from_obj(SimpleNamespace(service_type='qwen')).provider == 'qwen'

    def test_payload_defaults_and_overrides(self):
        client = LLMClient(_config())
        payload = client.build_payload([{'role': 'user', 'content': 'hi'}], max_tokens=5)
        assert payload['max_tokens'] == 5
        assert payload['temperature'] == 0.5 and payload['top_p'] == 0.9
        # defaults=() 只发显式参数（测试连接场景）
        payload = client.build_payload([], defaults=(), max_tokens=1)
        assert payload == {'model': 'm1', 'messages': [], 'max_tokens': 1}
        payload = client.build_payload([], stream=True, tools=[], tool_choice='auto')
        assert payload['stream'] is True and payload['tools'] == [] and payload['tool_choice'] == 'auto'


class TestHttpCalls:
    def _client(self, handler, **kwargs):
        return LLMClient(_config(), transport=httpx.MockTransport(handler), **kwargs)

    def test_chat_success_sends_bearer_and_json(self):
        seen = {}

        def handler(request):
            seen['url'] = str(request.url)
            seen['auth'] = request.headers['Authorization']
            seen['body'] = json.loads(request.content)
            return httpx.Response(200, json={'choices': [{'message': {'content': 'ok'}}]})

        result = self._client(handler).chat([{'role': 'user', 'content': 'hi'}])
        assert result['choices'][0]['message']['content'] == 'ok'
        assert seen['url'] == 'https://llm.example.com/v1/chat/completions'
        assert seen['auth'] == 'Bearer sk-test'
        assert seen['body']['model'] == 'm1'

    def test_http_error_is_llm_error_with_status(self):
        client = self._client(lambda r: httpx.Response(401, text='bad key'))
        with pytest.raises(LLMError) as exc:
            client.chat([])
        assert exc.value.status_code == 401 and exc.value.body == 'bad key'
        assert not isinstance(exc.value, LLMTimeoutError)

    def test_timeout_is_llm_timeout_error(self):
        def handler(request):
            raise httpx.ReadTimeout('slow', request=request)

        with pytest.raises(LLMTimeoutError):
            self._client(handler).chat([])
        with pytest.raises(LLMTimeoutError):
            _run(self._client(handler).achat([]))

    def test_achat_success(self):
        client = self._client(lambda r: httpx.Response(200, json={'choices': [{'message': {'content': 'a'}}]}))
        assert _run(client.achat([]))['choices'][0]['message']['content'] == 'a'

    def test_astream_yields_deltas_and_finish_reason(self):
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'hel'}, 'finish_reason': None}]}),
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'lo'}, 'finish_reason': 'length'}]}),
            'data: [DONE]',
        ]
        client = self._client(lambda r: httpx.Response(200, text='\n\n'.join(lines)))

        async def collect():
            return [d async for d in client.astream([])]

        deltas = _run(collect())
        assert ''.join(d.content for d in deltas) == 'hello'
        assert deltas[-1].finish_reason == 'length'

    def test_missing_base_url_raises(self):
        client = LLMClient(_config(base_url=None, model_type='other'))
        with pytest.raises(LLMError):
            client.chat([])


class TestBedrockRouting:
    @patch('apps.requirement_analysis.bedrock_adapter.boto3')
    def test_achat_routes_to_bedrock_adapter(self, mock_boto3):
        mock_boto3.client.return_value.converse.return_value = {
            'output': {'message': {'content': [{'text': 'from bedrock'}]}}
        }
        config = _config(model_type='bedrock_claude', aws_region='us-east-1', aws_access_key_id='k',
                         aws_secret_access_key='s', aws_model_id='anthropic.claude')
        result = _run(LLMClient(config).achat([{'role': 'user', 'content': 'hi'}]))
        assert result['choices'][0]['message']['content'] == 'from bedrock'
        mock_boto3.client.return_value.converse.assert_called_once()

    @patch('apps.requirement_analysis.bedrock_adapter.boto3')
    def test_bedrock_error_wrapped(self, mock_boto3):
        mock_boto3.client.return_value.converse.side_effect = RuntimeError('denied')
        config = _config(model_type='bedrock_claude', aws_region='us-east-1', aws_access_key_id='k',
                         aws_secret_access_key='s', aws_model_id='anthropic.claude')
        with pytest.raises(LLMError, match='Bedrock API 调用失败'):
            LLMClient(config).chat([{'role': 'user', 'content': 'hi'}])


class TestLangchainMapping:
    def test_special_model_temperature(self):
        assert resolve_temperature('Kimi-K2.5', 0.3) == 1.0
        assert resolve_temperature('gpt-4o', 0.3) == 0.3
        assert resolve_temperature('gpt-4o', None) == 0.0

    def test_chat_openai_kwargs_fills_default_base_url(self):
        kwargs = chat_openai_kwargs({'api_key': 'k', 'base_url': None, 'model_name': 'deepseek-chat',
                                     'provider': 'deepseek', 'temperature': 0.2})
        assert kwargs == {'model': 'deepseek-chat', 'api_key': 'k',
                          'base_url': 'https://api.deepseek.com', 'temperature': 0.2}


class TestAIModelServiceUsesCoreClient:
    def test_reexport_from_models(self):
        from apps.requirement_analysis.ai_service import AIModelService as direct
        from apps.requirement_analysis.models import AIModelService
        assert AIModelService is direct

    def test_http_error_message_format_preserved(self):
        from apps.requirement_analysis.ai_service import AIModelService
        config = _config()
        config.get_model_type_display = lambda: 'DeepSeek'
        with patch('apps.requirement_analysis.ai_service.LLMClient.achat',
                   side_effect=LLMError('500 - boom', status_code=500, body='boom')):
            with pytest.raises(Exception, match='DeepSeek API返回错误 500: boom'):
                _run(AIModelService.call_openai_compatible_api(config, []))

    def test_stream_auto_continues_on_length(self):
        from apps.core.llm import StreamDelta
        from apps.requirement_analysis.ai_service import AIModelService

        calls = []

        async def fake_astream(self, messages, **params):
            calls.append([dict(m) for m in messages])
            if len(calls) == 1:
                yield StreamDelta('part1', 'length')
            else:
                yield StreamDelta('part2', 'stop')

        received = []

        async def callback(chunk):
            received.append(chunk)

        async def collect():
            return [c async for c in AIModelService.call_openai_compatible_api_stream(
                _config(), [{'role': 'user', 'content': 'go'}], callback=callback)]

        with patch('apps.core.llm.client.LLMClient.astream', fake_astream):
            chunks = _run(collect())
        assert chunks == ['part1', 'part2'] and received == chunks
        assert len(calls) == 2
        assert calls[1][-2] == {'role': 'assistant', 'content': 'part1'}
        assert calls[1][-1]['role'] == 'user'



class TestBedrockStreamCallback:
    """Bedrock 流式输出按增量回调，与生成流水线 `stream_buffer += chunk` 的用法一致"""

    def test_callback_receives_increments_not_accumulated_text(self):
        from apps.requirement_analysis.ai_service import AIModelService

        async def fake_stream(config, messages, callback=None, max_tokens=None):
            full = ''
            for part in ('ab', 'cd'):
                full += part
                if callback:
                    await callback(full)
                yield part

        received = []

        async def cb(chunk):
            received.append(chunk)

        async def run():
            config = SimpleNamespace(model_type='bedrock_claude', max_tokens=100)
            return [c async for c in AIModelService.call_openai_compatible_api_stream(config, [], cb)]

        with patch('apps.requirement_analysis.bedrock_adapter.BedrockAdapter.call_stream', fake_stream):
            chunks = asyncio.run(run())

        assert chunks == ['ab', 'cd']
        assert received == ['ab', 'cd']
