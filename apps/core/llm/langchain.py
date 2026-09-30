"""
LangChain ChatOpenAI 参数映射（browser-use 依赖 LangChain，不能换成 LLMClient）

这里只负责 config → ChatOpenAI kwargs 的转换，不在模块级导入 langchain，
避免未安装 langchain 的环境导入 apps.core.llm 时报错。
"""
import logging
from typing import Optional

from .config import LLMConfig

logger = logging.getLogger(__name__)

# 特殊模型强制 temperature：{'模型名称关键字': temperature值}，按顺序匹配
SPECIAL_MODEL_TEMPERATURE = {
    'kimi-2.5': 1.0,  # Moonshot AI Kimi 2.5 只支持 temperature=1
    'kimi-k2.5': 1.0,  # Moonshot AI Kimi K2.5 只支持 temperature=1
    'kimi': 1.0,  # 通用Kimi模型匹配（兜底）
}


def resolve_temperature(model_name: Optional[str], configured: Optional[float], default: float = 0.0) -> float:
    """特殊模型优先；否则使用配置值；都没有则用默认值"""
    model_name_lower = (model_name or '').lower()
    for keyword, temp in SPECIAL_MODEL_TEMPERATURE.items():
        if keyword in model_name_lower:
            logger.info(f"检测到特殊模型 '{model_name}'，使用强制 temperature={temp}")
            return temp
    if configured is not None:
        logger.info(f"使用配置的 temperature={configured}")
        return configured
    logger.info(f"使用默认 temperature={default}")
    return default


def chat_openai_kwargs(config, default_temperature: float = 0.0) -> dict:
    """
    把配置转换为 langchain_openai.ChatOpenAI 的构造参数
    （ChatOpenAI 会自行拼接 /chat/completions，所以这里只解析 base_url 默认值）
    """
    cfg = LLMConfig.from_obj(config)
    return {
        'model': cfg.model_name,
        'api_key': cfg.api_key,
        'base_url': cfg.resolved_base_url,
        'temperature': resolve_temperature(cfg.model_name, cfg.temperature, default_temperature),
    }
