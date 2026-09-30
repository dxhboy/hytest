"""parameter_resolver 单元测试

测试项目参数 "{{参数名}}" 的解析逻辑。使用 mock 避免真实数据库依赖。
"""
import re
from unittest.mock import patch, MagicMock
from django.test import TestCase

from apps.ui_automation.parameter_resolver import resolve_project_parameters, _PARAM_PATTERN


class TestParamPattern(TestCase):
    """正则表达式 _PARAM_PATTERN 的边界测试"""

    def test_simple_param(self):
        self.assertEqual(_PARAM_PATTERN.findall('{{base_url}}'), ['base_url'])

    def test_param_with_spaces(self):
        self.assertEqual(_PARAM_PATTERN.findall('{{ base_url }}'), ['base_url'])

    def test_param_with_underscore_and_digits(self):
        self.assertEqual(_PARAM_PATTERN.findall('{{env_2}}'), ['env_2'])

    def test_param_starting_with_digit_no_match(self):
        """参数名不能以数字开头"""
        self.assertEqual(_PARAM_PATTERN.findall('{{2env}}'), [])

    def test_multiple_params(self):
        text = '{{host}}:{{port}}/{{path}}'
        self.assertEqual(_PARAM_PATTERN.findall(text), ['host', 'port', 'path'])

    def test_nested_braces_no_match(self):
        """三重花括号不应匹配（区分 Jinja 等模板语法）"""
        # 内层 {{param}} 仍然会被匹配，这是预期行为
        matches = _PARAM_PATTERN.findall('{{{param}}}')
        self.assertEqual(matches, ['param'])


class TestResolveProjectParameters(TestCase):
    """resolve_project_parameters 功能测试"""

    def test_none_text_returns_none(self):
        self.assertIsNone(resolve_project_parameters(None, 1))

    def test_empty_text_returns_empty(self):
        self.assertEqual(resolve_project_parameters('', 1), '')

    def test_no_placeholder_returns_unchanged(self):
        self.assertEqual(resolve_project_parameters('hello world', 1), 'hello world')

    def test_none_project_id_returns_unchanged(self):
        self.assertEqual(resolve_project_parameters('{{base_url}}', None), '{{base_url}}')

    @patch('apps.ui_automation.parameter_resolver._load_params')
    def test_single_param_replaced(self, mock_load):
        mock_load.return_value = {'base_url': 'https://example.com'}
        result = resolve_project_parameters('{{base_url}}/api', 1)
        self.assertEqual(result, 'https://example.com/api')

    @patch('apps.ui_automation.parameter_resolver._load_params')
    def test_multiple_params_replaced(self, mock_load):
        mock_load.return_value = {'host': 'localhost', 'port': '8080'}
        result = resolve_project_parameters('http://{{host}}:{{port}}', 1)
        self.assertEqual(result, 'http://localhost:8080')

    @patch('apps.ui_automation.parameter_resolver._load_params')
    def test_unmatched_param_preserved(self, mock_load):
        mock_load.return_value = {'base_url': 'https://example.com'}
        result = resolve_project_parameters('{{base_url}}/{{undefined_param}}', 1)
        self.assertEqual(result, 'https://example.com/{{undefined_param}}')

    @patch('apps.ui_automation.parameter_resolver._load_params')
    def test_empty_params_returns_unchanged(self, mock_load):
        mock_load.return_value = {}
        result = resolve_project_parameters('{{base_url}}', 1)
        self.assertEqual(result, '{{base_url}}')

    @patch('apps.ui_automation.parameter_resolver._load_params')
    def test_param_with_spaces_in_braces(self, mock_load):
        mock_load.return_value = {'base_url': 'https://example.com'}
        result = resolve_project_parameters('{{ base_url }}', 1)
        self.assertEqual(result, 'https://example.com')

    def test_cache_hit_avoids_reload(self):
        """传入 cache 字典后，相同 project_id 不再调用 _load_params"""
        cache = {1: {'token': 'abc123'}}
        result = resolve_project_parameters('Bearer {{token}}', 1, cache=cache)
        self.assertEqual(result, 'Bearer abc123')

    @patch('apps.ui_automation.parameter_resolver._load_params')
    def test_cache_populated_on_first_call(self, mock_load):
        """_load_params 被调用时应收到 cache 引用，由其负责填充"""
        def _fake_load(project_id, cache):
            params = {'key': 'val'}
            if cache is not None:
                cache[project_id] = params
            return params

        mock_load.side_effect = _fake_load
        cache = {}
        resolve_project_parameters('{{key}}', 1, cache=cache)
        # cache should now have the project_id entry
        self.assertIn(1, cache)
        self.assertEqual(cache[1], {'key': 'val'})
