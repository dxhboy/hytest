"""
LLM 配置归一化：把各模块不同的配置模型（AIModelConfig / AIServiceConfig / dict）
统一转换为 LLMConfig，并集中维护各厂商默认 Base URL 与 URL 拼接规则。
"""
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# 各厂商默认 Base URL（与前端 AIModelConfig.vue / AIIntelligentModeConfig.vue 保持一致）
PROVIDER_DEFAULT_BASE_URLS = {
    'openai': 'https://api.openai.com/v1',
    'siliconflow': 'https://api.siliconflow.cn/v1',
    'deepseek': 'https://api.deepseek.com',
    'anthropic': 'https://api.anthropic.com',
    'anthropic_claude': 'https://api.anthropic.com',
    'qwen': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'zhipu': 'https://open.bigmodel.cn/api/paas/v4',
}

# 走 AWS Bedrock（boto3）而非 HTTP 的 provider
BEDROCK_PROVIDERS = {'bedrock_claude'}

_VERSION_SUFFIX_RE = re.compile(r'/v(\d+)/?$')


def resolve_base_url(provider: Optional[str], base_url: Optional[str]) -> Optional[str]:
    """base_url 为空时按 provider 回退到默认地址；都没有则返回 None。"""
    if base_url:
        return base_url
    return PROVIDER_DEFAULT_BASE_URLS.get(provider or '')


def build_chat_url(base_url: str, auto_version: bool = True) -> str:
    """
    拼接 chat/completions 地址

    Args:
        base_url: 用户配置的 Base URL
        auto_version: True 时若 base_url 未以 /vN 结尾则自动补 /v1（原 AIModelService 规则）；
                      False 时直接拼接 /chat/completions（原配置中心测试连接规则）
    """
    base_url = base_url.rstrip('/')
    if base_url.endswith('/chat/completions'):
        return base_url
    if not auto_version or _VERSION_SUFFIX_RE.search(base_url):
        return f'{base_url}/chat/completions'
    return f'{base_url}/v1/chat/completions'


def build_headers(api_key: Optional[str]) -> dict:
    return {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }


@dataclass
class LLMConfig:
    """统一的 LLM 配置"""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    provider: str = 'openai'
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    # 原始配置对象（Bedrock 适配器需要 aws_* 字段）
    source: Any = field(default=None, repr=False)

    @property
    def is_bedrock(self) -> bool:
        return self.provider in BEDROCK_PROVIDERS

    @property
    def resolved_base_url(self) -> Optional[str]:
        return resolve_base_url(self.provider, self.base_url)

    @classmethod
    def from_obj(cls, obj) -> 'LLMConfig':
        """
        从配置对象或 dict 构建。provider 依次取 provider / model_type / service_type。
        """
        if isinstance(obj, LLMConfig):
            return obj
        if isinstance(obj, dict):
            get = obj.get
        else:
            def get(name, default=None):
                return getattr(obj, name, default)
        provider = 'openai'
        for key in ('model_type', 'service_type', 'provider'):
            value = get(key)
            if isinstance(value, str) and value:
                provider = value
                break
        return cls(
            api_key=get('api_key'),
            base_url=get('base_url'),
            model_name=get('model_name'),
            provider=provider,
            max_tokens=get('max_tokens'),
            temperature=get('temperature'),
            top_p=get('top_p'),
            source=obj,
        )
