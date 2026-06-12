import logging
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AssistantSession, AssistantMessage
from .serializers import (
    AssistantSessionSerializer, AssistantMessageSerializer, SendMessageSerializer
)
from .tools.base import run_tool_loop

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """你是 TestHub 测试平台的 AI 助手，可以帮助用户管理接口测试和 UI 自动化测试。

当前上下文：
- 模块: {context_module}
- 页面: {context_page}
- 项目ID: {context_project_id}

你可以查询、创建接口用例，列出/触发测试套件执行，查询执行结果。
请用中文回复。如果用户请求不清晰，先澄清再操作。
执行写入或执行类操作前，简要描述你将要做什么。"""


class ChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = SendMessageSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        data = ser.validated_data
        user_message = data['message']
        context = data.get('context') or {}
        session_id = data.get('session_id')

        # 获取或创建会话
        if session_id:
            session = AssistantSession.objects.filter(id=session_id, user=user).first()
            if not session:
                return Response({'error': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)
        else:
            session = AssistantSession.objects.create(
                user=user,
                title=user_message[:20],
                context_module=context.get('module', ''),
                context_page=context.get('page', ''),
                context_project_id=context.get('project_id'),
            )

        # 保存用户消息
        AssistantMessage.objects.create(session=session, role='user', content=user_message)

        # 构建消息历史（最近 20 条，避免 token 超限）
        history = list(
            session.messages.exclude(role='tool')
            .order_by('-created_at')[:20]
        )[::-1]

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            context_module=context.get('module', '未知'),
            context_page=context.get('page', '未知'),
            context_project_id=context.get('project_id', '未指定'),
        )
        messages = [{'role': 'system', 'content': system_prompt}]
        for m in history:
            messages.append({'role': m.role, 'content': m.content})

        # 执行工具循环
        try:
            reply, tools_called = run_tool_loop(messages, [], user, context)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.exception('AI tool loop error')
            return Response({'error': f'AI 服务异常: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 保存助手回复
        AssistantMessage.objects.create(
            session=session, role='assistant', content=reply,
            tool_name=','.join(tools_called) if tools_called else '',
        )

        # 更新会话时间
        session.save(update_fields=['updated_at'])

        return Response({
            'session_id': session.id,
            'reply': reply,
            'tools_called': tools_called,
        })


class SessionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AssistantSessionSerializer
    http_method_names = ['get', 'delete', 'head', 'options']

    def get_queryset(self):
        return AssistantSession.objects.filter(user=self.request.user)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        session = self.get_object()
        msgs = session.messages.all()
        return Response(AssistantMessageSerializer(msgs, many=True).data)
