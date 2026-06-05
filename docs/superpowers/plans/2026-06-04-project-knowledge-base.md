# 项目知识库与 Skills 功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在配置中心新增「项目知识库」页面，支持按项目上传知识库文档和编写 Skills，并在生成测试用例时自动检索注入到 AI 提示词。

**Architecture:** 后端新增 `KnowledgeDocument`（文件 + 全文检索）和 `ProjectSkill`（Markdown 文本）两个模型，通过 `AIModelService._build_knowledge_context()` 在生成前注入上下文；前端新增 `/configuration/knowledge-base` 路由和 `KnowledgeBase.vue` 组件（Tab 布局：文档列表 + Skills 编辑器）。

**Tech Stack:** Django 4.2, DRF, MySQL FULLTEXT index, pypdf, python-docx, Vue 3, Element Plus, Axios

---

## 文件变更清单

| 动作 | 文件 | 说明 |
|------|------|------|
| 修改 | `apps/requirement_analysis/models.py` | 新增 KnowledgeDocument、ProjectSkill 模型；AIModelService 新增 `_build_knowledge_context`；修改 `generate_test_cases` 和 `generate_test_cases_stream` |
| 新建 | `apps/requirement_analysis/migrations/0008_knowledge_base_models.py` | 建表 + FULLTEXT 索引 |
| 新建 | `apps/requirement_analysis/knowledge_utils.py` | 文档文本提取 + 段落切分工具函数 |
| 新建 | `apps/requirement_analysis/knowledge_views.py` | 5 个知识库 API 端点 |
| 修改 | `apps/requirement_analysis/urls.py` | 注册知识库 URL |
| 新建 | `apps/requirement_analysis/tests/test_knowledge.py` | 后端单元测试 |
| 新建 | `frontend/src/api/knowledge.js` | 前端 API 服务层 |
| 修改 | `frontend/src/router/index.js` | 新增 knowledge-base 路由 |
| 修改 | `frontend/src/layout/index.vue` | 配置中心侧边栏新增菜单项 |
| 修改 | `frontend/src/locales/lang/zh-cn/requirement.js` | 新增知识库中文翻译 |
| 修改 | `frontend/src/locales/lang/en/requirement.js` | 新增知识库英文翻译 |
| 新建 | `frontend/src/views/configuration/KnowledgeBase.vue` | 知识库管理页面 |

---

## Task 1: 新增 Django 模型

**Files:**
- Modify: `apps/requirement_analysis/models.py`（在文件末尾现有模型之后追加）

- [ ] **Step 1: 在 models.py 末尾追加两个新模型**

找到 `apps/requirement_analysis/models.py` 文件末尾（现有 `JiraIssueCaseLink` 类结束后），追加以下代码：

```python
class KnowledgeDocument(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_INDEXED = 'indexed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, '待处理'),
        (STATUS_PROCESSING, '处理中'),
        (STATUS_INDEXED, '已索引'),
        (STATUS_FAILED, '失败'),
    ]

    project = models.ForeignKey(
        'projects.Project', on_delete=models.CASCADE,
        related_name='knowledge_docs', verbose_name='所属项目'
    )
    name = models.CharField(max_length=255, verbose_name='文件名')
    file = models.FileField(upload_to='knowledge/', verbose_name='文件')
    file_size = models.PositiveIntegerField(default=0, verbose_name='文件大小(字节)')
    content_text = models.TextField(blank=True, verbose_name='全文内容')
    chunks = models.JSONField(default=list, verbose_name='段落列表')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_PENDING, verbose_name='状态'
    )
    error_msg = models.TextField(blank=True, verbose_name='错误信息')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='knowledge_docs', verbose_name='上传者'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')

    class Meta:
        ordering = ['-created_at']
        verbose_name = '知识库文档'
        verbose_name_plural = '知识库文档'

    def __str__(self):
        return self.name

    @classmethod
    def search(cls, query: str, project_id: int, top_k: int = 3) -> list:
        """BM25 全文检索，返回最相关的 top_k 个文档片段。"""
        if not query or not query.strip():
            return []
        try:
            docs = list(
                cls.objects.filter(
                    project_id=project_id,
                    status=cls.STATUS_INDEXED
                ).extra(
                    where=["MATCH(content_text) AGAINST (%s IN BOOLEAN MODE)"],
                    params=[query[:200]],
                    select={'relevance': "MATCH(content_text) AGAINST (%s IN BOOLEAN MODE)"},
                    select_params=[query[:200]],
                ).order_by('-relevance')[:top_k]
            )
            results = []
            for doc in docs:
                if doc.chunks:
                    results.append("\n".join(doc.chunks[:3]))
                elif doc.content_text:
                    results.append(doc.content_text[:500])
            return results
        except Exception:
            return []


class ProjectSkill(models.Model):
    project = models.OneToOneField(
        'projects.Project', on_delete=models.CASCADE,
        related_name='skill', verbose_name='所属项目'
    )
    content = models.TextField(blank=True, verbose_name='Skills 内容(Markdown)')
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='project_skills', verbose_name='最后修改者'
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='最后修改时间')

    class Meta:
        verbose_name = '项目 Skills'
        verbose_name_plural = '项目 Skills'

    def __str__(self):
        return f"{self.project} Skills"
```

