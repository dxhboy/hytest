# tests/test_schema_hooks.py
import pytest
from unittest.mock import MagicMock


def make_request(lang='zh-cn'):
    req = MagicMock()
    req.GET.get.side_effect = lambda key, default=None: lang if key == 'lang' else default
    return req


def make_result(*paths):
    return {'paths': {p: {'get': {}} for p in paths}}


def test_zh_tags_applied():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/projects/', '/api/testcases/')
    out = auto_tag_hook(result, None, make_request('zh-cn'), False)
    assert out['paths']['/api/projects/']['get']['tags'] == ['项目管理']
    assert out['paths']['/api/testcases/']['get']['tags'] == ['测试用例']


def test_en_tags_applied():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/projects/', '/api/testcases/')
    out = auto_tag_hook(result, None, make_request('en'), False)
    assert out['paths']['/api/projects/']['get']['tags'] == ['Projects']
    assert out['paths']['/api/testcases/']['get']['tags'] == ['Test Cases']


def test_existing_tags_not_overwritten():
    from backend.schema_hooks import auto_tag_hook
    result = {'paths': {'/api/projects/': {'get': {'tags': ['Custom']}}}}
    out = auto_tag_hook(result, None, make_request('zh-cn'), False)
    assert out['paths']['/api/projects/']['get']['tags'] == ['Custom']


def test_none_request_defaults_to_zh():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/users/')
    out = auto_tag_hook(result, None, None, False)
    assert out['paths']['/api/users/']['get']['tags'] == ['用户管理']


def test_unknown_lang_defaults_to_zh():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/executions/')
    out = auto_tag_hook(result, None, make_request('fr'), False)
    assert out['paths']['/api/executions/']['get']['tags'] == ['测试执行']


def test_api_testing_fallback():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/environments/')
    out = auto_tag_hook(result, None, make_request('zh-cn'), False)
    assert out['paths']['/api/environments/']['get']['tags'] == ['接口测试']


def test_multiple_methods_all_tagged():
    from backend.schema_hooks import auto_tag_hook
    result = {'paths': {'/api/projects/': {'get': {}, 'post': {}}}}
    out = auto_tag_hook(result, None, make_request('zh-cn'), False)
    assert out['paths']['/api/projects/']['get']['tags'] == ['项目管理']
    assert out['paths']['/api/projects/']['post']['tags'] == ['项目管理']
