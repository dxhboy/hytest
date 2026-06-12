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