- [ ] **Step 2: 验证模型语法**

```bash
cd /d/python/testhub_platform-main && source venv/Scripts/activate && python manage.py check requirement_analysis
```

期望输出：`System check identified no issues (0 silenced).`

- [ ] **Step 3: 提交**

```bash
git add apps/requirement_analysis/models.py
git commit -m "feat: add KnowledgeDocument and ProjectSkill models"
```

---

## Task 2: 数据库迁移

**Files:**
- Create: `apps/requirement_analysis/migrations/0008_knowledge_base_models.py`

- [ ] **Step 1: 生成迁移文件**

```bash
cd /d/python/testhub_platform-main && source venv/Scripts/activate && python manage.py makemigrations requirement_analysis --name knowledge_base_models
```

期望输出：`Migrations for 'requirement_analysis': apps/requirement_analysis/migrations/0008_knowledge_base_models.py`

- [ ] **Step 2: 在迁移文件中追加 FULLTEXT 索引**

打开生成的 `apps/requirement_analysis/migrations/0008_knowledge_base_models.py`，在 `operations` 列表末尾追加以下 RunSQL 操作（紧接在最后一个 `CreateModel` 之后）：

```python
migrations.RunSQL(
    sql="ALTER TABLE requirement_analysis_knowledgedocument ADD FULLTEXT INDEX idx_content_fulltext (content_text);",
    reverse_sql="ALTER TABLE requirement_analysis_knowledgedocument DROP INDEX idx_content_fulltext;",
),
```

- [ ] **Step 3: 执行迁移**

```bash
python manage.py migrate requirement_analysis
```

期望输出最后一行包含：`Applying requirement_analysis.0008_knowledge_base_models... OK`

- [ ] **Step 4: 提交**

```bash
git add apps/requirement_analysis/migrations/0008_knowledge_base_models.py
git commit -m "feat: add migration for KnowledgeDocument and ProjectSkill tables"
```

---

## Task 3: 文档处理工具

**Files:**
- Create: `apps/requirement_analysis/knowledge_utils.py`
- Create: `apps/requirement_analysis/tests/test_knowledge.py`

- [ ] **Step 1: 写失败的测试**

新建 `apps/requirement_analysis/tests/test_knowledge.py`（如果 `tests/` 目录不存在，先创建 `__init__.py`）：

```python
from django.test import TestCase
from apps.requirement_analysis.knowledge_utils import extract_text, split_into_chunks


class ExtractTextTest(TestCase):
    def test_extract_txt(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.txt', mode='w',
                                         encoding='utf-8', delete=False) as f:
            f.write("Hello world\n\nSecond paragraph")
            path = f.name
        try:
            result = extract_text(path)
            self.assertIn("Hello world", result)
            self.assertIn("Second paragraph", result)
        finally:
            os.unlink(path)

    def test_extract_md(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.md', mode='w',
                                         encoding='utf-8', delete=False) as f:
            f.write("# Title\n\nContent here")
            path = f.name
        try:
            result = extract_text(path)
            self.assertIn("Content here", result)
        finally:
            os.unlink(path)

    def test_unsupported_format_raises(self):
        from apps.requirement_analysis.knowledge_utils import UnsupportedFormatError
        with self.assertRaises(UnsupportedFormatError):
            extract_text("document.xlsx")


class SplitIntoChunksTest(TestCase):
    def test_short_text_single_chunk(self):
        result = split_into_chunks("Short text", max_chunk_size=500)
        self.assertEqual(result, ["Short text"])

    def test_blank_paragraphs_skipped(self):
        result = split_into_chunks("Para1\n\n\n\nPara2", max_chunk_size=500)
        self.assertEqual(result, ["Para1", "Para2"])

    def test_long_paragraph_is_hard_split(self):
        long_text = "A" * 1200
        result = split_into_chunks(long_text, max_chunk_size=500)
        self.assertEqual(len(result), 3)
        self.assertEqual(len(result[0]), 500)
        self.assertEqual(len(result[1]), 500)
        self.assertEqual(len(result[2]), 200)

    def test_empty_text_returns_empty_list(self):
        result = split_into_chunks("", max_chunk_size=500)
        self.assertEqual(result, [])
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /d/python/testhub_platform-main && source venv/Scripts/activate && python manage.py test apps.requirement_analysis.tests.test_knowledge -v 2
```

