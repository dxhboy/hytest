"""接口请求断言变更 → 同步到原样复制了断言的测试套件步骤"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.api_testing.models import ApiCollection, ApiProject, ApiRequest, TestSuite, TestSuiteRequest

User = get_user_model()

OLD = [{'type': 'status_code', 'expected': 200}]
NEW = [{'type': 'status_code', 'expected': 201}]


class SuiteAssertionSyncTest(TestCase):
    def setUp(self):
        user = User.objects.create_user(username='sync', password='pw')
        project = ApiProject.objects.create(
            name='p', project_type='HTTP', status='IN_PROGRESS', owner=user,
        )
        collection = ApiCollection.objects.create(name='c', project=project)
        self.request = ApiRequest.objects.create(
            name='r', url='http://x', collection=collection, assertions=OLD, created_by=user,
        )
        self.suite = TestSuite.objects.create(name='s', project=project, created_by=user)
        self.suite2 = TestSuite.objects.create(name='s2', project=project, created_by=user)
        self.suite3 = TestSuite.objects.create(name='s3', project=project, created_by=user)

    def step(self, suite, assertions):
        return TestSuiteRequest.objects.create(test_suite=suite, request=self.request, assertions=assertions)

    def change_assertions(self, value):
        self.request.assertions = value
        self.request.save()

    def test_copied_step_follows_source(self):
        copied = self.step(self.suite, list(OLD))
        self.change_assertions(NEW)
        copied.refresh_from_db()
        self.assertEqual(copied.assertions, NEW)

    def test_customized_and_empty_steps_untouched(self):
        custom = [{'type': 'status_code', 'expected': 404}]
        customized = self.step(self.suite, custom)
        empty = self.step(self.suite2, [])
        self.change_assertions(NEW)
        customized.refresh_from_db()
        empty.refresh_from_db()
        self.assertEqual(customized.assertions, custom)
        self.assertEqual(empty.assertions, [])

    def test_other_field_changes_do_not_sync(self):
        copied = self.step(self.suite, list(OLD))
        self.request.name = 'renamed'
        self.request.save(update_fields=['name'])
        copied.refresh_from_db()
        self.assertEqual(copied.assertions, OLD)

    def test_sequential_edits_keep_following(self):
        copied = self.step(self.suite3, list(OLD))
        self.change_assertions(NEW)
        newest = [{'type': 'status_code', 'expected': 202}]
        self.change_assertions(newest)
        copied.refresh_from_db()
        self.assertEqual(copied.assertions, newest)

    @override_settings(API_SUITE_ASSERTION_SYNC=False)
    def test_switch_off(self):
        copied = self.step(self.suite, list(OLD))
        self.change_assertions(NEW)
        copied.refresh_from_db()
        self.assertEqual(copied.assertions, OLD)
