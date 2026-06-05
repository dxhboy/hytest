import os
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from apps.projects.models import Project
from .models import KnowledgeDocument, ProjectSkill
from .knowledge_utils import process_document

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.md', '.txt'}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def knowledge_document_list(request):
    """GET /knowledge/documents/?project_id=<id> — 列出项目知识库文档"""
    project_id = request.query_params.get('project_id')
    if not project_id:
        return Response({'error': 'project_id 参数必填'}, status=status.HTTP_400_BAD_REQUEST)

    docs = KnowledgeDocument.objects.filter(project_id=project_id).values(
        'id', 'name', 'file_size', 'status', 'error_msg', 'created_at'
    )
    return Response({'results': list(docs)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def knowledge_document_upload(request):
    """POST /knowledge/documents/upload/ — 上传文档"""
    project_id = request.data.get('project_id')
    file = request.FILES.get('file')

    if not project_id:
        return Response({'error': 'project_id 必填'}, status=status.HTTP_400_BAD_REQUEST)
    if not file:
        return Response({'error': '未选择文件'}, status=status.HTTP_400_BAD_REQUEST)

    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return Response(
            {'error': f'不支持的文件格式，仅允许: {", ".join(ALLOWED_EXTENSIONS)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    if file.size > MAX_FILE_SIZE:
        return Response({'error': '文件大小不能超过 20MB'}, status=status.HTTP_400_BAD_REQUEST)

    project = get_object_or_404(Project, id=project_id)

    doc = KnowledgeDocument.objects.create(
        project=project,
        name=file.name,
        file=file,
        file_size=file.size,
        created_by=request.user,
    )
    process_document(doc)

    return Response({
        'id': doc.id,
        'name': doc.name,
        'file_size': doc.file_size,
        'status': doc.status,
        'error_msg': doc.error_msg,
    }, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def knowledge_document_delete(request, doc_id):
    """DELETE /knowledge/documents/<id>/ — 删除文档"""
    doc = get_object_or_404(KnowledgeDocument, id=doc_id)
    if doc.file and os.path.exists(doc.file.path):
        os.remove(doc.file.path)
    doc.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def project_skill_get(request):
    """GET /knowledge/skill/?project_id=<id> — 获取项目 Skills"""
    project_id = request.query_params.get('project_id')
    if not project_id:
        return Response({'error': 'project_id 必填'}, status=status.HTTP_400_BAD_REQUEST)

    skill = ProjectSkill.objects.filter(project_id=project_id).first()
    return Response({
        'project_id': int(project_id),
        'content': skill.content if skill else '',
        'updated_at': skill.updated_at.isoformat() if skill else None,
    })


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def project_skill_save(request):
    """PUT /knowledge/skill/save/ — 保存项目 Skills"""
    project_id = request.data.get('project_id')
    content = request.data.get('content', '')

    if not project_id:
        return Response({'error': 'project_id 必填'}, status=status.HTTP_400_BAD_REQUEST)

    project = get_object_or_404(Project, id=project_id)
    skill, _ = ProjectSkill.objects.update_or_create(
        project=project,
        defaults={'content': content, 'updated_by': request.user}
    )
    return Response({
        'project_id': project.id,
        'content': skill.content,
        'updated_at': skill.updated_at.isoformat(),
    })