期望：`ImportError: cannot import name 'extract_text'`（模块不存在）

- [ ] **Step 3: 实现 knowledge_utils.py**

新建 `apps/requirement_analysis/knowledge_utils.py`：

```python
import os


class UnsupportedFormatError(Exception):
    pass


def extract_text(file_path: str) -> str:
    """
    从文件中提取纯文本。
    支持 .pdf / .docx / .md / .txt
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return _extract_pdf(file_path)
    elif ext == '.docx':
        return _extract_docx(file_path)
    elif ext in ('.md', '.txt'):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    else:
        raise UnsupportedFormatError(f"不支持的文件格式: {ext}")


def _extract_pdf(file_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(file_path)
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _extract_docx(file_path: str) -> str:
    from docx import Document
    doc = Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def split_into_chunks(text: str, max_chunk_size: int = 500) -> list:
    """
    按双换行切分段落；超过 max_chunk_size 的段落硬切。
    """
    if not text or not text.strip():
        return []
    raw_paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks = []
    for para in raw_paragraphs:
        if len(para) <= max_chunk_size:
            chunks.append(para)
        else:
            for i in range(0, len(para), max_chunk_size):
                chunk = para[i:i + max_chunk_size]
                if chunk:
                    chunks.append(chunk)
    return chunks


def process_document(doc_instance) -> None:
    """
    提取文本、切分段落，更新 KnowledgeDocument 实例。
    doc_instance 需已 save()（有 id 和 file 字段）。
    """
    from apps.requirement_analysis.models import KnowledgeDocument
    try:
        doc_instance.status = KnowledgeDocument.STATUS_PROCESSING
        doc_instance.save(update_fields=['status'])

        file_path = doc_instance.file.path
        text = extract_text(file_path)
        chunks = split_into_chunks(text)

        doc_instance.content_text = text
        doc_instance.chunks = chunks
        doc_instance.status = KnowledgeDocument.STATUS_INDEXED
        doc_instance.error_msg = ''
        doc_instance.save(update_fields=['content_text', 'chunks', 'status', 'error_msg'])
    except Exception as e:
        doc_instance.status = KnowledgeDocument.STATUS_FAILED
        doc_instance.error_msg = str(e)[:500]
        doc_instance.save(update_fields=['status', 'error_msg'])
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python manage.py test apps.requirement_analysis.tests.test_knowledge -v 2
```

期望：`Ran 7 tests in ...s  OK`

- [ ] **Step 5: 提交**

```bash
git add apps/requirement_analysis/knowledge_utils.py apps/requirement_analysis/tests/
git commit -m "feat: add document text extraction and chunking utilities"
```

---

## Task 4: 知识库 API 视图

**Files:**
- Create: `apps/requirement_analysis/knowledge_views.py`
- Modify: `apps/requirement_analysis/urls.py`

- [ ] **Step 1: 新建 knowledge_views.py**

新建 `apps/requirement_analysis/knowledge_views.py`：

```python
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
    """POST /knowledge/documents/ — 上传文档"""
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
    """PUT /knowledge/skill/ — 保存项目 Skills"""
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
```

- [ ] **Step 2: 注册 URL**

打开 `apps/requirement_analysis/urls.py`，在文件头部的 import 区块之后（`from . import jira_views` 一行之后）添加：

```python
from . import knowledge_views
```

然后在 `urlpatterns` 列表末尾（最后一个 `path(...)` 之后）追加：

