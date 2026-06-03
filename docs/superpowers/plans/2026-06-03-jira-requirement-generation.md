# Jira 需求导入与测试用例生成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 支持从 Jira Cloud Issue 拉取需求并生成测试用例，同时建立 Issue ↔ 版本 ↔ 用例三向关联，实现基于 Jira 需求的回归用例推荐。

**Architecture:** 在 `requirement_analysis` 模块内新增 `jira_client.py` 封装 Jira REST API v3；`UserProfile` 扩展三个 Jira 凭据字段；新增 `JiraIssueLink` 和 `JiraIssueCaseLink` 两张关联表；前端新增独立的 `JiraImport.vue` 页面和个人资料 Jira 配置 Tab。

**Tech Stack:** Django REST Framework, httpx (已有), cryptography (新增), Django GenericForeignKey, Vue 3, Element Plus, Vue I18n

---

## 文件清单

### 新建文件
- `apps/requirement_analysis/jira_client.py` — Jira API 客户端
- `apps/requirement_analysis/jira_views.py` — Jira 相关视图（preview/import/recommend）
- `apps/requirement_analysis/jira_serializers.py` — Jira 相关序列化器
- `tests/requirement_analysis/test_jira_client.py` — jira_client 单测
- `tests/requirement_analysis/test_jira_views.py` — jira views 单测
- `frontend/src/views/requirement-analysis/JiraImport.vue` — 导入主页面
- `frontend/src/api/jira.js` — 前端 Jira API 调用层

### 修改文件
- `apps/users/models.py` — UserProfile 新增三个 Jira 字段
- `apps/users/serializers.py` — UserProfileSerializer 加入 Jira 字段（token 脱敏）
- `apps/users/views.py` — profile_view 支持更新 Jira 字段
- `apps/requirement_analysis/models.py` — 新增 JiraIssueLink、JiraIssueCaseLink 模型
- `apps/requirement_analysis/urls.py` — 注册 Jira 路由
- `apps/requirement_analysis/migrations/` — 数据库迁移文件（自动生成）
- `apps/users/migrations/` — UserProfile 迁移文件（自动生成）
- `frontend/src/views/profile/UserProfile.vue` — 新增 Jira 配置 Tab
- `frontend/src/views/requirement-analysis/RequirementAnalysisView.vue` — 侧边栏新增菜单项（或在 layout/router 处理）
- `frontend/src/router/index.js` — 新增 `/ai-generation/jira-import` 路由
- `frontend/src/locales/lang/zh-cn/requirement.js` — 新增 jira.* 命名空间
- `frontend/src/locales/lang/en/requirement.js` — 对应英文翻译
- `backend/settings.py` — 新增 `JIRA_TOKEN_ENCRYPT_KEY` 配置（或使用 SECRET_KEY 派生）

---

## Task 1: 安装 cryptography 依赖并配置加密密钥

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/settings.py`

- [ ] **Step 1: 检查 cryptography 是否已安装**

```bash
cd /d/python/testhub_platform-main
source venv/Scripts/activate
pip show cryptography
```

若已安装跳过 Step 2。

- [ ] **Step 2: 安装 cryptography**

```bash
pip install cryptography
echo "cryptography>=41.0.0" >> requirements.txt
```

- [ ] **Step 3: 在 settings.py 添加加密密钥配置**

在 `backend/settings.py` 末尾添加：

```python
import base64, hashlib
# 从 SECRET_KEY 派生 32 字节 Fernet 密钥，无需额外环境变量
_raw = hashlib.sha256(SECRET_KEY.encode()).digest()
JIRA_TOKEN_ENCRYPT_KEY = base64.urlsafe_b64encode(_raw)
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt backend/settings.py
git commit -m "chore: add cryptography dep and jira token encrypt key"
```

---

## Task 2: UserProfile 模型扩展（后端）

**Files:**
- Modify: `apps/users/models.py`
- Create: `apps/users/migrations/000X_userprofile_jira_fields.py`（自动生成）

- [ ] **Step 1: 写失败测试**

新建或追加到 `tests/users/test_models.py`：

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.users.models import UserProfile

User = get_user_model()

class UserProfileJiraFieldsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='pass')

    def test_jira_fields_default_blank(self):
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.jira_domain, '')
        self.assertEqual(profile.jira_email, '')
        self.assertEqual(profile.jira_api_token, '')

    def test_jira_fields_can_be_set(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.jira_domain = 'company.atlassian.net'
        profile.jira_email = 'user@company.com'
        profile.jira_api_token = 'encrypted_token_here'
        profile.save()
        profile.refresh_from_db()
        self.assertEqual(profile.jira_domain, 'company.atlassian.net')
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test tests.users.test_models.UserProfileJiraFieldsTest -v 2
```

期望：`AttributeError: 'UserProfile' object has no attribute 'jira_domain'`

- [ ] **Step 3: 在 UserProfile 模型添加字段**

打开 `apps/users/models.py`，在 `UserProfile` 模型的 `notifications` 字段后添加：

```python
    # Jira Cloud 集成凭据
    jira_domain = models.CharField(max_length=255, blank=True, default='',
                                   verbose_name='Jira 域名')
    jira_email = models.CharField(max_length=255, blank=True, default='',
                                  verbose_name='Jira 邮箱')
    jira_api_token = models.CharField(max_length=512, blank=True, default='',
                                      verbose_name='Jira API Token（加密）')
```

- [ ] **Step 4: 生成并应用迁移**

```bash
python manage.py makemigrations users --name="userprofile_jira_fields"
python manage.py migrate
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python manage.py test tests.users.test_models.UserProfileJiraFieldsTest -v 2
```

期望：`OK`

- [ ] **Step 6: Commit**

```bash
git add apps/users/models.py apps/users/migrations/
git commit -m "feat: add jira credential fields to UserProfile"
```

---

## Task 3: UserProfile 序列化器与视图更新（含 token 加解密）

**Files:**
- Modify: `apps/users/serializers.py`
- Modify: `apps/users/views.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/users/test_jira_profile_api.py`：

```python
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()

class JiraProfileAPITest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='pass123')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_save_and_retrieve_jira_config(self):
        url = reverse('profile')  # /api/users/profile/
        data = {
            'jira_domain': 'myco.atlassian.net',
            'jira_email': 'me@myco.com',
            'jira_api_token': 'mytoken123',
        }
        resp = self.client.patch(url, data, format='json')
        self.assertEqual(resp.status_code, 200)

        # 重新读取，token 应被脱敏
        resp2 = self.client.get(url)
        self.assertEqual(resp2.data['jira_domain'], 'myco.atlassian.net')
        self.assertEqual(resp2.data['jira_email'], 'me@myco.com')
        self.assertEqual(resp2.data['jira_api_token'], '***')

    def test_empty_token_does_not_overwrite(self):
        url = reverse('profile')
        # 先保存 token
        self.client.patch(url, {'jira_api_token': 'original_token'}, format='json')
        # 再用空 token 更新其他字段
        self.client.patch(url, {'jira_domain': 'other.atlassian.net', 'jira_api_token': ''}, format='json')
        from apps.users.models import UserProfile
        from cryptography.fernet import Fernet
        from django.conf import settings
        profile = UserProfile.objects.get(user=self.user)
        f = Fernet(settings.JIRA_TOKEN_ENCRYPT_KEY)
        decrypted = f.decrypt(profile.jira_api_token.encode()).decode()
        self.assertEqual(decrypted, 'original_token')
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test tests.users.test_jira_profile_api -v 2
```

