"""ElementMatcher 三层匹配逻辑单元测试"""
import pytest
from django.contrib.auth import get_user_model
from apps.ui_automation.models import (
    UiProject, Element, LocatorStrategy, ElementGroup,
)
from apps.ui_automation.recording.element_matcher import ElementMatcher

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='tester', password='test1234')


@pytest.fixture
def project(db, user):
    return UiProject.objects.create(name='TestProject', owner=user)


@pytest.fixture
def css_strategy(db):
    return LocatorStrategy.objects.create(name='css', description='CSS Selector')


@pytest.fixture
def text_strategy(db):
    return LocatorStrategy.objects.create(name='text', description='Text')


@pytest.fixture
def existing_element(db, project, css_strategy, user):
    """元素库中已有的元素：登录按钮，css定位"""
    return Element.objects.create(
        project=project,
        name='登录按钮',
        element_type='BUTTON',
        locator_strategy=css_strategy,
        locator_value='#login-btn',
        page='/login',
        created_by=user,
    )


class TestElementMatcherExact:
    """第1层：精确匹配 — 定位器完全一致时直接复用"""

    def test_exact_match_reuses_element(self, project, existing_element, user):
        steps = [{
            'step_number': 1,
            'action_type': 'click',
            'page_url': 'https://example.com/login',
            'element_info': {
                'element_type': 'BUTTON',
                'element_name': '登录按钮',
                'locators': [
                    {'strategy': 'css', 'value': '#login-btn'},
                    {'strategy': 'text', 'value': '登录'},
                ],
            },
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert len(results) == 1
        assert results[0]['status'] == 'reused'
        assert results[0]['element_id'] == existing_element.id

    def test_exact_match_via_backup_locator(self, project, existing_element, css_strategy, user):
        """备用定位器也能命中精确匹配"""
        existing_element.backup_locators = [{'strategy': 'text', 'value': '登录'}]
        existing_element.save()

        steps = [{
            'step_number': 1,
            'action_type': 'click',
            'page_url': 'https://example.com/login',
            'element_info': {
                'element_type': 'BUTTON',
                'element_name': '登录按钮',
                'locators': [{'strategy': 'text', 'value': '登录'}],
            },
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert results[0]['status'] == 'reused'


class TestElementMatcherFuzzy:
    """第2层：模糊匹配 — 元素变更但可识别，更新定位器"""

    def test_fuzzy_match_updates_locator(self, project, existing_element, css_strategy, user):
        """同页面、同 test-id → 定位器变了 → 更新"""
        existing_element.backup_locators = [{'strategy': 'test-id', 'value': 'login-btn'}]
        existing_element.save()

        steps = [{
            'step_number': 1,
            'action_type': 'click',
            'page_url': 'https://example.com/login',
            'element_info': {
                'element_type': 'BUTTON',
                'element_name': '登录按钮',
                'locators': [
                    {'strategy': 'test-id', 'value': 'login-btn'},
                    {'strategy': 'css', 'value': '#new-login-btn'},
                ],
            },
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert results[0]['status'] == 'updated'
        assert results[0]['element_id'] == existing_element.id


class TestElementMatcherNew:
    """第3层：无匹配 — 创建新元素"""

    def test_no_match_creates_new(self, project, css_strategy, user):
        steps = [{
            'step_number': 1,
            'action_type': 'click',
            'page_url': 'https://example.com/register',
            'element_info': {
                'element_type': 'BUTTON',
                'element_name': '注册按钮',
                'locators': [{'strategy': 'css', 'value': '#register-btn'}],
            },
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert results[0]['status'] == 'created'
        assert results[0]['element_name'] == '注册按钮'


class TestElementMatcherNoElement:
    """操作没有关联元素（如 wait、screenshot）"""

    def test_step_without_element(self, project, user):
        steps = [{
            'step_number': 1,
            'action_type': 'wait',
            'page_url': 'https://example.com/',
            'element_info': None,
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert results[0]['status'] == 'no_element'
