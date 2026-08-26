"""
录制功能 REST API 视图。

提供录制会话的创建、停止、匹配结果查看、确认保存和取消等操作。
"""
import logging
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    RecordingSession, UiProject, TestCase, TestCaseStep,
    Element, LocatorStrategy, ElementGroup,
)
from .recording_serializers import (
    StartRecordingSerializer, RecordingSessionSerializer, ConfirmRecordingSerializer,
)
from .recording.element_matcher import ElementMatcher

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_recording(request):
    """创建录制会话，返回 session_id 和 WebSocket 地址"""
    ser = StartRecordingSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    data = ser.validated_data
    project = UiProject.objects.filter(id=data['project_id']).first()
    if not project:
        return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

    session = RecordingSession.objects.create(
        project=project,
        target_url=data['target_url'],
        viewport_width=data.get('viewport_width', 1280),
        viewport_height=data.get('viewport_height', 720),
        created_by=request.user,
    )

    # 构建 WebSocket 地址（前端根据当前 host 拼接）
    ws_path = f'/ws/ui-automation/recording/{session.id}/'

    return Response({
        'session_id': session.id,
        'ws_path': ws_path,
        'status': session.status,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_recording(request, session_id):
    """停止录制，触发元素匹配"""
    session = RecordingSession.objects.filter(
        id=session_id, created_by=request.user
    ).first()
    if not session:
        return Response({'error': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)
    if session.status not in ('recording', 'matching'):
        return Response({'error': f'会话状态不允许此操作: {session.status}'}, status=status.HTTP_400_BAD_REQUEST)

    # 执行元素匹配
    matcher = ElementMatcher(session.project_id, request.user)
    match_results = matcher.match_all(session.recorded_steps)

    session.match_results = match_results
    session.status = 'confirming'
    session.finished_at = timezone.now()
    session.save()

    return Response({
        'session_id': session.id,
        'status': session.status,
        'match_results': match_results,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_match_results(request, session_id):
    """获取元素匹配结果供前端确认"""
    session = RecordingSession.objects.filter(
        id=session_id, created_by=request.user
    ).first()
    if not session:
        return Response({'error': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'session_id': session.id,
        'status': session.status,
        'recorded_steps': session.recorded_steps,
        'match_results': session.match_results,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_recording(request, session_id):
    """确认录制结果，保存为 TestCase + TestCaseSteps + 元素变更"""
    session = RecordingSession.objects.filter(
        id=session_id, created_by=request.user, status='confirming'
    ).first()
    if not session:
        return Response({'error': '会话不存在或状态不正确'}, status=status.HTTP_404_NOT_FOUND)

    ser = ConfirmRecordingSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    data = ser.validated_data
    confirmed_steps = data['steps']

    # 创建测试用例（注意：status 用 'draft' 而非 'active'，因为 TestCase.STATUS_CHOICES 没有 'active'）
    test_case = TestCase.objects.create(
        project=session.project,
        name=data['test_case_name'],
        description=f'由脚本录制自动生成，目标URL: {session.target_url}',
        status='draft',
        created_by=request.user,
    )

    # 逐步骤创建 TestCaseStep 并处理元素
    for step_data in confirmed_steps:
        element = None
        match_status = step_data.get('status', '')

        if match_status == 'reused':
            # 复用的元素 — 直接关联，无需变更
            element_id = step_data.get('element_id')
            if element_id:
                element = Element.objects.filter(id=element_id).first()

        elif match_status == 'updated':
            # 匹配阶段是 dry_run，只预览了 changes，并未写库。
            # 用户在此确认保存后，才真正把录制时检测到的定位器更新落库。
            element_id = step_data.get('element_id')
            if element_id:
                element = Element.objects.filter(id=element_id).first()
                if element and step_data.get('element_info'):
                    _apply_locator_update(element, step_data['element_info'].get('locators', []))

        elif match_status == 'created':
            # 新增元素 — 在此创建
            element_info = step_data.get('element_info', {})
            if element_info:
                element = _create_element(
                    session.project, element_info, step_data.get('page_url', ''), request.user
                )

        TestCaseStep.objects.create(
            test_case=test_case,
            step_number=step_data.get('step_number', 0),
            action_type=step_data.get('action_type', 'click'),
            element=element,
            input_value=step_data.get('input_value', ''),
            description=step_data.get('description', ''),
        )

    # 更新会话状态
    session.test_case = test_case
    session.status = 'saved'
    session.save()

    return Response({
        'session_id': session.id,
        'test_case_id': test_case.id,
        'test_case_name': test_case.name,
        'step_count': len(confirmed_steps),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_recording(request, session_id):
    """取消录制会话"""
    session = RecordingSession.objects.filter(
        id=session_id, created_by=request.user
    ).exclude(status__in=['saved', 'cancelled']).first()
    if not session:
        return Response({'error': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)

    session.status = 'cancelled'
    session.finished_at = timezone.now()
    session.save()

    return Response({'session_id': session.id, 'status': 'cancelled'})


def _apply_locator_update(element: Element, new_locators: list) -> dict:
    """
    将录制时检测到的定位器更新真正落库（独立于 ElementMatcher，
    仅在用户点击"确认保存"之后调用，逻辑与
    ElementMatcher._apply_update 的非 dry_run 分支保持一致）。
    新的最高优先级定位器成为主定位器，其余存入 backup_locators。
    """
    if not new_locators:
        return {}

    new_primary = new_locators[0]
    new_backups = new_locators[1:]

    strategy_obj = LocatorStrategy.objects.filter(name=new_primary['strategy']).first()
    if strategy_obj:
        element.locator_strategy = strategy_obj
        element.locator_value = new_primary['value']
        element.backup_locators = new_backups if new_backups else None
    else:
        # 策略不存在时不更新主定位器，只更新备用
        element.backup_locators = new_locators

    element.validation_status = 'VALID'
    element.last_validated = timezone.now()
    element.save()
    return {'element_id': element.id, 'new_primary': new_primary, 'new_backups': new_backups}


def _create_element(project, element_info: dict, page_url: str, user) -> Element:
    """根据录制到的元素信息创建新的 Element 记录"""
    from urllib.parse import urlparse
    page_path = urlparse(page_url).path or '/'

    locators = element_info.get('locators', [])
    if not locators:
        # 没有定位器时用 xpath 兜底
        locators = [{'strategy': 'xpath', 'value': '//body'}]

    # 主定位器 = 第一个
    primary = locators[0]
    strategy = LocatorStrategy.objects.filter(name=primary['strategy']).first()
    if not strategy:
        strategy = LocatorStrategy.objects.first()

    # 备用定位器 = 剩余
    backups = locators[1:] if len(locators) > 1 else None

    return Element.objects.create(
        project=project,
        name=element_info.get('element_name', 'unnamed_element'),
        element_type=element_info.get('element_type', 'BUTTON'),
        locator_strategy=strategy,
        locator_value=primary['value'],
        backup_locators=backups,
        page=page_path,
        created_by=user,
    )
