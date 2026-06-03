import re

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType


@receiver(post_save, sender='requirement_analysis.TestCaseGenerationTask')
def auto_link_generated_cases(sender, instance, **kwargs):
    """
    当 Jira 导入的生成任务变为 completed 时，
    将该任务自动关联到对应的 JiraIssueLink。
    只处理 task_id 以 'jira-' 开头的任务。

    注意：GeneratedTestCase 与 TestCaseGenerationTask 之间没有 FK 关系。
    Jira 导入任务的结果存储在 TestCaseGenerationTask.final_test_cases (TextField)。
    因此本信号将 TestCaseGenerationTask 本身作为关联对象写入 JiraIssueCaseLink。
    """
    if not instance.task_id.startswith('jira-'):
        return
    if instance.status != 'completed':
        return

    from .models import JiraIssueLink, JiraIssueCaseLink

    # 从任务标题解析关联的 Issue Keys
    # 格式: "Jira 导入: PROJ-1, PROJ-2 等N个 Issue"
    keys = re.findall(r'[A-Z][A-Z0-9]+-\d+', instance.title)
    if not keys:
        return

    ct = ContentType.objects.get_for_model(sender)

    for key in keys:
        issue_link = JiraIssueLink.objects.filter(issue_key=key).first()
        if not issue_link:
            continue
        JiraIssueCaseLink.objects.get_or_create(
            jira_issue=issue_link,
            content_type=ct,
            object_id=instance.id,
            defaults={
                'link_type': JiraIssueCaseLink.LINK_AUTO,
                'created_by': instance.created_by,
            }
        )