```python
    # 知识库端点
    path('knowledge/documents/', knowledge_views.knowledge_document_list, name='knowledge-doc-list'),
    path('knowledge/documents/upload/', knowledge_views.knowledge_document_upload, name='knowledge-doc-upload'),
    path('knowledge/documents/<int:doc_id>/', knowledge_views.knowledge_document_delete, name='knowledge-doc-delete'),
    path('knowledge/skill/', knowledge_views.project_skill_get, name='knowledge-skill-get'),
    path('knowledge/skill/save/', knowledge_views.project_skill_save, name='knowledge-skill-save'),
```

- [ ] **Step 3: 验证 URL 注册成功**

```bash
cd /d/python/testhub_platform-main && source venv/Scripts/activate && python manage.py show_urls 2>/dev/null | grep knowledge || python manage.py check
```

期望看到 5 条 `/api/requirement-analysis/knowledge/` 开头的 URL，或 check 无报错。

- [ ] **Step 4: 提交**

```bash
git add apps/requirement_analysis/knowledge_views.py apps/requirement_analysis/urls.py
git commit -m "feat: add knowledge base API endpoints (documents + skills)"
```

---

## Task 5: AI 生成上下文注入

**Files:**
- Modify: `apps/requirement_analysis/models.py`

- [ ] **Step 1: 在 AIModelService 类中添加 `_build_knowledge_context` 方法**

找到 `apps/requirement_analysis/models.py` 中 `class AIModelService:` 的定义，在类的第一个 `@staticmethod` 方法之前插入以下方法（作为类的第一个方法）：

```python
    @staticmethod
    def _build_knowledge_context(task) -> tuple:
        """
        根据任务所属项目，检索 Skills 和知识库文档，
        返回 (extra_system, extra_user) 用于注入提示词。
        """
        extra_system = ""
        extra_user = ""

        if not task.project_id:
            return extra_system, extra_user

        try:
            skill = ProjectSkill.objects.filter(project_id=task.project_id).first()
            if skill and skill.content and skill.content.strip():
                extra_system = "\n\n## 项目测试规范\n" + skill.content
        except Exception:
            pass

        try:
            chunks = KnowledgeDocument.search(
                query=task.requirement_text,
                project_id=task.project_id,
                top_k=3
            )
            if chunks:
                extra_user = "## 参考知识库\n" + "\n---\n".join(chunks) + "\n\n"
        except Exception:
            pass

        return extra_system, extra_user
```

- [ ] **Step 2: 修改 `generate_test_cases` 方法（line 695）**

找到 `generate_test_cases` 方法中这段代码（约 line 697-727）：

```python
        writer_prompt = task.writer_prompt_config.content

        # 构建更明确的用户提示，采用思维链(CoT)引导和细粒度拆分策略
        user_message = (
```

将 `writer_prompt = task.writer_prompt_config.content` 这一行替换为：

```python
        from asgiref.sync import sync_to_async
        extra_system, extra_user = await sync_to_async(
            AIModelService._build_knowledge_context
        )(task)
        writer_prompt = task.writer_prompt_config.content + extra_system
```

然后找到该方法中 `user_message` 字符串的结束位置（约 line 722）：

```python
            f"【需求文档内容】\n{task.requirement_text}"
        )
```

将其替换为：

```python
            f"【需求文档内容】\n{task.requirement_text}"
        )
        if extra_user:
            user_message = extra_user + user_message
```

- [ ] **Step 3: 修改 `generate_test_cases_stream` 方法（line 774）**

找到 `generate_test_cases_stream` 方法中这段代码（约 line 788）：

```python
        writer_prompt = task.writer_prompt_config.content

        # 构建用户提示
        user_message = (
```

将 `writer_prompt = task.writer_prompt_config.content` 这一行替换为：

```python
        from asgiref.sync import sync_to_async
        extra_system, extra_user = await sync_to_async(
            AIModelService._build_knowledge_context
        )(task)
        writer_prompt = task.writer_prompt_config.content + extra_system
```

然后找到该方法中 `user_message` 字符串的结束位置（约 line 813）：

```python
            f"【需求文档内容】\n{task.requirement_text}"
        )
```

将其替换为：

```python
            f"【需求文档内容】\n{task.requirement_text}"
        )
        if extra_user:
            user_message = extra_user + user_message
```

- [ ] **Step 4: 验证语法**

```bash
cd /d/python/testhub_platform-main && source venv/Scripts/activate && python manage.py check requirement_analysis
```

期望：`System check identified no issues (0 silenced).`

- [ ] **Step 5: 提交**

