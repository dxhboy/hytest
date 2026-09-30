import json
import logging
from apps.core.llm import LLMClient
from apps.requirement_analysis.models import AIModelConfig

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


# ---------------------------------------------------------------------------
# Format converters: OpenAI ↔ Anthropic
# ---------------------------------------------------------------------------

def _convert_tools_to_anthropic(tools: list) -> list:
    """OpenAI function-calling tool defs → Anthropic tool defs."""
    result = []
    for t in tools:
        func = t.get('function', {})
        result.append({
            'name': func['name'],
            'description': func.get('description', ''),
            'input_schema': func.get('parameters', {'type': 'object', 'properties': {}}),
        })
    return result


def _convert_messages_to_anthropic(messages: list) -> tuple[str, list]:
    """Extract system prompt and convert OpenAI messages → Anthropic format.

    Returns (system_text, anthropic_messages).
    Handles plain text, tool_calls (assistant), and tool results correctly.
    Consecutive tool-result messages are grouped into a single user turn.
    """
    system_parts = []
    anthropic_messages = []

    for msg in messages:
        role = msg.get('role', '')

        if role == 'system':
            system_parts.append(msg['content'])

        elif role == 'user':
            anthropic_messages.append({'role': 'user', 'content': msg['content']})

        elif role == 'assistant':
            if msg.get('tool_calls'):
                content_blocks = []
                if msg.get('content'):
                    content_blocks.append({'type': 'text', 'text': msg['content']})
                for tc in msg['tool_calls']:
                    args = tc['function']['arguments']
                    content_blocks.append({
                        'type': 'tool_use',
                        'id': tc['id'],
                        'name': tc['function']['name'],
                        'input': json.loads(args) if isinstance(args, str) else args,
                    })
                anthropic_messages.append({'role': 'assistant', 'content': content_blocks})
            else:
                anthropic_messages.append({'role': 'assistant', 'content': msg.get('content') or ''})

        elif role == 'tool':
            tool_result_block = {
                'type': 'tool_result',
                'tool_use_id': msg['tool_call_id'],
                'content': msg['content'],
            }
            if (anthropic_messages
                    and anthropic_messages[-1]['role'] == 'user'
                    and isinstance(anthropic_messages[-1]['content'], list)
                    and anthropic_messages[-1]['content']
                    and anthropic_messages[-1]['content'][0].get('type') == 'tool_result'):
                anthropic_messages[-1]['content'].append(tool_result_block)
            else:
                anthropic_messages.append({'role': 'user', 'content': [tool_result_block]})

    return '\n'.join(system_parts).strip(), anthropic_messages


def _normalize_anthropic_response(response) -> dict:
    """Anthropic Message → OpenAI-shaped dict expected by run_tool_loop."""
    text_parts = []
    tool_calls = []

    for block in response.content:
        if block.type == 'text':
            text_parts.append(block.text)
        elif block.type == 'tool_use':
            tool_calls.append({
                'id': block.id,
                'type': 'function',
                'function': {
                    'name': block.name,
                    'arguments': json.dumps(block.input, ensure_ascii=False),
                },
            })

    message = {
        'role': 'assistant',
        'content': '\n'.join(text_parts) if text_parts else None,
    }
    if tool_calls:
        message['tool_calls'] = tool_calls

    finish_reason = 'tool_calls' if response.stop_reason == 'tool_use' else 'stop'

    return {'choices': [{'message': message, 'finish_reason': finish_reason}]}


# ---------------------------------------------------------------------------
# LLM call backends
# ---------------------------------------------------------------------------

def _call_openai_compatible(config, messages: list, tools: list) -> dict:
    """OpenAI 兼容格式（含 function calling），HTTP 层走统一 LLM 客户端"""
    client = LLMClient(config, read_timeout=60.0)
    return client.chat(
        messages,
        defaults=('max_tokens', 'temperature'),
        tools=tools,
        tool_choice='auto',
    )


