"""test_executor 辅助函数的单元测试

测试 _StepAttrView（字典到属性访问的适配器）和 _build_step_result（引擎返回值到
历史格式的适配器）。这两个是纯数据转换，不依赖浏览器或数据库。
"""
from django.test import TestCase

from apps.ui_automation.test_executor import _StepAttrView, _build_step_result


class TestStepAttrView(TestCase):
    """_StepAttrView 字典适配器测试"""

    def test_all_fields_mapped(self):
        data = {
            'action_type': 'click',
            'input_value': 'hello',
            'wait_time': 5000,
            'assert_type': 'textContains',
            'assert_value': 'expected',
        }
        view = _StepAttrView(data)
        self.assertEqual(view.action_type, 'click')
        self.assertEqual(view.input_value, 'hello')
        self.assertEqual(view.wait_time, 5000)
        self.assertEqual(view.assert_type, 'textContains')
        self.assertEqual(view.assert_value, 'expected')

    def test_missing_fields_default_to_none(self):
        view = _StepAttrView({})
        self.assertIsNone(view.action_type)
        self.assertIsNone(view.input_value)
        self.assertIsNone(view.wait_time)
        self.assertIsNone(view.assert_type)
        self.assertIsNone(view.assert_value)

    def test_partial_fields(self):
        view = _StepAttrView({'action_type': 'fill', 'input_value': 'text'})
        self.assertEqual(view.action_type, 'fill')
        self.assertEqual(view.input_value, 'text')
        self.assertIsNone(view.wait_time)

    def test_extra_fields_ignored(self):
        """字典中多余的字段不应导致报错"""
        view = _StepAttrView({
            'action_type': 'click',
            'extra_field': 'should_be_ignored',
            'id': 42,
        })
        self.assertEqual(view.action_type, 'click')
        self.assertFalse(hasattr(view, 'extra_field'))


class TestBuildStepResult(TestCase):
    """_build_step_result 格式适配测试"""

    def _make_step_data(self, **overrides):
        base = {
            'step_number': 1,
            'action_type': 'click',
            'description': '点击登录按钮',
        }
        base.update(overrides)
        return base

    def test_success_result(self):
        step_data = self._make_step_data()
        result = _build_step_result(step_data, True, '点击成功')
        self.assertTrue(result['success'])
        self.assertEqual(result['step_number'], 1)
        self.assertEqual(result['action_type'], 'click')
        self.assertEqual(result['description'], '点击登录按钮')
        self.assertEqual(result['log'], '点击成功')
        self.assertIsNone(result['error'])
        self.assertNotIn('screenshot', result)

    def test_failure_result(self):
        step_data = self._make_step_data()
        result = _build_step_result(step_data, False, '元素未找到')
        self.assertFalse(result['success'])
        self.assertEqual(result['error'], '元素未找到')
        self.assertEqual(result['log'], '元素未找到')

    def test_with_screenshot(self):
        step_data = self._make_step_data()
        result = _build_step_result(step_data, False, '失败', 'data:image/png;base64,abc123')
        self.assertEqual(result['screenshot'], 'data:image/png;base64,abc123')

    def test_success_has_no_error(self):
        step_data = self._make_step_data()
        result = _build_step_result(step_data, True, '成功日志')
        self.assertIsNone(result['error'])

    def test_no_screenshot_key_when_none(self):
        step_data = self._make_step_data()
        result = _build_step_result(step_data, True, 'ok', None)
        self.assertNotIn('screenshot', result)
