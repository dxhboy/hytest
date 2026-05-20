# 可见性功能扩展设计文档

**日期**: 2026-04-10  
**状态**: 已审批  
**目标**: 为 ApiProject（接口测试项目）添加可见性功能；修复 ui_automation TestSuite 的可见性 bug

---

## 背景

项目中已有 5 个模型实现了 `visibility='all'/'private'` 模式（TestSuite/ScheduledTask in api_testing、TestSuite/UiScheduledTask in ui_automation），但：
1. `ApiProject` 没有 visibility 字段，只能通过 owner/members 控制访问
2. `ui_automation TestSuiteViewSet.get_queryset()` 存在项目门控 bug（与今天修复的 api_testing 系列同款），导致 `visibility='all'` 的套件对非项目成员不可见

---

## 一、ui_automation TestSuite bug 修复

**文件**：`apps/ui_automation/views.py:649`

**根因**：`get_queryset` 先按项目成员资格过滤，再按 visibility 过滤，两层 AND 导致 visibility='all' 被项目门控提前拦截。

**修复**：移除项目门控，与其他模块统一：

```python
# 修复前
return TestSuite.objects.filter(project__in=accessible_projects).filter(
    Q(visibility='all') | Q(created_by=user)
)

# 修复后
return TestSuite.objects.filter(
    Q(visibility='all') | Q(created_by=user)
)
```

---

## 二、ApiProject visibility 功能

### 2.1 后端

#### 模型（`apps/api_testing/models.py`）

在 `ApiProject` 类添加字段：

```python
visibility = models.CharField(
    max_length=10,
    choices=[('all', '所有人可见'), ('private', '仅自己可见')],
    default='all',
    verbose_name='可见性',
)
```

#### 数据库迁移

- 新建迁移文件：`apps/api_testing/migrations/00XX_add_visibility_to_apiproject.py`
- 存量数据迁移默认值：`'private'`（保留现有 owner/members 权限语义）
- 新建记录默认值：`'all'`（model 层 `default='all'`）

#### 序列化器（`apps/api_testing/serializers.py`）

`ApiProjectSerializer` 的 `fields` 列表添加 `'visibility'`。

#### 视图（`apps/api_testing/views.py`）

`ApiProjectViewSet.get_queryset()` 改为：

```python
def get_queryset(self):
    user = self.request.user
    return ApiProject.objects.filter(
        models.Q(visibility='all') |
        models.Q(owner=user) |
        models.Q(members=user)
    ).distinct()
```

语义：
- `visibility='all'`：所有登录用户可见（无需是项目成员）
- `visibility='private'`：仅 owner 和 members 可见（保留原有行为）

### 2.2 前端（`ProjectManagement.vue`）

#### ① form 数据对象（新增默认值）

```javascript
const form = reactive({
  name: "",
  description: "",
  project_type: "HTTP",
  status: "NOT_STARTED",
  owner: null,
  member_ids: [],
  start_date: "",
  end_date: "",
  visibility: "all",   // 新增
});
```

#### ② 新建/编辑 dialog 表单项

在成员字段（`member_ids`）之后、开始日期之前插入：

```html
<el-form-item :label="$t('apiTesting.common.visibility')">
  <el-radio-group v-model="form.visibility">
    <el-radio value="all">{{ $t('apiTesting.common.visibleAll') }}</el-radio>
    <el-radio value="private">{{ $t('apiTesting.common.visibleSelf') }}</el-radio>
  </el-radio-group>
</el-form-item>
```

i18n key 已存在：`apiTesting.common.visibility/visibleAll/visibleSelf`，无需新增翻译。

#### ③ 项目列表表格新增可见性列

在操作列前插入：

```html
<el-table-column :label="$t('apiTesting.common.visibility')" width="120">
  <template #default="scope">
    <el-tag :type="scope.row.visibility === 'all' ? 'primary' : 'info'" size="small">
      {{ scope.row.visibility === 'all'
          ? $t('apiTesting.common.visibleAll')
          : $t('apiTesting.common.visibleSelf') }}
    </el-tag>
  </template>
</el-table-column>
```

#### ④ 编辑时回填 visibility

在 `openEditDialog` 中补充：

```javascript
form.visibility = project.visibility ?? 'all';
```

---

## 变更文件清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `apps/api_testing/models.py` | 修改 | ApiProject 加 visibility 字段 |
| `apps/api_testing/migrations/00XX_...` | 新建 | 存量数据 default='private' |
| `apps/api_testing/serializers.py` | 修改 | ApiProjectSerializer fields 加 visibility |
| `apps/api_testing/views.py` | 修改 | ApiProjectViewSet.get_queryset() |
| `apps/ui_automation/views.py` | 修改 | TestSuiteViewSet.get_queryset() |
| `frontend/src/views/api-testing/ProjectManagement.vue` | 修改 | form + 表单项 + 表格列 + 编辑回填 |

---

## 不在范围内

- ApiCollection、ApiRequest 的项目级联权限不变（仍依赖 ApiProject 的 owner/members）
- 不修改"所有人可见"项目的写权限（添加/修改用例仍需是项目成员）
- ui_automation 以外的模块不涉及