def _call_anthropic_api(client, model: str, config, messages: list, tools: list) -> dict:
    """Shared call logic for direct Anthropic and Bedrock Claude."""
    anthropic_tools = _convert_tools_to_anthropic(tools)
    system_text, anthropic_messages = _convert_messages_to_anthropic(messages)

    kwargs = {
        'model': model,
        'max_tokens': config.max_tokens or 4096,
        'messages': anthropic_messages,
    }
    if system_text:
        kwargs['system'] = system_text
    if anthropic_tools:
        kwargs['tools'] = anthropic_tools
    if config.temperature is not None:
        kwargs['temperature'] = config.temperature

    response = client.messages.create(**kwargs)
    return _normalize_anthropic_response(response)


def _call_anthropic(config, messages: list, tools: list) -> dict:
    import anthropic
    client_kwargs = {'api_key': config.api_key, 'timeout': 120.0}
    if config.base_url:
        client_kwargs['base_url'] = config.base_url.rstrip('/')
    client = anthropic.Anthropic(**client_kwargs)
    return _call_anthropic_api(client, config.model_name, config, messages, tools)


def _call_bedrock_claude(config, messages: list, tools: list) -> dict:
    import anthropic
    client = anthropic.AnthropicBedrock(
        aws_access_key=config.aws_access_key_id,
        aws_secret_key=config.aws_secret_access_key,
        aws_region=config.aws_region or 'us-east-1',
        timeout=120.0,
    )
    return _call_anthropic_api(client, config.aws_model_id, config, messages, tools)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_llm_with_tools(messages: list, tools: list) -> dict:
    """调用 LLM，根据模型类型自动分发到对应后端。未配置模型时抛 ValueError。"""
    config = AIModelConfig.objects.filter(is_active=True, role='writer').first()
    if not config:
        raise ValueError('未找到可用的 AI 模型配置，请在"配置中心 → AI 模型配置"中添加并启用一个 writer 角色的配置。')

    if config.model_type == 'anthropic_claude':
        return _call_anthropic(config, messages, tools)
    elif config.model_type == 'bedrock_claude':
        return _call_bedrock_claude(config, messages, tools)
    else:
        return _call_openai_compatible(config, messages, tools)


class ToolDispatcher:
    """将模型返回的 tool_call 分发到对应的 Python 函数。"""

    _registry: dict = {}  # {tool_name: callable}

    @classmethod
    def register(cls, name: str, func):
        cls._registry[name] = func

    @classmethod
    def execute(cls, tool_name: str, args: dict, user, context: dict) -> dict:
        func = cls._registry.get(tool_name)
        if not func:
            return {'error': f'未知工具: {tool_name}'}
        try:
            return func(user=user, context=context, **args)
        except Exception as e:
            logger.exception('Tool %s failed', tool_name)
            return {'error': str(e)}


def run_tool_loop(messages: list, tools: list, user, context: dict) -> tuple[str, list]:
    """
    执行完整的 tool-call 循环，返回 (final_reply, tools_called_names)。
    messages 应已包含 system prompt 和本轮用户消息。
    """
    from apps.ai_assistant.tools import TOOL_DEFINITIONS  # 延迟导入避免循环

    tools_called = []

    for _ in range(MAX_TOOL_ROUNDS):
        response = call_llm_with_tools(messages, TOOL_DEFINITIONS)
        choices = response.get('choices')
        if not choices:
            logger.error('LLM 返回空 choices，响应：%s', response)
            return '模型返回异常，请稍后重试。', tools_called
        choice = choices[0]
        msg = choice['message']
        finish_reason = choice.get('finish_reason', '')

        tool_calls = msg.get('tool_calls') or []
        if finish_reason != 'tool_calls' or not tool_calls:
            return msg.get('content') or '', tools_called

        # 执行工具调用
        messages.append(msg)
        for tc in tool_calls:
            name = tc['function']['name']
            try:
                args = json.loads(tc['function']['arguments'])
            except json.JSONDecodeError:
                logger.warning('Tool %s arguments 不是合法 JSON: %s', name, tc['function'].get('arguments'))
                args = {}
            tools_called.append(name)
            result = ToolDispatcher.execute(name, args, user, context)
            messages.append({
                'role': 'tool',
                'tool_call_id': tc['id'],
                'content': json.dumps(result, ensure_ascii=False),
            })

    return '工具调用轮次超出上限，请简化您的请求后重试。', tools_called
