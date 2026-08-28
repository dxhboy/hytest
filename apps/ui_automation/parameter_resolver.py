"""
项目参数解析
============

按项目管理的一组扁平键值对（见 models.UiProjectParameter），测试步骤的输入值/
断言值、项目的 base_url 里填 "{{参数名}}" 引用，执行时用这里的 resolve_project_
parameters() 现查数据库替换成真实值。

跟 apps/core/variable_resolver.py 的关系：那套 "{{var}}" 运行时变量机制靠一个
进程级全局单例（模块级 `_resolver = VariableResolver()`）保存 runtime_variables，
所有请求/所有并发执行共享同一份状态——如果拿它来放项目参数，两个用户同时调试执行
不同项目的用例，会互相看到对方项目的参数值（甚至互相覆盖）。这里故意不基于它，
每次解析都直接查 UiProjectParameter 表，不维护任何跨请求共享的可变状态，天然没有
这个并发串数据的问题。

两套 "{{...}}" 语法长得一样，但互不冲突：这里只替换"确实是当前项目定义过的参数名"，
没匹配上的 token（比如以后 apps.core 那套运行时变量真的在 UI 自动化里用起来了）
原样保留，留给后续 resolve_variables() 那一遍去处理。调用顺序建议是：先
resolve_project_parameters()，再 resolve_variables()。
"""
import re

_PARAM_PATTERN = re.compile(r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}')


def resolve_project_parameters(text, project_id, cache=None, overrides=None):
    """把 text 里的 "{{参数名}}" 替换成对应的参数值。

    解析优先级: overrides > 项目参数 (UiProjectParameter)。

    Args:
        text: 待解析的原始文本。
        project_id: 归属项目 id。
        cache: 可选，批量执行时复用的缓存 dict。
        overrides: 可选，额外的键值对 dict，优先于项目参数；
            典型用法是把 step_parameters 与 case_parameters 合并后传入，
            step 层的同名 key 会覆盖 case 层（调用方负责合并顺序）。

    Returns:
        替换后的文本。找不到对应参数的 "{{name}}" 原样保留。
    """
    if not text or '{{' not in text:
        return text

    # 即使 project_id 为 None，只要有 overrides 也能解析
    params = _load_params(project_id, cache) if project_id is not None else {}

    if overrides:
        params = {**params, **overrides}

    if not params:
        return text

    def _replace(match):
        name = match.group(1)
        return params.get(name, match.group(0))

    return _PARAM_PATTERN.sub(_replace, text)


def _load_params(project_id, cache):
    if cache is not None and project_id in cache:
        return cache[project_id]

    # 延迟导入，避免 parameter_resolver 模块在 Django app 还没注册好模型的阶段
    # 被别的模块提前 import 时报错
    from .models import UiProjectParameter

    params = dict(
        UiProjectParameter.objects.filter(project_id=project_id).values_list('name', 'value')
    )
    if cache is not None:
        cache[project_id] = params
    return params
