"""录制 REST API 集成测试"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.ui_automation.models import UiProject, RecordingSession, LocatorStrategy

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='recorder', password='test1234')


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def project(db, user):
    # 注意：UiProject 用 owner 而非 created_by
    return UiProject.objects.create(name='RecordProject', owner=user)


@pytest.fixture
def css_strategy(db):
    # 注意：LocatorStrategy 只有 name 和 description
    return LocatorStrategy.objects.create(name='css', description='CSS Selector')


class TestStartRecording:
    def test_start_returns_session_and_ws_path(self, client, project):
        resp = client.post('/api/ui-automation/recording/start/', {
            'project_id': project.id,
            'target_url': 'https://example.com',
        }, format='json')
        assert resp.status_code == 201
        assert 'session_id' in resp.data
        assert '/ws/ui-automation/recording/' in resp.data['ws_path']

    def test_start_with_invalid_project(self, client):
        resp = client.post('/api/ui-automation/recording/start/', {
            'project_id': 99999,
            'target_url': 'https://example.com',
        }, format='json')
        assert resp.status_code == 404


class TestConfirmRecording:
    def test_confirm_creates_test_case(self, client, project, css_strategy, user):
        session = RecordingSession.objects.create(
            project=project,
            target_url='https://example.com',
            status='confirming',
            recorded_steps=[{
                'step_number': 1,
                'action_type': 'click',
                'page_url': 'https://example.com/login',
                'element_info': {
                    'element_type': 'BUTTON',
                    'element_name': '登录',
                    'locators': [{'strategy': 'css', 'value': '#login'}],
                },
            }],
            match_results=[{
                'step_number': 1,
                'status': 'created',
                'element_id': None,
                'action_type': 'click',
                'element_info': {
                    'element_type': 'BUTTON',
                    'element_name': '登录',
                    'locators': [{'strategy': 'css', 'value': '#login'}],
                },
            }],
            created_by=user,
        )
        resp = client.post(f'/api/ui-automation/recording/{session.id}/confirm/', {
            'test_case_name': '录制测试-登录流程',
            'steps': session.match_results,
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['test_case_name'] == '录制测试-登录流程'
        assert resp.data['step_count'] == 1


class TestCancelRecording:
    def test_cancel_updates_status(self, client, project, user):
        session = RecordingSession.objects.create(
            project=project,
            target_url='https://example.com',
            status='recording',
            created_by=user,
        )
        resp = client.post(f'/api/ui-automation/recording/{session.id}/cancel/')
        assert resp.status_code == 200
        assert resp.data['status'] == 'cancelled'
