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
        s1 = AssistantSession.objects.create(user=self.user, title='s1')
        s2 = AssistantSession.objects.create(user=self.user, title='s2')
        sessions = list(AssistantSession.objects.filter(user=self.user))
        self.assertEqual(sessions[0].id, s2.id)
