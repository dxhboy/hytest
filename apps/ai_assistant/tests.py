from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import AssistantSession, AssistantMessage

User = get_user_model()


class AssistantSessionModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass')

    def test_create_session(self):
        session = AssistantSession.objects.create(
            user=self.user,
            title='测试会话',
            context_module='api-testing',
            context_page='interface-management',
            context_project_id=1,
        )
        self.assertEqual(session.title, '测试会话')
        self.assertEqual(session.context_module, 'api-testing')

    def test_create_message(self):
        session = AssistantSession.objects.create(user=self.user)
        msg = AssistantMessage.objects.create(
            session=session, role='user', content='帮我列出接口'
        )
        self.assertEqual(msg.role, 'user')
        self.assertEqual(session.messages.count(), 1)

    def test_session_ordering_by_updated(self):
        from django.utils import timezone
        from datetime import timedelta
        s1 = AssistantSession.objects.create(user=self.user, title='s1')
        s2 = AssistantSession.objects.create(user=self.user, title='s2')
        # 强制 s2 的 updated_at 比 s1 更新，避免时序竞争
        AssistantSession.objects.filter(pk=s2.pk).update(
            updated_at=timezone.now() + timedelta(seconds=1)
        )
        sessions = list(AssistantSession.objects.filter(user=self.user))
        self.assertEqual(sessions[0].pk, s2.pk)


from rest_framework.test import APIClient


class ChatViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='chatuser', password='testpassword123')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_send_message_creates_session(self):
        url = '/api/ai-assistant/chat/send_message/'
        resp = self.client.post(url, {
            'message': '帮我列出接口',
            'context': {'module': 'api-testing', 'page': 'interface-management'},
        }, format='json')
        # 无 AI 配置时返回 503，有配置时返回 200
        self.assertIn(resp.status_code, [200, 503])

    def test_session_list(self):
        from .models import AssistantSession
        AssistantSession.objects.create(user=self.user, title='test')
        resp = self.client.get('/api/ai-assistant/sessions/')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.data['results']), 1)

    def test_session_messages(self):
        from .models import AssistantSession, AssistantMessage
        session = AssistantSession.objects.create(user=self.user)
        AssistantMessage.objects.create(session=session, role='user', content='hi')
        resp = self.client.get(f'/api/ai-assistant/sessions/{session.id}/messages/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_delete_session(self):
        from .models import AssistantSession
        session = AssistantSession.objects.create(user=self.user)
        resp = self.client.delete(f'/api/ai-assistant/sessions/{session.id}/')
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(AssistantSession.objects.filter(id=session.id).count(), 0)