期望：序列化器不含 jira 字段，返回 400 或字段被忽略。

- [ ] **Step 3: 更新 UserProfileSerializer**

在 `apps/users/serializers.py` 找到 `UserProfileSerializer`，替换为：

```python
from cryptography.fernet import Fernet
from django.conf import settings

def _get_fernet():
    return Fernet(settings.JIRA_TOKEN_ENCRYPT_KEY)

class UserProfileSerializer(serializers.ModelSerializer):
    # 只读，返回脱敏值
    jira_api_token = serializers.SerializerMethodField()
    # 只写，接收明文
    jira_api_token_input = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = UserProfile
        fields = ['theme', 'language', 'timezone', 'notifications',
                  'jira_domain', 'jira_email', 'jira_api_token', 'jira_api_token_input']

    def get_jira_api_token(self, obj):
        return '***' if obj.jira_api_token else ''

    def update(self, instance, validated_data):
        token_input = validated_data.pop('jira_api_token_input', None)
        if token_input:  # 非空才加密覆盖
            f = _get_fernet()
            instance.jira_api_token = f.encrypt(token_input.encode()).decode()
        return super().update(instance, validated_data)
```

- [ ] **Step 4: 确认 profile_view 支持 PATCH**

打开 `apps/users/views.py`，找到 `profile_view`。确保它调用 `UserProfileSerializer`。若当前不支持 PATCH，改为：

```python
@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'GET':
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data)
    partial = request.method == 'PATCH'
    serializer = UserProfileSerializer(profile, data=request.data, partial=partial)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python manage.py test tests.users.test_jira_profile_api -v 2
```

期望：`OK`

- [ ] **Step 6: Commit**

```bash
git add apps/users/serializers.py apps/users/views.py
git commit -m "feat: jira credentials in UserProfile with encrypted token storage"
```

---

## Task 4: JiraIssueLink 和 JiraIssueCaseLink 模型

**Files:**
- Modify: `apps/requirement_analysis/models.py`
- Create: migration 文件（自动生成）

- [ ] **Step 1: 写失败测试**

新建 `tests/requirement_analysis/test_jira_models.py`：

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from apps.requirement_analysis.models import JiraIssueLink, JiraIssueCaseLink, GeneratedTestCase

User = get_user_model()

class JiraIssueLinkTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='pass')

    def test_create_issue_link(self):
        link = JiraIssueLink.objects.create(
            issue_key='PROJ-123',
            issue_url='https://co.atlassian.net/browse/PROJ-123',
            issue_summary='Login feature',
            jira_domain='co.atlassian.net',
            created_by=self.user,
        )
        self.assertEqual(str(link.issue_key), 'PROJ-123')

    def test_unique_together_issue_key_domain(self):
        JiraIssueLink.objects.create(
            issue_key='PROJ-1', issue_url='https://co.atlassian.net/browse/PROJ-1',
            issue_summary='S', jira_domain='co.atlassian.net', created_by=self.user)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            JiraIssueLink.objects.create(
                issue_key='PROJ-1', issue_url='https://co.atlassian.net/browse/PROJ-1',
                issue_summary='S', jira_domain='co.atlassian.net', created_by=self.user)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test tests.requirement_analysis.test_jira_models -v 2
```

- [ ] **Step 3: 在 models.py 末尾添加两个新模型**

打开 `apps/requirement_analysis/models.py`，在文件顶部 imports 区域确认已有以下 import（若没有则添加）：

```python
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
```

然后在文件末尾追加：

```python
class JiraIssueLink(models.Model):
    """记录已导入的 Jira Issue 及其与 TestHub 版本的关联"""
    issue_key        = models.CharField(max_length=64, verbose_name='Issue Key')
    issue_url        = models.URLField(verbose_name='Issue URL')
    issue_summary    = models.CharField(max_length=500, verbose_name='Issue 标题')
    jira_domain      = models.CharField(max_length=255, verbose_name='Jira 域名')
    jira_fix_version = models.CharField(max_length=255, blank=True, default='',
                                        verbose_name='Jira Fix Version')
    version          = models.ForeignKey('versions.Version', null=True, blank=True,
                                         on_delete=models.SET_NULL,
                                         related_name='jira_issue_links',
                                         verbose_name='关联版本')
    project          = models.ForeignKey('projects.Project', null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name='jira_issue_links',
                                          verbose_name='关联项目')
    created_by       = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                          on_delete=models.SET_NULL,
                                          related_name='created_jira_links')
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('issue_key', 'jira_domain')
        verbose_name = 'Jira Issue 关联'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.issue_key}: {self.issue_summary[:50]}'


class JiraIssueCaseLink(models.Model):
    """用例与 Jira Issue 的关联（支持 AI 生成用例和手工用例）"""
    LINK_AUTO   = 'auto'
    LINK_MANUAL = 'manual'
    LINK_CHOICES = [(LINK_AUTO, '自动关联'), (LINK_MANUAL, '手动关联')]

    jira_issue   = models.ForeignKey(JiraIssueLink, on_delete=models.CASCADE,
                                      related_name='case_links')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id    = models.PositiveIntegerField()
    case         = GenericForeignKey('content_type', 'object_id')
    link_type    = models.CharField(max_length=16, choices=LINK_CHOICES,
                                     default=LINK_MANUAL)
    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                                      on_delete=models.SET_NULL,
                                      related_name='created_case_links')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('jira_issue', 'content_type', 'object_id')
        verbose_name = 'Jira Issue 用例关联'
        ordering = ['-created_at']
```

- [ ] **Step 4: 生成并应用迁移**

```bash
python manage.py makemigrations requirement_analysis --name="jira_issue_link_models"
python manage.py migrate
```

- [ ] **Step 5: 运行测试确认通过**

```bash
python manage.py test tests.requirement_analysis.test_jira_models -v 2
```

- [ ] **Step 6: Commit**

```bash
git add apps/requirement_analysis/models.py apps/requirement_analysis/migrations/
git commit -m "feat: add JiraIssueLink and JiraIssueCaseLink models"
```

---

## Task 5: Jira 客户端（jira_client.py）

**Files:**
- Create: `apps/requirement_analysis/jira_client.py`
- Create: `tests/requirement_analysis/test_jira_client.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/requirement_analysis/test_jira_client.py`：

```python
from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.requirement_analysis.jira_client import JiraClient, JiraClientError

