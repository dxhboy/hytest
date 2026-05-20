# Visibility: ApiProject + ui_automation TestSuite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 ApiProject 添加完整的可见性功能（all/private），并修复 ui_automation TestSuiteViewSet 存在的项目门控 bug。

**Architecture:** 后端分两条线：① 独立的 ui_automation bug 修复（单行 get_queryset 改动）；② ApiProject 新增 visibility 字段（模型→迁移→序列化器→视图集）。前端只改 ProjectManagement.vue（表单+对话框+表格+回填）。每条线独立可测试。

**Tech Stack:** Django 4.2 / Django REST Framework / Vue 3 / Element Plus

---

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `apps/ui_automation/views.py` | 修改 | TestSuiteViewSet.get_queryset 移除项目门控 |
| `apps/ui_automation/test_suite_visibility.py` | 新建 | ui_automation 可见性回归测试 |
| `apps/api_testing/models.py` | 修改 | ApiProject 加 visibility 字段 |
| `apps/api_testing/migrations/0005_add_visibility_to_apiproject.py` | 新建 | 迁移，存量数据 default='private' |
| `apps/api_testing/serializers.py` | 修改 | ApiProjectSerializer fields 加 visibility |
| `apps/api_testing/views.py` | 修改 | ApiProjectViewSet.get_queryset() 加 visibility 过滤 |
| `apps/api_testing/test_project_visibility.py` | 新建 | ApiProject 可见性回归测试 |
| `frontend/src/views/api-testing/ProjectManagement.vue` | 修改 | form + 对话框 + 表格列 + editProject 回填 |

---

## Task 1: 修复 ui_automation TestSuiteViewSet 项目门控 bug

**Files:**
- Test: `apps/ui_automation/test_suite_visibility.py`（新建）
- Modify: `apps/ui_automation/views.py:649-656`

- [ ] **Step 1: 新建测试文件（会失败）**

新建 `apps/ui_automation/test_suite_visibility.py`，写入以下内容：

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.ui_automation.models import UiProject, TestSuite

User = get_user_model()


class TestSuiteVisibilityTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='ui_owner', password='testpass123', email='ui_owner@test.com'
        )
        self.other = User.objects.create_user(
            username='ui_other', password='testpass123', email='ui_other@test.com'
        )
        self.project = UiProject.objects.create(
            name='Test UI Project',
            owner=self.owner,
            base_url='http://localhost',
        )
        self.suite = TestSuite.objects.create(
            name='Public Suite',
            project=self.project,
            created_by=self.owner,
            visibility='all',
        )

    def test_public_suite_visible_to_non_member(self):
        """visibility='all' 的套件对非项目成员应可见"""
        client = APIClient()
        client.force_authenticate(user=self.other)
        response = client.get('/api/ui-automation/test-suites/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        suite_ids = [s['id'] for s in results]
        self.assertIn(self.suite.id, suite_ids)

    def test_private_suite_hidden_from_non_creator(self):
        """visibility='private' 的套件对非创建者不可见"""
        private_suite = TestSuite.objects.create(
            name='Private Suite',
            project=self.project,
            created_by=self.owner,
            visibility='private',
        )
        client = APIClient()
        client.force_authenticate(user=self.other)
        response = client.get('/api/ui-automation/test-suites/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        suite_ids = [s['id'] for s in results]
        self.assertNotIn(private_suite.id, suite_ids)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd D:/python/testhub_platform-main && venv/Scripts/python.exe manage.py test apps.ui_automation.test_suite_visibility -v 2
```

期望输出：`test_public_suite_visible_to_non_member` FAIL（AssertionError，套件 ID 不在结果中）

- [ ] **Step 3: 修复 apps/ui_automation/views.py**

定位到 `apps/ui_automation/views.py` 第 649–656 行，将 `get_queryset` 方法替换为：

```python
    def get_queryset(self):
        user = self.request.user
        return TestSuite.objects.filter(
            models.Q(visibility='all') | models.Q(created_by=user)
        )
```

（删除原有的 `accessible_projects` 查询和 `project__in=` 前置门控）

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd D:/python/testhub_platform-main && venv/Scripts/python.exe manage.py test apps.ui_automation.test_suite_visibility -v 2
```

期望输出：2 tests, 0 failures

- [ ] **Step 5: 提交**

```bash
cd D:/python/testhub_platform-main && git add apps/ui_automation/views.py apps/ui_automation/test_suite_visibility.py && git commit -m "fix: 移除 ui_automation TestSuiteViewSet 的项目门控，修复 visibility=all 对非成员不可见的 bug"
```

---

## Task 2: ApiProject 模型加 visibility 字段 + 迁移

**Files:**
- Modify: `apps/api_testing/models.py`
- Create: `apps/api_testing/migrations/0005_add_visibility_to_apiproject.py`

- [ ] **Step 1: 修改 apps/api_testing/models.py**

在 `ApiProject` 类的 `members` 字段（第 29 行）之后、`created_at` 字段之前，插入以下字段定义：

```python
    visibility = models.CharField(
        max_length=10,
        choices=[('all', '所有人可见'), ('private', '仅自己可见')],
        default='all',
        verbose_name='可见性',
    )
```

修改后 `ApiProject` 字段顺序（第 22–32 行附近）应为：

```python
    name = models.CharField(max_length=200, verbose_name='项目名称')
    description = models.TextField(blank=True, verbose_name='项目描述')
    project_type = models.CharField(max_length=20, choices=PROJECT_TYPE_CHOICES, verbose_name='项目类型')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name='项目状态')
    start_date = models.DateField(null=True, blank=True, verbose_name='开始日期')
    end_date = models.DateField(null=True, blank=True, verbose_name='结束日期')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_api_projects', verbose_name='负责人')
    members = models.ManyToManyField(User, blank=True, related_name='api_projects', verbose_name='团队成员')
    visibility = models.CharField(
        max_length=10,
        choices=[('all', '所有人可见'), ('private', '仅自己可见')],
        default='all',
        verbose_name='可见性',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
```

- [ ] **Step 2: 手动创建迁移文件**

新建 `apps/api_testing/migrations/0005_add_visibility_to_apiproject.py`，写入以下完整内容：

```python
# Generated manually on 2026-04-10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api_testing', '0004_add_visibility_to_apirequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='apiproject',
            name='visibility',
            field=models.CharField(
                choices=[('all', '所有人可见'), ('private', '仅自己可见')],
                default='private',
                max_length=10,
                verbose_name='可见性',
            ),
        ),
    ]
```

> **注意**：迁移中用 `default='private'`，使存量项目记录保持原有的仅限 owner/members 可见语义；模型中 `default='all'` 供新建项目使用。

- [ ] **Step 3: 执行迁移**

```bash
cd D:/python/testhub_platform-main && venv/Scripts/python.exe manage.py migrate api_testing
```

期望输出：`Applying api_testing.0005_add_visibility_to_apiproject... OK`

- [ ] **Step 4: 提交**

```bash
cd D:/python/testhub_platform-main && git add apps/api_testing/models.py apps/api_testing/migrations/0005_add_visibility_to_apiproject.py && git commit -m "feat: ApiProject 模型添加 visibility 字段，迁移存量数据默认 private"
```

---

## Task 3: 更新序列化器、视图集，并验证

**Files:**
- Modify: `apps/api_testing/serializers.py:40-44`
- Modify: `apps/api_testing/views.py:112-116`
- Test: `apps/api_testing/test_project_visibility.py`（新建）

- [ ] **Step 1: 新建测试文件（会失败）**

新建 `apps/api_testing/test_project_visibility.py`，写入以下内容：

```python
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.api_testing.models import ApiProject

User = get_user_model()


class ApiProjectVisibilityTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='api_owner', password='testpass123', email='api_owner@test.com'
        )
        self.other = User.objects.create_user(
            username='api_other', password='testpass123', email='api_other@test.com'
        )
        self.public_project = ApiProject.objects.create(
            name='Public Project',
            project_type='HTTP',
            status='NOT_STARTED',
            owner=self.owner,
            visibility='all',
        )
        self.private_project = ApiProject.objects.create(
            name='Private Project',
            project_type='HTTP',
            status='NOT_STARTED',
            owner=self.owner,
            visibility='private',
        )

    def test_public_project_visible_to_non_member(self):
        """visibility='all' 的项目对非成员可见"""
        client = APIClient()
        client.force_authenticate(user=self.other)
        response = client.get('/api/api-testing/projects/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        project_ids = [p['id'] for p in results]
        self.assertIn(self.public_project.id, project_ids)

    def test_private_project_hidden_from_non_member(self):
        """visibility='private' 的项目对非成员不可见"""
        client = APIClient()
        client.force_authenticate(user=self.other)
        response = client.get('/api/api-testing/projects/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        project_ids = [p['id'] for p in results]
        self.assertNotIn(self.private_project.id, project_ids)

    def test_owner_sees_own_private_project(self):
        """owner 能看到自己的 private 项目"""
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.get('/api/api-testing/projects/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        results = data.get('results', data) if isinstance(data, dict) else data
        project_ids = [p['id'] for p in results]
        self.assertIn(self.private_project.id, project_ids)

    def test_visibility_field_in_response(self):
        """响应中应包含 visibility 字段"""
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.get(f'/api/api-testing/projects/{self.public_project.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('visibility', response.json())
        self.assertEqual(response.json()['visibility'], 'all')
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd D:/python/testhub_platform-main && venv/Scripts/python.exe manage.py test apps.api_testing.test_project_visibility -v 2
```

期望输出：至少 `test_public_project_visible_to_non_member` 和 `test_visibility_field_in_response` 失败（视图集还未改、序列化器还未加 visibility）

- [ ] **Step 3: 修改 apps/api_testing/serializers.py**

找到 `ApiProjectSerializer.Meta.fields`（第 40–44 行），在 `'end_date'` 之后、`'created_at'` 之前插入 `'visibility'`：

```python
        fields = [
            'id', 'name', 'description', 'project_type', 'status',
            'owner', 'members', 'member_ids', 'start_date', 'end_date',
            'visibility', 'created_at', 'updated_at'
        ]
```

- [ ] **Step 4: 修改 apps/api_testing/views.py**

找到 `ApiProjectViewSet.get_queryset()`（第 112–116 行），替换为：

```python
    def get_queryset(self):
        user = self.request.user
        return ApiProject.objects.filter(
            models.Q(visibility='all') |
            models.Q(owner=user) |
            models.Q(members=user)
        ).distinct()
```

- [ ] **Step 5: 运行测试，确认全部通过**

```bash
cd D:/python/testhub_platform-main && venv/Scripts/python.exe manage.py test apps.api_testing.test_project_visibility -v 2
```

期望输出：4 tests, 0 failures

- [ ] **Step 6: 提交**

```bash
cd D:/python/testhub_platform-main && git add apps/api_testing/serializers.py apps/api_testing/views.py apps/api_testing/test_project_visibility.py && git commit -m "feat: ApiProject 序列化器和视图集支持 visibility 过滤"
```

---

## Task 4: 前端 ProjectManagement.vue 添加可见性

**Files:**
- Modify: `frontend/src/views/api-testing/ProjectManagement.vue`

- [ ] **Step 1: form 对象加 visibility 字段**

定位第 327–336 行的 `const form = reactive({...})`，在 `member_ids: [],` 之后插入 `visibility: "all",`：

```javascript
const form = reactive({
  name: "",
  description: "",
  project_type: "HTTP",
  status: "NOT_STARTED",
  owner: null,
  member_ids: [],
  visibility: "all",
  start_date: "",
  end_date: "",
});
```

- [ ] **Step 2: editProject 函数中回填 visibility**

定位第 430–441 行的 `editProject` 函数，在 `form.end_date = project.end_date;` 之后插入：

```javascript
  form.visibility = project.visibility ?? 'all';
```

完整函数体如下：

```javascript
const editProject = (project) => {
  editingProject.value = project;
  form.name = project.name;
  form.description = project.description;
  form.project_type = project.project_type;
  form.status = project.status;
  form.owner = project.owner.id;
  form.member_ids = project.members.map((m) => m.id);
  form.start_date = project.start_date;
  form.end_date = project.end_date;
  form.visibility = project.visibility ?? 'all';
  showCreateDialog.value = true;
};
```

- [ ] **Step 3: 对话框中加可见性表单项**

定位到成员字段 `el-form-item`（约第 173–190 行，`prop="member_ids"` 的 `</el-form-item>` 之后），在它和开始日期 `el-form-item`（`prop="start_date"`）之间插入：

```html
        <el-form-item :label="$t('apiTesting.common.visibility')">
          <el-radio-group v-model="form.visibility">
            <el-radio value="all">{{ $t('apiTesting.common.visibleAll') }}</el-radio>
            <el-radio value="private">{{ $t('apiTesting.common.visibleSelf') }}</el-radio>
          </el-radio-group>
        </el-form-item>
```

- [ ] **Step 4: 表格加可见性列**

定位到操作列（第 66 行）`<el-table-column :label="$t('apiTesting.common.operation')" width="200">`，在该列之前插入：

```html
      <el-table-column :label="$t('apiTesting.common.visibility')" width="120">
        <template #default="scope">
          <el-tag
            :type="scope.row.visibility === 'all' ? 'primary' : 'info'"
            size="small"
          >
            {{ scope.row.visibility === 'all'
                ? $t('apiTesting.common.visibleAll')
                : $t('apiTesting.common.visibleSelf') }}
          </el-tag>
        </template>
      </el-table-column>
```

- [ ] **Step 5: 重置表单中加 visibility**

定位到 `resetForm` 或创建成功后的表单重置代码（约第 518 行，`member_ids: []` 附近），在 `member_ids: [],` 之后插入 `visibility: 'all',`。

先搜索重置代码块：

```bash
grep -n "member_ids: \[\]" D:/python/testhub_platform-main/frontend/src/views/api-testing/ProjectManagement.vue
```

找到所有 `member_ids: []` 出现位置，在每处之后加 `visibility: 'all',`。

- [ ] **Step 6: 提交**

```bash
cd D:/python/testhub_platform-main && git add frontend/src/views/api-testing/ProjectManagement.vue && git commit -m "feat: ProjectManagement.vue 添加可见性表单项、表格列和编辑回填"
```

---

## 自检结果

**Spec 覆盖：**
- ✅ ui_automation TestSuite bug fix → Task 1
- ✅ ApiProject model visibility field → Task 2 Step 1
- ✅ Migration default='private' → Task 2 Step 2
- ✅ Serializer add visibility → Task 3 Step 3
- ✅ ViewSet get_queryset → Task 3 Step 4
- ✅ Frontend form/dialog/table/backfill → Task 4

**类型一致性：** `visibility` 字段值在所有任务中统一为 `'all'` / `'private'` 字符串。