```bash
git add apps/requirement_analysis/models.py
git commit -m "feat: inject knowledge base and skills context before AI generation"
```

---

## Task 6: 前端 API 服务层

**Files:**
- Create: `frontend/src/api/knowledge.js`

- [ ] **Step 1: 新建 knowledge.js**

新建 `frontend/src/api/knowledge.js`：

```javascript
import request from "@/utils/api";

// 知识库文档

export function getKnowledgeDocs(projectId) {
  return request({
    url: "/requirement-analysis/knowledge/documents/",
    method: "get",
    params: { project_id: projectId },
  });
}

export function uploadKnowledgeDoc(projectId, file) {
  const formData = new FormData();
  formData.append("project_id", projectId);
  formData.append("file", file);
  return request({
    url: "/requirement-analysis/knowledge/documents/upload/",
    method: "post",
    data: formData,
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export function deleteKnowledgeDoc(docId) {
  return request({
    url: `/requirement-analysis/knowledge/documents/${docId}/`,
    method: "delete",
  });
}

// 项目 Skills

export function getProjectSkill(projectId) {
  return request({
    url: "/requirement-analysis/knowledge/skill/",
    method: "get",
    params: { project_id: projectId },
  });
}

export function saveProjectSkill(projectId, content) {
  return request({
    url: "/requirement-analysis/knowledge/skill/save/",
    method: "put",
    data: { project_id: projectId, content },
  });
}
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/api/knowledge.js
git commit -m "feat: add knowledge base API service layer"
```

---

## Task 7: 路由、菜单、i18n

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layout/index.vue`
- Modify: `frontend/src/locales/lang/zh-cn/requirement.js`
- Modify: `frontend/src/locales/lang/en/requirement.js`

- [ ] **Step 1: 新增路由**

打开 `frontend/src/router/index.js`，找到 configuration children 数组中最后一个路由配置：

```javascript
        {
          path: "projects",
          name: "ConfigProjectCenter",
          component: () => import("@/views/configuration/ProjectCenter.vue"),
        },
```

在其后（`],` 闭合括号之前）追加：

```javascript
        {
          path: "knowledge-base",
          name: "ConfigKnowledgeBase",
          component: () =>
            import("@/views/configuration/KnowledgeBase.vue"),
        },
```

- [ ] **Step 2: 新增侧边栏菜单项**

打开 `frontend/src/layout/index.vue`，找到配置中心菜单末尾（约 line 211-214）：

```vue
            <el-menu-item index="/configuration/projects">
              <el-icon><FolderOpened /></el-icon>
              <span>{{ $t("menu.projectCenter") }}</span>
            </el-menu-item>
          </template>
```

在 `</template>` 之前插入：

```vue
            <el-menu-item index="/configuration/knowledge-base">
              <el-icon><Collection /></el-icon>
              <span>{{ $t("menu.knowledgeBase") }}</span>
            </el-menu-item>
