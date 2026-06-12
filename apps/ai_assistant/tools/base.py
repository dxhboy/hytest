import json
import logging
import httpx
from apps.requirement_analysis.models import AIModelConfig

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


def _build_llm_url(base_url: str) -> str:
    base_url = base_url.rstrip('/')
    if base_url.endswith('/chat/completions'):
        return base_url
    if base_url.endswith('/v1'):
        return f'{base_url}/chat/completions'
    return f'{base_url}/v1/chat/completions'


def call_llm_with_tools(messages: list, tools: list) -> dict:
    """调用 OpenAI-compatible API，返回原始响应 dict。未配置模型时抛 ValueError。"""
    config = AIModelConfig.objects.filter(is_active=True, role='writer').first()
    if not config:
        raise ValueError('未找到可用的 AI 模型配置，请在"配置中心 → AI 模型配置"中添加并启用一个 writer 角色的配置。')

    url = _build_llm_url(config.base_url)
    headers = {'Authorization': f'Bearer {config.api_key}', 'Content-Type': 'application/json'}
    payload = {
        'model': config.model_name,
        'messages': messages,
        'max_tokens': config.max_tokens,
        'temperature': config.temperature,
        'tools': tools,
        'tool_choice': 'auto',
    }
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


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
        choice = response['choices'][0]
        msg = choice['message']
        finish_reason = choice.get('finish_reason', '')

        if finish_reason != 'tool_calls':
            return msg.get('content') or '', tools_called

        # 执行工具调用
        messages.append(msg)
        for tc in msg.get('tool_calls', []):
            name = tc['function']['name']
            args = json.loads(tc['function']['arguments'])
            tools_called.append(name)
            result = ToolDispatcher.execute(name, args, user, context)
            messages.append({
                'role': 'tool',
                'tool_call_id': tc['id'],
                'content': json.dumps(result, ensure_ascii=False),
            })

    return '工具调用轮次超出上限，请简化您的请求后重试。', tools_called
