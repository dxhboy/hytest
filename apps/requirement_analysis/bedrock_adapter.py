import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List

import boto3

logger = logging.getLogger(__name__)


class BedrockAdapter:
    """将 AWS Bedrock converse API 适配为与 AIModelService 一致的接口。"""

    @staticmethod
    def _build_client(config):
        return boto3.client(
            'bedrock-runtime',
            region_name=config.aws_region or 'us-east-1',
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )

    @staticmethod
    def _split_messages(messages: List[Dict[str, str]]):
        """将 OpenAI 格式 messages 拆分为 system 列表和 conversation 列表。"""
        system_parts = []
        conversation = []
        for msg in messages:
            if msg['role'] == 'system':
                system_parts.append({'text': msg['content']})
            else:
                conversation.append({
                    'role': msg['role'],
                    'content': [{'text': msg['content']}],
                })
        return system_parts, conversation

    @staticmethod
    async def call(config, messages: List[Dict[str, str]], max_tokens: int = None) -> Dict[str, Any]:
        """非流式调用，返回与 call_openai_compatible_api 一致的结构。"""
        actual_max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        system_parts, conversation = BedrockAdapter._split_messages(messages)

        def _invoke():
            client = BedrockAdapter._build_client(config)
            kwargs = dict(
                modelId=config.aws_model_id,
                messages=conversation,
                inferenceConfig={
                    'maxTokens': actual_max_tokens,
                    'temperature': config.temperature,
                    'topP': config.top_p,
                },
            )
            if system_parts:
                kwargs['system'] = system_parts
            logger.info(f"Bedrock converse: model={config.aws_model_id}, region={config.aws_region}")
            return client.converse(**kwargs)

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(None, _invoke)
        except Exception as e:
            logger.error(f"Bedrock API 调用失败: {repr(e)}")
            raise Exception(f"Bedrock API 调用失败: {str(e) or repr(e)}")

        text = response['output']['message']['content'][0]['text']
        return {
            'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}],
            'usage': response.get('usage', {}),
        }

    @staticmethod
    async def call_stream(config, messages: List[Dict[str, str]], callback=None, max_tokens: int = None) -> AsyncIterator[str]:
        """流式调用，逐块 yield 文本；callback 与现有 SSE 回调兼容。"""
        actual_max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        system_parts, conversation = BedrockAdapter._split_messages(messages)

        def _invoke_stream():
            client = BedrockAdapter._build_client(config)
            kwargs = dict(
                modelId=config.aws_model_id,
                messages=conversation,
                inferenceConfig={
                    'maxTokens': actual_max_tokens,
                    'temperature': config.temperature,
                    'topP': config.top_p,
                },
            )
            if system_parts:
                kwargs['system'] = system_parts
            logger.info(f"Bedrock converse_stream: model={config.aws_model_id}")
            return client.converse_stream(**kwargs)

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(None, _invoke_stream)
        except Exception as e:
            logger.error(f"Bedrock 流式 API 调用失败: {repr(e)}")
            raise Exception(f"Bedrock 流式 API 调用失败: {str(e) or repr(e)}")

        full_content = ""
        for event in response['stream']:
            if 'contentBlockDelta' in event:
                chunk = event.get('contentBlockDelta', {}).get('delta', {}).get('text', '')
                if chunk:
                    full_content += chunk
                    if callback:
                        await callback(full_content)
                    yield chunk