```

然后在同文件顶部 `import { ... } from "@element-plus/icons-vue"` 的 icons 引入中，确认 `Collection` 已包含；若没有，追加 `Collection` 到该导入列表。

- [ ] **Step 3: 添加中文翻译**

打开 `frontend/src/locales/lang/zh-cn/requirement.js`，在 `export default {` 对象内（任意现有 key 之后）添加新的顶层 key：

```javascript
  knowledgeBase: {
    title: "项目知识库",
    selectProject: "选择项目",
    selectProjectPlaceholder: "请选择项目",
    tabDocs: "知识库文档",
    tabSkills: "Skills 配置",
    uploadBtn: "上传文档",
    uploadHint: "支持 PDF / DOCX / MD / TXT，单文件 ≤ 20MB",
    colName: "文件名",
    colSize: "大小",
    colStatus: "状态",
    colAction: "操作",
    statusPending: "待处理",
    statusProcessing: "处理中",
    statusIndexed: "已索引",
    statusFailed: "失败",
    deleteConfirm: "确认删除此文档？",
    deleteSuccess: "删除成功",
    uploadSuccess: "上传成功，正在建立索引",
    uploadFailed: "上传失败",
    skillsHint: "在此填写本项目的测试规范、业务约束和注意事项。生成测试用例时，这些内容将自动追加到 AI 提示词中。",
    skillsPlaceholder: "## 测试规范\n\n### 通用规则\n- ...",
    saveBtn: "保存",
    previewBtn: "预览",
    saveSuccess: "保存成功",
    lastSaved: "最后保存：",
    previewTitle: "Skills 预览",
  },
```

同时在 `frontend/src/locales/lang/zh-cn/` 中找到菜单翻译文件（通常为 `index.js` 或 `menu.js`，搜索含有 `projectCenter` key 的文件），在同级位置追加：

```javascript
    knowledgeBase: "项目知识库",
```

- [ ] **Step 4: 添加英文翻译**

打开 `frontend/src/locales/lang/en/requirement.js`，在对应位置添加：

```javascript
  knowledgeBase: {
    title: "Project Knowledge Base",
    selectProject: "Select Project",
    selectProjectPlaceholder: "Please select a project",
    tabDocs: "Documents",
    tabSkills: "Skills",
    uploadBtn: "Upload Document",
    uploadHint: "Supports PDF / DOCX / MD / TXT, max 20MB per file",
    colName: "File Name",
    colSize: "Size",
    colStatus: "Status",
    colAction: "Action",
    statusPending: "Pending",
    statusProcessing: "Processing",
    statusIndexed: "Indexed",
    statusFailed: "Failed",
    deleteConfirm: "Confirm delete this document?",
    deleteSuccess: "Deleted successfully",
    uploadSuccess: "Uploaded, indexing in progress",
    uploadFailed: "Upload failed",
    skillsHint: "Write project-specific test standards, constraints, and notes here. These will be automatically appended to the AI prompt when generating test cases.",
    skillsPlaceholder: "## Test Standards\n\n### General Rules\n- ...",
    saveBtn: "Save",
    previewBtn: "Preview",
    saveSuccess: "Saved successfully",
    lastSaved: "Last saved: ",
    previewTitle: "Skills Preview",
  },
```

在英文菜单翻译文件同级位置追加：

```javascript
    knowledgeBase: "Knowledge Base",
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/router/index.js frontend/src/layout/index.vue frontend/src/locales/
git commit -m "feat: add knowledge base route, menu item, and i18n keys"
```

---

## Task 8: KnowledgeBase.vue 组件

**Files:**
- Create: `frontend/src/views/configuration/KnowledgeBase.vue`

- [ ] **Step 1: 新建 KnowledgeBase.vue**

新建 `frontend/src/views/configuration/KnowledgeBase.vue`：

```vue
<template>
  <div class="knowledge-base">
    <!-- 顶部：项目选择 -->
    <div class="kb-header">
      <el-select
        v-model="selectedProjectId"
        :placeholder="$t('knowledgeBase.selectProjectPlaceholder')"
        filterable
        style="width: 280px"
        @change="onProjectChange"
      >
        <el-option
          v-for="p in projects"
          :key="p.id"
          :label="p.name"
          :value="p.id"
        />
      </el-select>
    </div>

    <!-- 主内容：Tab 切换 -->
    <el-tabs v-model="activeTab" class="kb-tabs" :class="{ 'is-hidden': !selectedProjectId }">
      <!-- Tab 1: 知识库文档 -->
      <el-tab-pane :label="$t('knowledgeBase.tabDocs')" name="docs">
        <div class="tab-toolbar">
          <span class="doc-count">{{ documents.length }} 个文档</span>
          <el-upload
            :show-file-list="false"
            :before-upload="handleBeforeUpload"
            :http-request="handleUpload"
            accept=".pdf,.docx,.md,.txt"
          >
            <el-button type="primary" :loading="uploading">
              + {{ $t('knowledgeBase.uploadBtn') }}
            </el-button>
          </el-upload>
        </div>

        <el-table :data="documents" stripe style="width: 100%">
          <el-table-column :label="$t('knowledgeBase.colName')" prop="name" min-width="200" />
          <el-table-column :label="$t('knowledgeBase.colSize')" width="100">
            <template #default="{ row }">
              {{ formatSize(row.file_size) }}
            </template>
          </el-table-column>
          <el-table-column :label="$t('knowledgeBase.colStatus')" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ $t(`knowledgeBase.status${capitalize(row.status)}`) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('knowledgeBase.colAction')" width="80">
            <template #default="{ row }">
              <el-popconfirm
                :title="$t('knowledgeBase.deleteConfirm')"
                @confirm="handleDelete(row.id)"
              >
                <template #reference>
                  <el-button type="danger" link size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="documents.length === 0 && !docsLoading" class="empty-hint">
          <el-empty description="暂无文档，请上传" :image-size="80" />
        </div>
      </el-tab-pane>

      <!-- Tab 2: Skills 配置 -->
      <el-tab-pane :label="$t('knowledgeBase.tabSkills')" name="skills">
        <div class="skills-hint">{{ $t('knowledgeBase.skillsHint') }}</div>

        <el-input
          v-model="skillContent"
          type="textarea"
          :autosize="{ minRows: 12, maxRows: 30 }"
          :placeholder="$t('knowledgeBase.skillsPlaceholder')"
          class="skills-editor"
        />

        <div class="skills-footer">
          <span v-if="skillSavedAt" class="saved-time">
            {{ $t('knowledgeBase.lastSaved') }}{{ skillSavedAt }}
          </span>
          <div class="skills-actions">
            <el-button @click="showPreview = true">{{ $t('knowledgeBase.previewBtn') }}</el-button>
            <el-button type="primary" :loading="skillSaving" @click="handleSaveSkill">
              {{ $t('knowledgeBase.saveBtn') }}
            </el-button>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <div v-if="!selectedProjectId" class="select-hint">
      <el-empty description="请先选择项目" :image-size="80" />
    </div>

    <!-- Skills 预览弹窗 -->
    <el-dialog
      v-model="showPreview"
      :title="$t('knowledgeBase.previewTitle')"
      width="600px"
    >
      <pre class="skills-preview">{{ skillContent || '（暂无内容）' }}</pre>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import {
  getKnowledgeDocs,
  uploadKnowledgeDoc,
  deleteKnowledgeDoc,
  getProjectSkill,
  saveProjectSkill,
} from '@/api/knowledge'
import request from '@/utils/api'

const { t } = useI18n()

const projects = ref([])
const selectedProjectId = ref(null)
const activeTab = ref('docs')

// 文档列表
const documents = ref([])
const docsLoading = ref(false)
const uploading = ref(false)

// Skills
const skillContent = ref('')
const skillSaving = ref(false)
const skillSavedAt = ref('')
const showPreview = ref(false)

onMounted(async () => {
  try {
    const res = await request({ url: '/projects/', method: 'get' })
    projects.value = res.results || res
  } catch (e) {
    // 静默失败，projects 为空
  }
})

async function onProjectChange(projectId) {
  if (!projectId) return
  await Promise.all([loadDocs(projectId), loadSkill(projectId)])
}

async function loadDocs(projectId) {
  docsLoading.value = true
  try {
    const res = await getKnowledgeDocs(projectId)
    documents.value = res.results || []
  } finally {
    docsLoading.value = false
  }
}

async function loadSkill(projectId) {
  try {
    const res = await getProjectSkill(projectId)
    skillContent.value = res.content || ''
    skillSavedAt.value = res.updated_at
      ? new Date(res.updated_at).toLocaleString()
      : ''
  } catch (e) {
    skillContent.value = ''
  }
}

function handleBeforeUpload(file) {
  const allowed = ['.pdf', '.docx', '.md', '.txt']
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!allowed.includes(ext)) {
    ElMessage.error(t('knowledgeBase.uploadHint'))
    return false
  }
  if (file.size > 20 * 1024 * 1024) {
    ElMessage.error(t('knowledgeBase.uploadHint'))
    return false
  }
  return true
}