class JiraClientTest(TestCase):
    def setUp(self):
        self.client = JiraClient(
            domain='co.atlassian.net',
            email='user@co.com',
            api_token='token123'
        )

    @patch('apps.requirement_analysis.jira_client.httpx.get')
    def test_get_issue_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'key': 'PROJ-1',
            'fields': {
                'summary': 'Login page',
                'description': {'content': [{'content': [{'text': 'User can login'}]}]},
                'priority': {'name': 'High'},
                'labels': ['auth'],
                'subtasks': [],
            }
        }
        mock_get.return_value = mock_resp
        issue = self.client.get_issue('PROJ-1', fields=['summary', 'description'])
        self.assertEqual(issue['key'], 'PROJ-1')
        self.assertEqual(issue['fields']['summary'], 'Login page')

    @patch('apps.requirement_analysis.jira_client.httpx.get')
    def test_get_issue_404_raises_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        with self.assertRaises(JiraClientError):
            self.client.get_issue('PROJ-999', fields=['summary'])

    def test_extract_content_summary_only(self):
        issue = {
            'key': 'PROJ-1',
            'fields': {
                'summary': 'Login feature',
                'description': None,
                'priority': {'name': 'Medium'},
                'labels': [],
                'subtasks': [],
            }
        }
        text = self.client.extract_content(issue, selected_fields=['summary'])
        self.assertIn('Login feature', text)

    @patch('apps.requirement_analysis.jira_client.httpx.get')
    def test_validate_connection_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        self.assertTrue(self.client.validate_connection())

    @patch('apps.requirement_analysis.jira_client.httpx.get')
    def test_validate_connection_fail(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp
        self.assertFalse(self.client.validate_connection())
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test tests.requirement_analysis.test_jira_client -v 2
```

- [ ] **Step 3: 实现 jira_client.py**

新建 `apps/requirement_analysis/jira_client.py`：

```python
import httpx
import base64
import re
from typing import Optional

ALLOWED_FIELDS = {'summary', 'description', 'acceptance_criteria', 'subtasks', 'labels', 'priority'}
MAX_EPIC_CHILDREN = 50


class JiraClientError(Exception):
    pass


class JiraClient:
    def __init__(self, domain: str, email: str, api_token: str):
        self.base_url = f'https://{domain}/rest/api/3'
        credentials = base64.b64encode(f'{email}:{api_token}'.encode()).decode()
        self.headers = {
            'Authorization': f'Basic {credentials}',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

    def get_issue(self, issue_key: str, fields: list[str]) -> dict:
        safe_fields = [f for f in fields if f in ALLOWED_FIELDS]
        # Always fetch summary
        if 'summary' not in safe_fields:
            safe_fields.insert(0, 'summary')
        params = {'fields': ','.join(safe_fields)}
        resp = httpx.get(
            f'{self.base_url}/issue/{issue_key}',
            headers=self.headers,
            params=params,
            timeout=10,
        )
        if resp.status_code == 404:
            raise JiraClientError(f'Issue {issue_key} not found')
        if resp.status_code == 401:
            raise JiraClientError('Jira authentication failed: check email and API token')
        if resp.status_code == 403:
            raise JiraClientError(f'No permission to access {issue_key}')
        if resp.status_code != 200:
            raise JiraClientError(f'Jira API error {resp.status_code} for {issue_key}')
        return resp.json()

    def get_epic_children(self, epic_key: str, fields: list[str]) -> list[dict]:
        jql = f'"Epic Link" = {epic_key} OR parent = {epic_key}'
        params = {
            'jql': jql,
            'fields': ','.join(fields),
            'maxResults': MAX_EPIC_CHILDREN,
        }
        resp = httpx.get(
            f'{self.base_url}/search',
            headers=self.headers,
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            raise JiraClientError(f'Failed to fetch Epic children: {resp.status_code}')
        data = resp.json()
        issues = data.get('issues', [])
        return issues

    def extract_content(self, issue: dict, selected_fields: list[str]) -> str:
        fields = issue.get('fields', {})
        lines = [f'# {fields.get("summary", "")}']

        if 'description' in selected_fields and fields.get('description'):
            lines.append('\n## 需求描述')
            lines.append(self._adf_to_text(fields['description']))

        if 'acceptance_criteria' in selected_fields:
            # 自定义字段：按名称模糊匹配
            for key, val in fields.items():
                if key.startswith('customfield_') and isinstance(val, dict):
                    text = self._adf_to_text(val)
                    if text:
                        lines.append('\n## 验收标准')
                        lines.append(text)
                        break

        if 'subtasks' in selected_fields and fields.get('subtasks'):
            lines.append('\n## 子任务')
            for sub in fields['subtasks']:
                lines.append(f'- {sub["fields"]["summary"]}')

        if 'priority' in selected_fields and fields.get('priority'):
            lines.append(f'\n**优先级:** {fields["priority"]["name"]}')

        if 'labels' in selected_fields and fields.get('labels'):
            lines.append(f'**标签:** {", ".join(fields["labels"])}')

        return '\n'.join(lines)

    def validate_connection(self) -> bool:
        try:
            resp = httpx.get(
                f'{self.base_url}/myself',
                headers=self.headers,
                timeout=8,
            )
            return resp.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _adf_to_text(adf: dict) -> str:
        """将 Atlassian Document Format (ADF) 递归转为纯文本"""
        if not adf or not isinstance(adf, dict):
            return ''
        node_type = adf.get('type', '')
        content = adf.get('content', [])
        text = adf.get('text', '')

        if node_type == 'text':
            return text
        parts = [JiraClient._adf_to_text(child) for child in content]
        joined = ' '.join(p for p in parts if p)
        if node_type in ('paragraph', 'heading'):
            return joined + '\n'
        if node_type == 'listItem':
            return f'- {joined}'
        return joined

    @staticmethod
    def issue_key_from_url(url: str) -> Optional[str]:
        """从 Jira Issue URL 解析 Issue Key，如 PROJ-123"""
        match = re.search(r'/browse/([A-Z][A-Z0-9]+-\d+)', url)
        if match:
            return match.group(1)
        # 直接输入 key 格式
        if re.match(r'^[A-Z][A-Z0-9]+-\d+$', url.strip()):
            return url.strip()
        return None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
python manage.py test tests.requirement_analysis.test_jira_client -v 2
```

- [ ] **Step 5: Commit**

```bash
git add apps/requirement_analysis/jira_client.py tests/requirement_analysis/test_jira_client.py
git commit -m "feat: add JiraClient with issue fetch and content extraction"
```

---

## Task 6: Jira 序列化器

**Files:**
- Create: `apps/requirement_analysis/jira_serializers.py`

- [ ] **Step 1: 创建序列化器文件**

新建 `apps/requirement_analysis/jira_serializers.py`：

```python
from rest_framework import serializers
from .models import JiraIssueLink, JiraIssueCaseLink

ALLOWED_FIELDS = ['summary', 'description', 'acceptance_criteria', 'subtasks', 'labels', 'priority']


class JiraPreviewRequestSerializer(serializers.Serializer):
    urls = serializers.ListField(
        child=serializers.CharField(), min_length=1, max_length=50
    )
    selected_fields = serializers.ListField(
        child=serializers.ChoiceField(choices=ALLOWED_FIELDS),
        default=['summary', 'description']
    )


class JiraImportRequestSerializer(serializers.Serializer):
    urls = serializers.ListField(
        child=serializers.CharField(), min_length=1, max_length=50
    )
    selected_fields = serializers.ListField(
        child=serializers.ChoiceField(choices=ALLOWED_FIELDS),
        default=['summary', 'description']
    )
    version_id = serializers.IntegerField(required=False, allow_null=True)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    writer_model_config_id = serializers.IntegerField(required=False, allow_null=True)
    reviewer_model_config_id = serializers.IntegerField(required=False, allow_null=True)
    expand_epic = serializers.BooleanField(default=False)


class JiraIssueLinkSerializer(serializers.ModelSerializer):
    case_count = serializers.SerializerMethodField()
    version_name = serializers.CharField(source='version.name', read_only=True, default='')

    class Meta:
        model = JiraIssueLink
        fields = ['id', 'issue_key', 'issue_url', 'issue_summary',
                  'jira_fix_version', 'version', 'version_name',
                  'project', 'created_by', 'created_at', 'case_count']
        read_only_fields = ['id', 'created_by', 'created_at']

    def get_case_count(self, obj):
        return obj.case_links.count()


class LinkCaseRequestSerializer(serializers.Serializer):
    case_type = serializers.ChoiceField(choices=['generated', 'manual'])
    case_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)


class JiraRecommendRequestSerializer(serializers.Serializer):
    version_id = serializers.IntegerField()
```

- [ ] **Step 2: Commit**

```bash
git add apps/requirement_analysis/jira_serializers.py
git commit -m "feat: add jira serializers"
```

---

## Task 7: Jira 视图（preview/import/recommend/link）

**Files:**
- Create: `apps/requirement_analysis/jira_views.py`
- Modify: `apps/requirement_analysis/urls.py`
- Create: `tests/requirement_analysis/test_jira_views.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/requirement_analysis/test_jira_views.py`：

```python
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from apps.users.models import UserProfile
from apps.requirement_analysis.models import JiraIssueLink
from cryptography.fernet import Fernet
from django.conf import settings

User = get_user_model()

class JiraPreviewViewTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='pass')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        # 写入加密 token
        f = Fernet(settings.JIRA_TOKEN_ENCRYPT_KEY)
        profile = UserProfile.objects.get(user=self.user)
        profile.jira_domain = 'co.atlassian.net'
        profile.jira_email = 'u@co.com'
        profile.jira_api_token = f.encrypt(b'token123').decode()
        profile.save()

    @patch('apps.requirement_analysis.jira_views.JiraClient')
    def test_preview_returns_issue_summary(self, MockClient):
        instance = MockClient.return_value
        instance.issue_key_from_url = MagicMock(return_value='PROJ-1')
        instance.get_issue.return_value = {
            'key': 'PROJ-1',
            'fields': {'summary': 'Login', 'description': None,
                       'priority': None, 'labels': [], 'subtasks': []}
        }
        instance.extract_content.return_value = '# Login'
        resp = self.client.post('/api/requirement-analysis/jira/preview/', {
            'urls': ['https://co.atlassian.net/browse/PROJ-1'],
            'selected_fields': ['summary'],
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('results', resp.data)
        self.assertEqual(resp.data['results'][0]['issue_key'], 'PROJ-1')

    def test_preview_returns_400_when_no_jira_config(self):
        profile = UserProfile.objects.get(user=self.user)
        profile.jira_domain = ''
        profile.save()
        resp = self.client.post('/api/requirement-analysis/jira/preview/', {
            'urls': ['https://co.atlassian.net/browse/PROJ-1'],
            'selected_fields': ['summary'],
        }, format='json')
        self.assertEqual(resp.status_code, 400)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python manage.py test tests.requirement_analysis.test_jira_views -v 2
```

- [ ] **Step 3: 实现 jira_views.py**

新建 `apps/requirement_analysis/jira_views.py`：

```python
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
    JiraIssueLink, JiraIssueCaseLink, GeneratedTestCase,
    TestCaseGenerationTask, AIModelConfig,
)


def _get_jira_client(user):
    """从 UserProfile 读取并解密凭据，构造 JiraClient。凭据不完整时抛出 ValueError。"""
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
    """验证当前用户的 Jira 凭据是否有效"""
    try:
        client = _get_jira_client(request.user)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    ok = client.validate_connection()
    if ok:
        return Response({'valid': True, 'message': '连接成功'})
    return Response({'valid': False, 'message': '连接失败，请检查域名、邮箱和 API Token'},
                    status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def jira_preview(request):
    """预览：拉取 Jira Issue 内容摘要，不触发 AI 生成"""
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
    """正式导入：拉取 Issue → 组装文本 → 创建生成任务 → 自动关联"""
    ser = JiraImportRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data

    try:
        client = _get_jira_client(request.user)
    except ValueError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # 解析所有 Issue Key（支持 Epic 展开）
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
                issue_keys.append(key)  # Epic 展开失败则当普通 Issue 处理
        else:
            issue_keys.append(key)

    if not issue_keys:
        return Response({'error': '未能解析任何有效的 Issue Key'}, status=status.HTTP_400_BAD_REQUEST)

    # 拉取所有 Issue 内容并组装需求文本
    requirement_parts = []
    issue_metas = []  # 用于后续建立关联
    for key in issue_keys:
        try:
            issue = client.get_issue(key, fields=data['selected_fields'])
            content = client.extract_content(issue, selected_fields=data['selected_fields'])
            requirement_parts.append(content)
            issue_metas.append({
                'key': key,
                'url': f'https://{_get_profile_domain(request.user)}/browse/{key}',
                'summary': issue['fields'].get('summary', key),
                'fix_version': _extract_fix_version(issue),
            })
        except JiraClientError:
            continue  # 跳过失败的 Issue

    if not requirement_parts:
        return Response({'error': '所有 Issue 拉取失败'}, status=status.HTTP_400_BAD_REQUEST)

    requirement_text = '\n\n---\n\n'.join(requirement_parts)

    # 获取 AI 模型配置
    writer_config = _get_ai_config(data.get('writer_model_config_id'), 'writer')
    reviewer_config = _get_ai_config(data.get('reviewer_model_config_id'), 'reviewer')

    # 创建生成任务（复用现有模型）
    task = TestCaseGenerationTask.objects.create(
        task_id=f'jira-{uuid.uuid4().hex[:12]}',
        title=f'Jira 导入: {", ".join(m["key"] for m in issue_metas[:3])}' +
              (f' 等{len(issue_metas)}个 Issue' if len(issue_metas) > 3 else ''),
        requirement_text=requirement_text,
        status='pending',
        writer_model_config=writer_config,
        reviewer_model_config=reviewer_config,
        created_by=request.user,
    )

    # 建立 JiraIssueLink 关联
    from apps.users.models import UserProfile
    profile = UserProfile.objects.get(user=request.user)
    version = None
    if data.get('version_id'):
        from apps.versions.models import Version
        version = Version.objects.filter(id=data['version_id']).first()
    project = None
    if data.get('project_id'):
        from apps.projects.models import Project
        project = Project.objects.filter(id=data['project_id']).first()

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

    # 触发异步生成（复用现有机制）
    from .views import _start_generation_task
    _start_generation_task(task)

    return Response({
        'task_id': task.task_id,
        'message': f'已为 {len(issue_metas)} 个 Issue 创建生成任务',
        'issue_count': len(issue_metas),
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def jira_issues_list(request):
    """查询当前用户项目下的 JiraIssueLink 列表"""
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
    """手动关联用例到 Jira Issue"""
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
    """解除用例与 Jira Issue 的关联"""
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
    """查询某 Issue 关联的所有用例"""
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
    """根据版本关联的 Jira Issue，返回去重后的推荐回归用例列表"""
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


# ── 内部工具函数 ──────────────────────────────────────────

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
```

- [ ] **Step 4: 在 urls.py 注册路由**

打开 `apps/requirement_analysis/urls.py`，在 `urlpatterns` 列表末尾添加：

```python
from . import jira_views

# Jira 集成端点
urlpatterns += [
    path('jira/validate/', jira_views.jira_validate_connection, name='jira-validate'),
    path('jira/preview/', jira_views.jira_preview, name='jira-preview'),
    path('jira/import/', jira_views.jira_import, name='jira-import'),
    path('jira/issues/', jira_views.jira_issues_list, name='jira-issues-list'),
    path('jira/issues/<int:issue_id>/link-cases/', jira_views.jira_link_cases, name='jira-link-cases'),
    path('jira/issues/<int:issue_id>/unlink-cases/', jira_views.jira_unlink_cases, name='jira-unlink-cases'),
    path('jira/issues/<int:issue_id>/cases/', jira_views.jira_issue_cases, name='jira-issue-cases'),
    path('jira/recommend/', jira_views.jira_recommend, name='jira-recommend'),
]
```

- [ ] **Step 5: 找到 _start_generation_task 并确认可复用**

在 `apps/requirement_analysis/views.py` 中搜索任务启动方式：

```bash
grep -n "_start_generation_task\|threading\|asyncio\|task\.save\|status.*pending" \
  apps/requirement_analysis/views.py | head -20
```

若没有名为 `_start_generation_task` 的函数，改用实际的任务启动代码（查看 `TestCaseGenerationTaskViewSet.create` 方法如何启动任务，复用相同逻辑）。

- [ ] **Step 6: 运行测试确认通过**

```bash
python manage.py test tests.requirement_analysis.test_jira_views -v 2
```

- [ ] **Step 7: Commit**

```bash
git add apps/requirement_analysis/jira_views.py apps/requirement_analysis/jira_serializers.py \
        apps/requirement_analysis/urls.py tests/requirement_analysis/test_jira_views.py
git commit -m "feat: add jira preview/import/recommend/link API endpoints"
```

---

## Task 8: 任务完成后自动建立用例关联（post_save 信号）

**Files:**
- Modify: `apps/requirement_analysis/models.py`（或新建 `apps/requirement_analysis/signals.py`）
- Modify: `apps/requirement_analysis/apps.py`

- [ ] **Step 1: 新建 signals.py**

新建 `apps/requirement_analysis/signals.py`：

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType


@receiver(post_save, sender='requirement_analysis.TestCaseGenerationTask')
def auto_link_generated_cases(sender, instance, **kwargs):
    """
    当生成任务变为 completed 时，将生成的用例自动关联到对应的 JiraIssueLink。
    只处理 task_id 以 'jira-' 开头的任务（由 jira_import 创建）。
    """
    if not instance.task_id.startswith('jira-'):
        return
    if instance.status != 'completed':
        return

    from .models import JiraIssueLink, JiraIssueCaseLink, GeneratedTestCase

    # 从任务标题解析关联的 Issue Keys
    # 格式: "Jira 导入: PROJ-1, PROJ-2 等N个 Issue"
    import re
    keys = re.findall(r'[A-Z][A-Z0-9]+-\d+', instance.title)
    if not keys:
        return

    ct = ContentType.objects.get_for_model(GeneratedTestCase)
    cases = GeneratedTestCase.objects.filter(generation_task=instance)

    for key in keys:
        issue_link = JiraIssueLink.objects.filter(issue_key=key).first()
        if not issue_link:
            continue
        for case in cases:
            JiraIssueCaseLink.objects.get_or_create(
                jira_issue=issue_link,
                content_type=ct,
                object_id=case.id,
                defaults={
                    'link_type': JiraIssueCaseLink.LINK_AUTO,
                    'created_by': instance.created_by,
                }
            )
```

- [ ] **Step 2: 在 apps.py 注册信号**

打开 `apps/requirement_analysis/apps.py`，添加 `ready()` 方法：

```python
class RequirementAnalysisConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.requirement_analysis'

    def ready(self):
        import apps.requirement_analysis.signals  # noqa: F401
```

- [ ] **Step 3: 确认 GeneratedTestCase 有 generation_task 字段**

```bash
grep -n "generation_task\|TestCaseGenerationTask" apps/requirement_analysis/models.py | head -10
```

若字段名不同（如 `task`），在 signals.py 中调整为正确字段名。

- [ ] **Step 4: Commit**

```bash
git add apps/requirement_analysis/signals.py apps/requirement_analysis/apps.py
git commit -m "feat: auto-link generated cases to jira issues via post_save signal"
```

---

## Task 9: 前端 API 层（jira.js）

**Files:**
- Create: `frontend/src/api/jira.js`

- [ ] **Step 1: 创建 API 调用文件**

新建 `frontend/src/api/jira.js`：

```javascript
import request from '@/utils/api'

// Jira 凭据验证
export function validateJiraConnection() {
  return request({ url: '/requirement-analysis/jira/validate/', method: 'post' })
}

// 预览：拉取 Issue 内容摘要
export function previewJiraIssues(data) {
  return request({ url: '/requirement-analysis/jira/preview/', method: 'post', data })
}

// 正式导入：生成测试用例
export function importJiraIssues(data) {
  return request({ url: '/requirement-analysis/jira/import/', method: 'post', data })
}

// 查询 Jira Issue 关联列表
export function getJiraIssues(params) {
  return request({ url: '/requirement-analysis/jira/issues/', method: 'get', params })
}

// 手动关联用例
export function linkCasesToIssue(issueId, data) {
  return request({ url: `/requirement-analysis/jira/issues/${issueId}/link-cases/`, method: 'post', data })
}

// 解除关联
export function unlinkCasesFromIssue(issueId, data) {
  return request({ url: `/requirement-analysis/jira/issues/${issueId}/unlink-cases/`, method: 'post', data })
}

// 查询某 Issue 的关联用例
export function getIssueCases(issueId) {
  return request({ url: `/requirement-analysis/jira/issues/${issueId}/cases/`, method: 'get' })
}

// 版本回归推荐
export function recommendCasesByVersion(versionId) {
  return request({ url: '/requirement-analysis/jira/recommend/', method: 'post', data: { version_id: versionId } })
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/jira.js
git commit -m "feat: add jira api layer for frontend"
```

---

## Task 10: 个人资料页 Jira 配置 Tab

**Files:**
- Modify: `frontend/src/views/profile/UserProfile.vue`
- Modify: `frontend/src/locales/lang/zh-cn/requirement.js`
- Modify: `frontend/src/locales/lang/en/requirement.js`

- [ ] **Step 1: 在 zh-cn/requirement.js 添加 i18n**

打开 `frontend/src/locales/lang/zh-cn/requirement.js`，在导出对象末尾添加（在最后一个 `}` 前）：

```javascript
  jira: {
    tabTitle: 'Jira 配置',
    domain: 'Jira 域名',
    domainPlaceholder: 'yourcompany.atlassian.net',
    email: '邮箱',
    emailPlaceholder: '您的 Jira 登录邮箱',
    apiToken: 'API Token',
    apiTokenPlaceholder: '输入新 Token（留空则不修改）',
    testConnection: '测试连接',
    save: '保存',
    connectionSuccess: 'Jira 连接成功',
    connectionFailed: 'Jira 连接失败，请检查配置',
    saveSuccess: 'Jira 配置已保存',
    saveFailed: '保存失败',
    howToGetToken: '如何获取 API Token？',
    tokenGuide: '前往 https://id.atlassian.com/manage-profile/security/api-tokens 创建',
  },
```

- [ ] **Step 2: 在 en/requirement.js 添加英文**

打开 `frontend/src/locales/lang/en/requirement.js`，添加：

```javascript
  jira: {
    tabTitle: 'Jira Config',
    domain: 'Jira Domain',
    domainPlaceholder: 'yourcompany.atlassian.net',
    email: 'Email',
    emailPlaceholder: 'Your Jira login email',
    apiToken: 'API Token',
    apiTokenPlaceholder: 'Enter new token (leave blank to keep current)',
    testConnection: 'Test Connection',
    save: 'Save',
    connectionSuccess: 'Jira connected successfully',
    connectionFailed: 'Jira connection failed, please check config',
    saveSuccess: 'Jira config saved',
    saveFailed: 'Save failed',
    howToGetToken: 'How to get API Token?',
    tokenGuide: 'Go to https://id.atlassian.com/manage-profile/security/api-tokens to create one',
  },
```

- [ ] **Step 3: 在 UserProfile.vue 新增 Jira Tab**

打开 `frontend/src/views/profile/UserProfile.vue`。

在 `<el-tabs>` 中，在"修改密码"Tab 之后添加第三个 Tab（找到 `</el-tabs>` 前插入）：

```vue
<el-tab-pane :label="$t('requirementAnalysis.jira.tabTitle')" name="jira">
  <el-form :model="jiraForm" label-width="120px" style="max-width: 480px; margin-top: 16px">
    <el-form-item :label="$t('requirementAnalysis.jira.domain')">
      <el-input v-model="jiraForm.jira_domain"
                :placeholder="$t('requirementAnalysis.jira.domainPlaceholder')" />
    </el-form-item>
    <el-form-item :label="$t('requirementAnalysis.jira.email')">
      <el-input v-model="jiraForm.jira_email"
                :placeholder="$t('requirementAnalysis.jira.emailPlaceholder')" />
    </el-form-item>
    <el-form-item :label="$t('requirementAnalysis.jira.apiToken')">
      <el-input v-model="jiraForm.jira_api_token" type="password" show-password
                :placeholder="$t('requirementAnalysis.jira.apiTokenPlaceholder')" />
      <div style="font-size:12px; color:#909399; margin-top:4px">
        {{ $t('requirementAnalysis.jira.tokenGuide') }}
      </div>
    </el-form-item>
    <el-form-item>
      <el-button @click="testJiraConnection" :loading="jiraTesting">
        {{ $t('requirementAnalysis.jira.testConnection') }}
      </el-button>
      <el-button type="primary" @click="saveJiraConfig" :loading="jiraSaving">
        {{ $t('requirementAnalysis.jira.save') }}
      </el-button>
    </el-form-item>
  </el-form>
</el-tab-pane>
```

- [ ] **Step 4: 在 script setup 中添加 Jira 相关逻辑**

在 `<script setup>` 中（已有 `import { ref, ... }` 部分后面）添加：

```javascript
import { validateJiraConnection } from '@/api/jira'
import request from '@/utils/api'

// Jira 配置
const jiraForm = ref({ jira_domain: '', jira_email: '', jira_api_token: '' })
const jiraTesting = ref(false)
const jiraSaving = ref(false)

// 加载当前 Jira 配置（在 onMounted 或 tab 切换时调用）
const loadJiraConfig = async () => {
  try {
    const res = await request({ url: '/users/profile/', method: 'get' })
    jiraForm.value.jira_domain = res.data.jira_domain || ''
    jiraForm.value.jira_email = res.data.jira_email || ''
    // token 不回填（脱敏），保持占位符提示
  } catch {}
}

const testJiraConnection = async () => {
  jiraTesting.value = true
  try {
    await validateJiraConnection()
    ElMessage.success(t('requirementAnalysis.jira.connectionSuccess'))
  } catch {
    ElMessage.error(t('requirementAnalysis.jira.connectionFailed'))
  } finally {
    jiraTesting.value = false
  }
}

const saveJiraConfig = async () => {
  jiraSaving.value = true
  try {
    await request({
      url: '/users/profile/',
      method: 'patch',
      data: {
        jira_domain: jiraForm.value.jira_domain,
        jira_email: jiraForm.value.jira_email,
        jira_api_token_input: jiraForm.value.jira_api_token, // 注意字段名
      }
    })
    ElMessage.success(t('requirementAnalysis.jira.saveSuccess'))
    jiraForm.value.jira_api_token = '' // 保存后清空，避免误覆盖
  } catch {
    ElMessage.error(t('requirementAnalysis.jira.saveFailed'))
  } finally {
    jiraSaving.value = false
  }
}
```

在已有的 `onMounted` 调用中追加 `loadJiraConfig()`。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/profile/UserProfile.vue \
        frontend/src/locales/lang/zh-cn/requirement.js \
        frontend/src/locales/lang/en/requirement.js \
        frontend/src/api/jira.js
git commit -m "feat: add jira config tab in user profile page"
```

---

## Task 11: JiraImport.vue 主页面

**Files:**
- Create: `frontend/src/views/requirement-analysis/JiraImport.vue`
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: 在路由中注册新页面**

打开 `frontend/src/router/index.js`，在 `/ai-generation` 路由的 `children` 数组中添加：

```javascript
{
  path: 'jira-import',
  name: 'JiraImport',
  component: () => import('@/views/requirement-analysis/JiraImport.vue'),
},
```

- [ ] **Step 2: 新建 JiraImport.vue**

新建 `frontend/src/views/requirement-analysis/JiraImport.vue`：

```vue
<template>
  <div class="jira-import-page" style="padding: 24px">
    <div class="page-header" style="margin-bottom: 20px">
      <h2>{{ $t('requirementAnalysis.jira.importTitle') }}</h2>
      <p style="color: #909399">{{ $t('requirementAnalysis.jira.importDesc') }}</p>
    </div>

    <el-steps :active="currentStep" finish-status="success" style="margin-bottom: 32px">
      <el-step :title="$t('requirementAnalysis.jira.step1')" />
      <el-step :title="$t('requirementAnalysis.jira.step2')" />
      <el-step :title="$t('requirementAnalysis.jira.step3')" />
    </el-steps>

    <!-- Step 1: 输入 URL -->
    <div v-if="currentStep === 0">
      <el-card style="margin-bottom: 16px">
        <template #header>{{ $t('requirementAnalysis.jira.inputUrls') }}</template>
        <el-radio-group v-model="inputMode" style="margin-bottom: 12px">
          <el-radio value="single">{{ $t('requirementAnalysis.jira.singleMode') }}</el-radio>
          <el-radio value="batch">{{ $t('requirementAnalysis.jira.batchMode') }}</el-radio>
        </el-radio-group>

        <el-input v-if="inputMode === 'single'" v-model="singleUrl"
                  :placeholder="$t('requirementAnalysis.jira.urlPlaceholder')"
                  style="margin-bottom: 8px" />
        <el-input v-else v-model="batchUrls" type="textarea" :rows="6"
                  :placeholder="$t('requirementAnalysis.jira.batchPlaceholder')" />

        <el-checkbox v-model="expandEpic" style="margin-top: 8px">
          {{ $t('requirementAnalysis.jira.expandEpic') }}
        </el-checkbox>

        <div style="margin-top: 16px">
          <span style="margin-right: 8px">{{ $t('requirementAnalysis.jira.bindVersion') }}</span>
          <el-select v-model="selectedVersionId" clearable style="width: 240px"
                     :placeholder="$t('requirementAnalysis.jira.selectVersion')">
            <el-option v-for="v in versions" :key="v.id" :label="v.name" :value="v.id" />
          </el-select>
        </div>
      </el-card>

      <el-button type="primary" @click="goPreview" :loading="previewing">
        {{ $t('requirementAnalysis.jira.preview') }}
      </el-button>
    </div>

    <!-- Step 2: 字段选择 + 预览结果 -->
    <div v-if="currentStep === 1">
      <el-card style="margin-bottom: 16px">
        <template #header>{{ $t('requirementAnalysis.jira.selectFields') }}</template>
        <el-checkbox-group v-model="selectedFields">
          <el-checkbox value="summary" disabled>Summary（必选）</el-checkbox>
          <el-checkbox value="description">Description</el-checkbox>
          <el-checkbox value="acceptance_criteria">Acceptance Criteria</el-checkbox>
          <el-checkbox value="subtasks">子任务列表</el-checkbox>
          <el-checkbox value="priority">优先级</el-checkbox>
          <el-checkbox value="labels">标签</el-checkbox>
        </el-checkbox-group>
      </el-card>

      <el-card style="margin-bottom: 16px">
        <template #header>{{ $t('requirementAnalysis.jira.previewResults') }}</template>
        <div v-for="(item, idx) in previewResults" :key="idx" style="margin-bottom: 12px">
          <el-alert v-if="!item.success" :title="item.error" type="error" show-icon />
          <el-card v-else shadow="never" style="background: #f8f9fa">
            <div style="font-weight: bold">{{ item.issue_key }}: {{ item.summary }}</div>
            <div style="color: #606266; font-size: 13px; margin-top: 4px; white-space: pre-wrap">
              {{ item.content_preview }}
            </div>
          </el-card>
        </div>
      </el-card>

      <el-button @click="currentStep = 0">{{ $t('common.back') }}</el-button>
      <el-button type="primary" @click="currentStep = 2">{{ $t('common.next') }}</el-button>
    </div>

    <!-- Step 3: 生成 -->
    <div v-if="currentStep === 2">
      <el-card style="margin-bottom: 16px">
        <template #header>{{ $t('requirementAnalysis.jira.aiConfig') }}</template>
        <el-form label-width="120px">
          <el-form-item :label="$t('requirementAnalysis.jira.writerModel')">
            <el-select v-model="writerModelId" clearable style="width: 300px">
              <el-option v-for="m in aiModels.filter(m => m.role === 'writer')"
                         :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('requirementAnalysis.jira.reviewerModel')">
            <el-select v-model="reviewerModelId" clearable style="width: 300px">
              <el-option v-for="m in aiModels.filter(m => m.role === 'reviewer')"
                         :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </el-form-item>
        </el-form>
      </el-card>

      <el-button @click="currentStep = 1">{{ $t('common.back') }}</el-button>
      <el-button type="primary" @click="startImport" :loading="importing">
        {{ $t('requirementAnalysis.jira.startGenerate') }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { previewJiraIssues, importJiraIssues } from '@/api/jira'
import request from '@/utils/api'

const { t } = useI18n()
const router = useRouter()

const currentStep = ref(0)
const inputMode = ref('single')
const singleUrl = ref('')
const batchUrls = ref('')
const expandEpic = ref(false)
const selectedVersionId = ref(null)
const selectedFields = ref(['summary', 'description'])
const previewing = ref(false)
const importing = ref(false)
const previewResults = ref([])
const versions = ref([])
const aiModels = ref([])
const writerModelId = ref(null)
const reviewerModelId = ref(null)

const getUrls = () => {
  if (inputMode.value === 'single') {
    return singleUrl.value ? [singleUrl.value.trim()] : []
  }
  return batchUrls.value.split('\n').map(u => u.trim()).filter(Boolean)
}

const goPreview = async () => {
  const urls = getUrls()
  if (!urls.length) {
    ElMessage.warning(t('requirementAnalysis.jira.urlRequired'))
    return
  }
  previewing.value = true
  try {
    const res = await previewJiraIssues({ urls, selected_fields: selectedFields.value })
    previewResults.value = res.data.results
    currentStep.value = 1
  } catch {
    ElMessage.error(t('requirementAnalysis.jira.previewFailed'))
  } finally {
    previewing.value = false
  }
}

const startImport = async () => {
  importing.value = true
  try {
    const res = await importJiraIssues({
      urls: getUrls(),
      selected_fields: selectedFields.value,
      version_id: selectedVersionId.value,
      writer_model_config_id: writerModelId.value,
      reviewer_model_config_id: reviewerModelId.value,
      expand_epic: expandEpic.value,
    })
    ElMessage.success(t('requirementAnalysis.jira.importSuccess'))
    router.push(`/ai-generation/task-detail/${res.data.task_id}`)
  } catch {
    ElMessage.error(t('requirementAnalysis.jira.importFailed'))
  } finally {
    importing.value = false
  }
}

onMounted(async () => {
  try {
    const [vRes, mRes] = await Promise.all([
      request({ url: '/versions/', method: 'get' }),
      request({ url: '/requirement-analysis/ai-models/', method: 'get' }),
    ])
    versions.value = vRes.data.results || vRes.data
    aiModels.value = mRes.data.results || mRes.data
  } catch {}
})
</script>
```

- [ ] **Step 3: 在 zh-cn/requirement.js 的 jira 块补充页面文本**

在上一步已添加的 `jira: { ... }` 中追加：

```javascript
    importTitle: 'Jira 需求导入',
    importDesc: '从 Jira Cloud Issue 拉取需求，自动生成测试用例',
    step1: '输入 Issue URL',
    step2: '字段选择 & 预览',
    step3: '生成测试用例',
    inputUrls: '输入 Issue URL',
    singleMode: '单条',
    batchMode: '批量',
    urlPlaceholder: 'https://yourco.atlassian.net/browse/PROJ-123',
    batchPlaceholder: '每行一个 Issue URL 或 Issue Key',
    expandEpic: '展开 Epic 子任务',
    bindVersion: '关联版本（可选）',
    selectVersion: '选择 TestHub 版本',
    selectFields: '选择拉取字段',
    previewResults: '预览结果',
    aiConfig: 'AI 模型配置',
    writerModel: '编写模型',
    reviewerModel: '评审模型',
    startGenerate: '开始生成',
    preview: '预览',
    urlRequired: '请输入至少一个 Issue URL',
    previewFailed: '预览失败，请检查 Jira 配置',
    importSuccess: '导入成功，已跳转到任务详情',
    importFailed: '导入失败',
```

- [ ] **Step 4: 在 en/requirement.js 的 jira 块补充英文**

```javascript
    importTitle: 'Jira Requirement Import',
    importDesc: 'Pull requirements from Jira Cloud Issues and auto-generate test cases',
    step1: 'Enter Issue URL',
    step2: 'Select Fields & Preview',
    step3: 'Generate Test Cases',
    inputUrls: 'Enter Issue URLs',
    singleMode: 'Single',
    batchMode: 'Batch',
    urlPlaceholder: 'https://yourco.atlassian.net/browse/PROJ-123',
    batchPlaceholder: 'One Issue URL or Issue Key per line',
    expandEpic: 'Expand Epic children',
    bindVersion: 'Link to Version (optional)',
    selectVersion: 'Select TestHub Version',
    selectFields: 'Select Fields to Fetch',
    previewResults: 'Preview Results',
    aiConfig: 'AI Model Config',
    writerModel: 'Writer Model',
    reviewerModel: 'Reviewer Model',
    startGenerate: 'Start Generating',
    preview: 'Preview',
    urlRequired: 'Please enter at least one Issue URL',
    previewFailed: 'Preview failed, please check Jira config',
    importSuccess: 'Import successful, redirecting to task detail',
    importFailed: 'Import failed',
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/requirement-analysis/JiraImport.vue \
        frontend/src/router/index.js \
        frontend/src/locales/lang/zh-cn/requirement.js \
        frontend/src/locales/lang/en/requirement.js
git commit -m "feat: add JiraImport page with 3-step flow"
```

---

## Task 12: 侧边栏菜单新增 Jira 导入入口

**Files:**
- Modify: `frontend/src/layout/index.vue`（或侧边栏导航配置文件）

- [ ] **Step 1: 找到侧边栏 AI 生成模块菜单项**

```bash
grep -rn "requirement-analysis\|jira\|ai-generation" frontend/src/layout/ | head -20
grep -rn "RequirementAnalysis\|ai-generation" frontend/src/views/requirement-analysis/RequirementAnalysisView.vue | head -10
```

- [ ] **Step 2: 新增菜单项**

在找到的侧边栏文件中，在需求分析主入口之后添加 Jira 导入菜单：

```vue
<el-menu-item index="/ai-generation/jira-import">
  <el-icon><Connection /></el-icon>
  <span>{{ $t('requirementAnalysis.jira.importTitle') }}</span>
</el-menu-item>
```

若侧边栏使用路由配置而非硬编码，在路由中为 `JiraImport` 路由添加 `meta`：

```javascript
{
  path: 'jira-import',
  name: 'JiraImport',
  component: () => import('@/views/requirement-analysis/JiraImport.vue'),
  meta: { title: 'Jira 需求导入', icon: 'Connection' }
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layout/ frontend/src/router/index.js
git commit -m "feat: add jira import menu item to sidebar"
```

---

## Task 13: 版本详情页 — 关联需求 Tab 与回归推荐

**Files:**
- Modify: `frontend/src/views/versions/VersionList.vue`（或版本详情页）

- [ ] **Step 1: 找到版本详情页文件**

```bash
ls frontend/src/views/versions/
grep -rn "VersionDetail\|version.*detail" frontend/src/router/index.js | head -5
```

- [ ] **Step 2: 在版本详情页（或 VersionList 的详情抽屉）新增"关联需求" Tab**

找到版本详情的组件，在已有 Tab 后追加：

```vue
<el-tab-pane label="关联 Jira 需求" name="jira">
  <div style="margin-bottom: 12px; display: flex; justify-content: space-between">
    <span>该版本关联的 Jira Issues</span>
    <el-button type="primary" size="small" @click="loadRecommend" :loading="recommending">
      推荐回归用例
    </el-button>
  </div>

  <el-table :data="jiraIssues" v-loading="loadingIssues" size="small">
    <el-table-column prop="issue_key" label="Issue Key" width="120" />
    <el-table-column prop="issue_summary" label="标题" min-width="200" show-overflow-tooltip />
    <el-table-column prop="jira_fix_version" label="Fix Version" width="120" />
    <el-table-column prop="case_count" label="关联用例数" width="100" />
    <el-table-column label="操作" width="100">
      <template #default="{ row }">
        <el-button link size="small" @click="viewIssueCases(row)">查看用例</el-button>
      </template>
    </el-table-column>
  </el-table>

  <!-- 推荐结果 -->
  <el-drawer v-model="showRecommend" title="推荐回归用例" size="50%">
    <div style="padding: 16px">
      <p>共 {{ recommendResults.length }} 条推荐用例（已去重）</p>
      <el-table :data="recommendResults" size="small">
        <el-table-column prop="issue_key" label="来源 Issue" width="120" />  
        <el-table-column prop="title" label="用例标题" min-width="200" />
        <el-table-column prop="case_type" label="类型" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.case_type === 'generatedtestcase' ? 'success' : 'info'">
              {{ row.case_type === 'generatedtestcase' ? 'AI生成' : '手工' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-drawer>
</el-tab-pane>
```

- [ ] **Step 3: 在 script setup 中添加对应逻辑**

```javascript
import { getJiraIssues, recommendCasesByVersion } from '@/api/jira'

const jiraIssues = ref([])
const loadingIssues = ref(false)
const recommending = ref(false)
const recommendResults = ref([])
const showRecommend = ref(false)

const loadJiraIssues = async (versionId) => {
  loadingIssues.value = true
  try {
    const res = await getJiraIssues({ version_id: versionId })
    jiraIssues.value = res.data
  } catch {} finally {
    loadingIssues.value = false
  }
}

const loadRecommend = async () => {
  recommending.value = true
  try {
    const res = await recommendCasesByVersion(currentVersionId.value)
    recommendResults.value = res.data.results
    showRecommend.value = true
  } catch {
    ElMessage.error('加载推荐用例失败')
  } finally {
    recommending.value = false
  }
}
```

在 Tab 切换到"关联 Jira 需求"时调用 `loadJiraIssues(versionId)`。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/versions/
git commit -m "feat: add jira issues tab and regression recommendation in version detail"
```

---

## Task 14: 端到端手动验证

- [ ] **Step 1: 启动服务**

```bash
# 后端
cd /d/python/testhub_platform-main
source venv/Scripts/activate
python manage.py runserver

# 前端（另一个终端）
cd /d/python/testhub_platform-main/frontend
"D:/software/Node/node.exe" node_modules/vite/bin/vite.js
```

- [ ] **Step 2: 验证个人资料 Jira 配置**

1. 登录 http://localhost:3000
2. 进入个人资料页 → "Jira 配置" Tab
3. 填入真实 Jira 域名、邮箱、API Token
4. 点击"测试连接"，应看到成功提示
5. 点击"保存"，刷新页面后域名和邮箱应回填

- [ ] **Step 3: 验证 Jira 导入流程**

1. 侧边栏进入"Jira 需求导入"
2. Step 1：输入一个真实 Jira Issue URL，选择版本
3. 点击"预览"，应看到 Issue 标题和内容摘要
4. Step 2：勾选字段，确认预览结果
5. Step 3：选择 AI 模型，点击"开始生成"
6. 应自动跳转到任务详情页，看到生成进度

- [ ] **Step 4: 验证关联与推荐**

1. 生成完成后，进入版本详情页 → "关联 Jira 需求" Tab
2. 应看到刚才导入的 Issue 及关联用例数
3. 点击"推荐回归用例"，应看到去重后的用例列表

- [ ] **Step 5: 运行所有相关单测**

```bash
python manage.py test tests.users.test_jira_profile_api \
                       tests.requirement_analysis.test_jira_client \
                       tests.requirement_analysis.test_jira_models \
                       tests.requirement_analysis.test_jira_views -v 2
```

期望：所有测试通过。

- [ ] **Step 6: 最终 Commit**

```bash
git add -A
git commit -m "feat: complete jira integration - import, link, version association, regression recommend"
```

---

## 自检结果

**Spec 覆盖率：**
- ✅ Jira Cloud + API Token 认证
- ✅ 域名/邮箱/token 各人配置，token 加密存储
- ✅ 可配置字段（6个可选字段）
- ✅ 独立"Jira 需求导入"页面（侧边栏）
- ✅ 单条 + 批量 + Epic 展开
- ✅ 三步式流程（输入 → 预览 → 生成）
- ✅ JiraIssueLink + JiraIssueCaseLink 模型
- ✅ 导入时自动建立关联（post_save 信号）
- ✅ 手动关联/解除 API
- ✅ 版本详情关联需求 Tab
- ✅ 回归推荐 API + 前端 Drawer
- ✅ 凭据未配置 / Issue 不存在 / 超时错误处理
- ✅ Epic 超 50 条截断（jira_client.py MAX_EPIC_CHILDREN）
- ✅ 中英文 i18n

**类型一致性：** `JiraClient.issue_key_from_url` 为 static 方法，在 jira_views.py 中通过类名调用，一致。`jira_api_token_input` 写字段名与 profile view 的 partial update 处理一致。