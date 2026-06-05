import asyncio
import logging
import threading
import uuid

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .jira_client import JiraClient, JiraClientError
from .jira_serializers import (
    JiraPreviewRequestSerializer, JiraImportRequestSerializer,
    JiraIssueLinkSerializer, LinkCaseRequestSerializer,
    JiraRecommendRequestSerializer,
)
from .models import (
    JiraIssueLink, JiraIssueCaseLink,
    TestCaseGenerationTask, AIModelConfig, AIModelService,
    GenerationConfig,
)

logger = logging.getLogger(__name__)


def _get_jira_client(user):
    from apps.users.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not (profile.jira_domain and profile.jira_email and profile.jira_api_token):
        raise ValueError('Jira 凭据未配置，请在个人资料页 Jira 配置 Tab 填写')
    f = Fernet(settings.JIRA_TOKEN_ENCRYPT_KEY)
    try:
        token = f.decrypt(profile.jira_api_token.encode()).decode()
    except (InvalidToken, Exception):
        raise ValueError('Jira API Token 解密失败，请重新保存 Token')
    return JiraClient(domain=profile.jira_domain, email=profile.jira_email, api_token=token)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def jira_validate_connection(request):
    try:
        client = _get_jira_client(request.user)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    ok = client.validate_connection()
    if ok:
        return Response({'valid': True, 'message': '连接成功'})
    return Response(
        {'valid': False, 'message': '连接失败，请检查域名、邮箱和 API Token'},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def jira_preview(request):
    ser = JiraPreviewRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    try:
        client = _get_jira_client(request.user)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    results = []
    for url in data['urls']:
        issue_key = JiraClient.issue_key_from_url(url)
        if not issue_key:
            results.append({'url': url, 'success': False, 'error': 'URL 格式无效，无法解析 Issue Key'})
            continue
        try:
            issue = client.get_issue(issue_key, fields=data['selected_fields'])
            content = client.extract_content(issue, selected_fields=data['selected_fields'])
            results.append({
                'url': url,
                'issue_key': issue_key,
                'summary': issue['fields'].get('summary', ''),
                'content_preview': content[:300],
                'success': True,
            })
        except JiraClientError as e:
            results.append({'url': url, 'issue_key': issue_key, 'success': False, 'error': str(e)})

    return Response({'results': results})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def jira_import(request):
    ser = JiraImportRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    try:
        client = _get_jira_client(request.user)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    issue_keys = []
    for url in data['urls']:
        key = JiraClient.issue_key_from_url(url)
        if not key:
            continue
        if data.get('expand_epic'):
            try:
                children = client.get_epic_children(key, fields=data['selected_fields'])
                issue_keys.extend([c['key'] for c in children])
            except JiraClientError:
                issue_keys.append(key)
        else:
            issue_keys.append(key)

    if not issue_keys:
        return Response({'error': '未能解析任何有效的 Issue Key'}, status=status.HTTP_400_BAD_REQUEST)

    requirement_parts = []
    issue_metas = []
    domain = _get_profile_domain(request.user)
    for key in issue_keys:
        try:
            issue = client.get_issue(key, fields=data['selected_fields'])
            content = client.extract_content(issue, selected_fields=data['selected_fields'])
            requirement_parts.append(content)
            issue_metas.append({
                'key': key,
                'url': f'https://{domain}/browse/{key}',
                'summary': issue['fields'].get('summary', key),
                'fix_version': _extract_fix_version(issue),
            })
        except JiraClientError:
            continue

    if not requirement_parts:
        return Response({'error': '所有 Issue 拉取失败'}, status=status.HTTP_400_BAD_REQUEST)

    requirement_text = '\n\n---\n\n'.join(requirement_parts)

    writer_config = _get_ai_config(data.get('writer_model_config_id'), 'writer')
    reviewer_config = _get_ai_config(data.get('reviewer_model_config_id'), 'reviewer')

    from apps.users.models import UserProfile
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    version = None
    if data.get('version_id'):
        from apps.versions.models import Version
        version = Version.objects.filter(id=data['version_id']).first()
    project = None
    if data.get('project_id'):
        from apps.projects.models import Project
        project = Project.objects.filter(id=data['project_id']).first()

    task = TestCaseGenerationTask.objects.create(
        task_id=f'jira-{uuid.uuid4().hex[:12]}',
        title='Jira 导入: ' + ', '.join(m['key'] for m in issue_metas[:3]) +
              (f' 等{len(issue_metas)}个 Issue' if len(issue_metas) > 3 else ''),
        requirement_text=requirement_text,
        status='pending',
        writer_model_config=writer_config,
        reviewer_model_config=reviewer_config,
        created_by=request.user,
        project=project,
    )

    _trigger_task_generation(task)

    for meta in issue_metas:
        JiraIssueLink.objects.update_or_create(
            issue_key=meta['key'],
            jira_domain=profile.jira_domain,
            defaults={
                'issue_url': meta['url'],
                'issue_summary': meta['summary'],
                'jira_fix_version': meta['fix_version'],
                'version': version,
                'project': project,
                'created_by': request.user,
            }
        )

    return Response({
        'task_id': task.task_id,
        'message': f'已为 {len(issue_metas)} 个 Issue 创建生成任务',
        'issue_count': len(issue_metas),
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def jira_issues_list(request):
    project_id = request.query_params.get('project_id')
    version_id = request.query_params.get('version_id')
    qs = JiraIssueLink.objects.filter(created_by=request.user)
    if project_id:
        qs = qs.filter(project_id=project_id)
    if version_id:
        qs = qs.filter(version_id=version_id)
    ser = JiraIssueLinkSerializer(qs, many=True)
    return Response(ser.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def jira_link_cases(request, issue_id):
    issue = JiraIssueLink.objects.filter(id=issue_id).first()
    if not issue:
        return Response({'error': 'Issue 不存在'}, status=status.HTTP_404_NOT_FOUND)
    ser = LinkCaseRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    if data['case_type'] == 'generated':
        from apps.requirement_analysis.models import GeneratedTestCase as CaseModel
    else:
        from apps.testcases.models import TestCase as CaseModel

    ct = ContentType.objects.get_for_model(CaseModel)
    created_count = 0
    for case_id in data['case_ids']:
        _, created = JiraIssueCaseLink.objects.get_or_create(
            jira_issue=issue, content_type=ct, object_id=case_id,
            defaults={'link_type': JiraIssueCaseLink.LINK_MANUAL, 'created_by': request.user}
        )
        if created:
            created_count += 1
    return Response({'linked': created_count})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def jira_unlink_cases(request, issue_id):
    ser = LinkCaseRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    if data['case_type'] == 'generated':
        from apps.requirement_analysis.models import GeneratedTestCase as CaseModel
    else:
        from apps.testcases.models import TestCase as CaseModel

    ct = ContentType.objects.get_for_model(CaseModel)
    deleted, _ = JiraIssueCaseLink.objects.filter(
        jira_issue_id=issue_id, content_type=ct, object_id__in=data['case_ids']
    ).delete()
    return Response({'unlinked': deleted})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def jira_issue_cases(request, issue_id):
    links = JiraIssueCaseLink.objects.filter(jira_issue_id=issue_id).select_related('content_type')
    results = []
    for link in links:
        obj = link.case
        if obj is None:
            continue
        results.append({
            'id': link.object_id,
            'case_type': link.content_type.model,
            'link_type': link.link_type,
            'title': getattr(obj, 'title', getattr(obj, 'name', str(obj))),
        })
    return Response({'results': results})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def jira_recommend(request):
    ser = JiraRecommendRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    version_id = ser.validated_data['version_id']

    issues = JiraIssueLink.objects.filter(version_id=version_id).prefetch_related('case_links')
    seen = set()
    results = []
    for issue in issues:
        for link in issue.case_links.all():
            key = (link.content_type_id, link.object_id)
            if key in seen:
                continue
            seen.add(key)
            obj = link.case
            if obj is None:
                continue
            results.append({
                'id': link.object_id,
                'case_type': link.content_type.model,
                'title': getattr(obj, 'title', getattr(obj, 'name', str(obj))),
                'source_issue': issue.issue_key,
                'link_type': link.link_type,
            })
    return Response({'version_id': version_id, 'count': len(results), 'results': results})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_profile_domain(user):
    from apps.users.models import UserProfile
    profile = UserProfile.objects.filter(user=user).first()
    return profile.jira_domain if profile else ''


def _extract_fix_version(issue: dict) -> str:
    fix_versions = issue.get('fields', {}).get('fixVersions', [])
    if fix_versions:
        return fix_versions[0].get('name', '')
    return ''


def _get_ai_config(config_id, role: str):
    if config_id:
        return AIModelConfig.objects.filter(id=config_id).first()
    return AIModelConfig.objects.filter(role=role, is_active=True).first()


def _trigger_task_generation(task: TestCaseGenerationTask):
    """
    触发 AI 生成任务。

    复用与 TestCaseGenerationTaskViewSet.generate 相同的机制：
    daemon threading.Thread + asyncio.new_event_loop()。
    """
    from asgiref.sync import sync_to_async
    from django.utils import timezone

    gen_config = GenerationConfig.get_active_config()
    enable_auto_review = gen_config.enable_auto_review if gen_config else True

    def execute_task():
        try:
            task.status = 'generating'
            task.progress = 10
            task.save()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if task.output_mode == 'stream':
                    task.stream_buffer = ''
                    task.stream_position = 0
                    task.save()

                    def save_stream_buffer(content):
                        task.stream_buffer = content
                        task.stream_position = len(content)
                        task.last_stream_update = timezone.now()
                        task.save(update_fields=['stream_buffer', 'stream_position', 'last_stream_update'])

                    async_save_stream = sync_to_async(save_stream_buffer)

                    async def stream_callback(chunk):
                        task.stream_buffer += chunk
                        task.stream_position = len(task.stream_buffer)
                        task.last_stream_update = timezone.now()
                        if task.stream_position % 500 < 20 or len(chunk) > 100:
                            try:
                                await async_save_stream(task.stream_buffer)
                            except Exception as save_err:
                                logger.warning(f'保存流式内容失败: {save_err}')

                    task.progress = 30
                    task.save()
                    generated_cases = loop.run_until_complete(
                        AIModelService.generate_test_cases_stream(task, callback=stream_callback)
                    )
                    if task.stream_buffer:
                        save_stream_buffer(task.stream_buffer)
                    task.generated_test_cases = generated_cases
                    task.progress = 60
                    task.save()
                else:
                    loop.run_until_complete(AIModelService.generate_test_cases(task))
                    task.progress = 60
                    task.save()
                    generated_cases = task.generated_test_cases

                if (enable_auto_review
                        and task.reviewer_model_config
                        and task.reviewer_prompt_config):
                    task.status = 'reviewing'
                    task.progress = 70
                    task.save()
                    if task.output_mode == 'stream':
                        loop.run_until_complete(
                            AIModelService.review_test_cases_stream(task, generated_cases, None)
                        )
                    else:
                        loop.run_until_complete(
                            AIModelService.review_test_cases(task, generated_cases)
                        )
                    task.progress = 85
                    task.save()

                    task.status = 'revising'
                    task.save()
                    loop.run_until_complete(
                        AIModelService.revise_test_cases_based_on_review(task)
                    )

                task.status = 'completed'
                task.progress = 100
                task.completed_at = timezone.now()
                task.save()
            finally:
                loop.close()
        except Exception as exc:
            logger.error(f'Jira 生成任务 {task.task_id} 失败: {exc}')
            task.status = 'failed'
            task.error_message = str(exc)
            task.save()

    thread = threading.Thread(target=execute_task, daemon=True)
    thread.start()