async function handleUpload({ file }) {
  uploading.value = true
  try {
    const res = await uploadKnowledgeDoc(selectedProjectId.value, file)
    documents.value.unshift(res)
    ElMessage.success(t('knowledgeBase.uploadSuccess'))
    // 轮询状态直到 indexed/failed
    pollDocStatus(res.id)
  } catch (e) {
    ElMessage.error(t('knowledgeBase.uploadFailed'))
  } finally {
    uploading.value = false
  }
}

function pollDocStatus(docId) {
  let retries = 0
  const timer = setInterval(async () => {
    retries++
    if (retries > 30) { clearInterval(timer); return }
    try {
      const res = await getKnowledgeDocs(selectedProjectId.value)
      const doc = (res.results || []).find(d => d.id === docId)
      if (doc) {
        const idx = documents.value.findIndex(d => d.id === docId)
        if (idx !== -1) documents.value[idx] = doc
        if (doc.status === 'indexed' || doc.status === 'failed') {
          clearInterval(timer)
        }
      }
    } catch (e) {
      clearInterval(timer)
    }
  }, 2000)
}

async function handleDelete(docId) {
  try {
    await deleteKnowledgeDoc(docId)
    documents.value = documents.value.filter(d => d.id !== docId)
    ElMessage.success(t('knowledgeBase.deleteSuccess'))
  } catch (e) {
    ElMessage.error('删除失败')
  }
}

