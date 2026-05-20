# backend/schema_hooks.py

# 有序映射：越具体的前缀越靠前，/api/ 兜底放最后
_TAG_MAP = [
    ('/api/auth/',                 '用户认证',  'Authentication'),
    ('/api/users/',                '用户管理',  'User Management'),
    ('/api/projects/',             '项目管理',  'Projects'),
    ('/api/testcases/',            '测试用例',  'Test Cases'),
    ('/api/testsuites/',           '测试套件',  'Test Suites'),
    ('/api/executions/',           '测试执行',  'Executions'),
    ('/api/reports/',              '测试报告',  'Reports'),
    ('/api/reviews/',              '评审管理',  'Reviews'),
    ('/api/versions/',             '版本管理',  'Versions'),
    ('/api/assistant/',            'AI助手',    'AI Assistant'),
    ('/api/requirement-analysis/', '需求分析',  'Requirement Analysis'),
    ('/api/ui-automation/',        'UI自动化',  'UI Automation'),
    ('/api/data-factory/',         '数据工厂',  'Data Factory'),
    ('/api/core/',                 '核心功能',  'Core'),
    ('/api/',                      '接口测试',  'API Testing'),
]

_SUPPORTED_LANGS = {'zh-cn', 'en'}


def _get_lang(request):
    """从 request.GET 读取 lang 参数，不支持的值回落到 zh-cn。"""
    if request is None:
        return 'zh-cn'
    lang = request.GET.get('lang', 'zh-cn')
    return lang if lang in _SUPPORTED_LANGS else 'zh-cn'


def _resolve_tag(path, lang):
    """按最具体前缀匹配，返回对应语言的标签名。"""
    for prefix, zh_tag, en_tag in _TAG_MAP:
        if path.startswith(prefix):
            return zh_tag if lang == 'zh-cn' else en_tag
    return '其他' if lang == 'zh-cn' else 'Other'


def auto_tag_hook(result, generator, request, public):
    """
    drf-spectacular postprocessing hook。
    为没有 tags 的 operation 自动分配模块标签，语言由 ?lang= 参数决定。
    """
    lang = _get_lang(request)
    for path, methods in result.get('paths', {}).items():
        tag = _resolve_tag(path, lang)
        for method, operation in methods.items():
            if isinstance(operation, dict) and 'tags' not in operation:
                operation['tags'] = [tag]
    return result