async function handleSaveSkill() {
  skillSaving.value = true
  try {
    const res = await saveProjectSkill(selectedProjectId.value, skillContent.value)
    skillSavedAt.value = new Date(res.updated_at).toLocaleString()
    ElMessage.success(t('knowledgeBase.saveSuccess'))
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    skillSaving.value = false
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function statusTagType(status) {
  const map = { pending: 'info', processing: 'warning', indexed: 'success', failed: 'danger' }
  return map[status] || 'info'
}

function capitalize(str) {
  return str.charAt(0).toUpperCase() + str.slice(1)
}
</script>

<style scoped>
.knowledge-base {
  padding: 20px;
}
.kb-header {
  margin-bottom: 20px;
}
.kb-tabs.is-hidden {
  display: none;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.doc-count {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.empty-hint {
  margin-top: 40px;
}
.skills-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 12px;
  line-height: 1.6;
}
.skills-editor {
  font-family: monospace;
}
.skills-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}
.saved-time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.skills-actions {
  display: flex;
  gap: 8px;
}
.select-hint {
  margin-top: 60px;
}
.skills-preview {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: monospace;
  font-size: 13px;
  background: var(--el-fill-color-light);
  padding: 12px;
  border-radius: 4px;
  max-height: 400px;
  overflow-y: auto;
}
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/views/configuration/KnowledgeBase.vue
git commit -m "feat: add KnowledgeBase.vue configuration page"
```

---

## Task 9: 端到端验证

- [ ] **Step 1: 启动后端**

```bash
cd /d/python/testhub_platform-main && source venv/Scripts/activate && python manage.py runserver
```

- [ ] **Step 2: 启动前端**

```bash
cd /d/python/testhub_platform-main/frontend && "D:/software/Node/node.exe" node_modules/vite/bin/vite.js
```

- [ ] **Step 3: 手动验证功能**

1. 打开 http://localhost:3000/configuration/knowledge-base
2. 确认侧边栏「项目知识库」菜单项可见
3. 选择一个项目
4. 上传一个 .txt 测试文件，确认状态最终变为「已索引」
5. 切换到 Skills Tab，输入测试文本，点击保存，确认提示「保存成功」
6. 刷新页面，重新选择同一项目，确认 Skills 内容持久化
7. 删除刚才上传的文档，确认从列表中消失

- [ ] **Step 4: 验证 AI 注入**

在需求分析页面对有知识库文档和 Skills 的项目触发生成，通过 Django shell 验证注入是否发生：

```bash
python manage.py shell
```

```python
from apps.requirement_analysis.models import AIModelService, TestCaseGenerationTask
# 取一个已有的 task
task = TestCaseGenerationTask.objects.filter(project__isnull=False).last()
if task:
    extra_system, extra_user = AIModelService._build_knowledge_context(task)
    print("extra_system:", extra_system[:100] if extra_system else "(空)")
    print("extra_user:", extra_user[:100] if extra_user else "(空)")
```

- [ ] **Step 5: 最终提交**

```bash
git add -A
git commit -m "feat: complete project knowledge base and skills feature"
```

---

## 自检：Spec 覆盖检查

| Spec 需求 | 任务 |
|-----------|------|
| 按项目上传知识库文档（PDF/Word/Markdown） | Task 3, 4, 8 |
| 文档全文检索（BM25） | Task 2, 3 |
| 按项目编写 Skills（Markdown 文本块） | Task 4, 8 |
| 配置中心新增独立路由 `/configuration/knowledge-base` | Task 7 |
| Tab 切换：文档 + Skills | Task 8 |
| 项目下拉选择器 | Task 8 |
| 右上角上传按钮 + 文件列表（名称/大小/状态/删除） | Task 8 |
| 上传后轮询状态 | Task 8 |
| Skills 保存/预览按钮 | Task 8 |
| 生成时自动注入 Skills 到系统提示词 | Task 5 |
| 生成时自动检索知识库注入用户消息 | Task 5 |
| Jira 生成复用同一注入路径 | Task 5（通过 project_id 自动复用） |
| 侧边栏菜单项 | Task 7 |
| i18n 中英文 | Task 7 |
| 后端依赖 pypdf / python-docx | 已存在，无需安装 |
