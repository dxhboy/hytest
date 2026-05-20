# Move Request to Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在接口管理页左侧树右键菜单中，支持将单个或多个接口用例移动到指定集合（弹窗选集合，Ctrl 多选）。

**Architecture:** 后端新增 `PATCH /api/api-testing/requests/batch-move/` action，接收 request id 列表和目标 collection_id，批量更新 collection 外键。前端在 el-tree 上实现 Ctrl+Click 多选逻辑（selectedRequests ref），右键菜单增加"移动到集合"入口（仅 request 节点可见），点击后弹出集合选择 Dialog（el-tree 展示集合树，单选），确认后调接口并刷新树。

**Tech Stack:** Django REST Framework (action), Vue 3, Element Plus (el-tree, el-dialog), Axios

---

## Files

| 操作 | 文件 |
|------|------|
| Modify | `apps/api_testing/views.py` — 新增 `batch_move` action |
| Modify | `frontend/src/views/api-testing/InterfaceManagement.vue` — 多选逻辑、右键菜单、移动弹窗 |
| Modify | `frontend/src/locales/lang/zh-cn/api-testing.js` — 新增中文 key |
| Modify | `frontend/src/locales/lang/en/api-testing.js` — 新增英文 key |

---

## Task 1: 后端新增 batch_move action

**Files:**
- Modify: `apps/api_testing/views.py`（`ApiRequestViewSet` 类，在 `perform_destroy` 之后新增 action）

- [ ] **Step 1: 在 `ApiRequestViewSet` 中新增 `batch_move` action**

找到 `apps/api_testing/views.py` 中 `perform_destroy` 方法结束处（约第 1103 行），紧接其后插入：

```python
@action(detail=False, methods=['patch'], url_path='batch-move')
def batch_move(self, request):
    """批量移动接口到指定集合"""
    ids = request.data.get('ids', [])
    collection_id = request.data.get('collection_id')  # None 表示移到根（无集合）

    if not ids:
        return Response({'detail': '请提供要移动的接口 id 列表'}, status=400)

    # 只能操作自己有权限的用例
    qs = ApiRequest.objects.filter(
        id__in=ids
    ).filter(
        models.Q(visibility='all') | models.Q(created_by=request.user)
    )

    if collection_id is not None:
        try:
            collection = ApiCollection.objects.get(id=collection_id)
        except ApiCollection.DoesNotExist:
            return Response({'detail': '目标集合不存在'}, status=400)
        qs.update(collection=collection)
    else:
        qs.update(collection=None)

    return Response({'moved': qs.count()})
```

- [ ] **Step 2: 确认 `ApiCollection` 已在 views.py 顶部导入**

在 `apps/api_testing/views.py` 中搜索 `from .models import`，确认 `ApiCollection` 在导入列表中。若不在，将其添加到该导入行。

- [ ] **Step 3: 手动验证接口可访问**

启动后端：
```bash
cd /d/python/testhub_platform-main
source venv/Scripts/activate
python manage.py runserver
```

用 curl 或浏览器访问 `http://127.0.0.1:8000/api/api-testing/requests/batch-move/`，预期返回 405 Method Not Allowed（GET 不允许），说明路由注册成功。

- [ ] **Step 4: Commit**

```bash
git add apps/api_testing/views.py
git commit -m "feat: add batch_move action to ApiRequestViewSet"
```

---

## Task 2: 新增 i18n 翻译 key

**Files:**
- Modify: `frontend/src/locales/lang/zh-cn/api-testing.js`
- Modify: `frontend/src/locales/lang/en/api-testing.js`

- [ ] **Step 1: 在 zh-cn 的 contextMenu 对象中新增 key**

找到 `frontend/src/locales/lang/zh-cn/api-testing.js` 中：
```javascript
    contextMenu: {
      addRequest: "添加请求",
      addSubCollection: "添加子集合",
      clone: "克隆接口",
      edit: "编辑",
      delete: "删除",
    },
```
替换为：
```javascript
    contextMenu: {
      addRequest: "添加请求",
      addSubCollection: "添加子集合",
      clone: "克隆接口",
      edit: "编辑",
      delete: "删除",
      moveToCollection: "移动到集合",
    },
    moveDialog: {
      title: "移动到集合",
      selectTarget: "请选择目标集合",
      moveToRoot: "移动到根目录（无集合）",
      confirm: "确认移动",
      cancel: "取消",
      success: "移动成功",
      noSelection: "请选择目标集合",
      batchHint: "已选中 {count} 个接口",
    },
```

- [ ] **Step 2: 在 en 的 contextMenu 对象中新增 key**

找到 `frontend/src/locales/lang/en/api-testing.js` 中：
```javascript
    contextMenu: {
      addRequest: "Add Request",
      addSubCollection: "Add Sub-collection",
      clone: "Clone Interface",
      edit: "Edit",
      delete: "Delete",
    },
```
替换为：
```javascript
    contextMenu: {
      addRequest: "Add Request",
      addSubCollection: "Add Sub-collection",
      clone: "Clone Interface",
      edit: "Edit",
      delete: "Delete",
      moveToCollection: "Move to Collection",
    },
    moveDialog: {
      title: "Move to Collection",
      selectTarget: "Select target collection",
      moveToRoot: "Move to root (no collection)",
      confirm: "Confirm",
      cancel: "Cancel",
      success: "Moved successfully",
      noSelection: "Please select a target collection",
      batchHint: "{count} interface(s) selected",
    },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/locales/lang/zh-cn/api-testing.js frontend/src/locales/lang/en/api-testing.js
git commit -m "feat: add i18n keys for move-to-collection feature"
```

---

## Task 3: 前端多选状态与树节点样式

**Files:**
- Modify: `frontend/src/views/api-testing/InterfaceManagement.vue`

### 3A: 新增多选 ref 状态变量

- [ ] **Step 1: 在现有 ref 声明区域（约第 1904 行 `loading` 附近）新增以下变量**

```javascript
// 多选移动相关
const selectedRequests = ref([])  // 已选中的 request 节点数组
```

### 3B: 修改 el-tree 的 node-click 事件，支持 Ctrl+Click 多选

- [ ] **Step 2: 修改 `onNodeClick` 函数**

找到现有的 `onNodeClick` 函数（约第 2168 行），在函数体**最开头**插入多选处理逻辑：

```javascript
const onNodeClick = async (data, node, treeNode, event) => {
  // Ctrl+Click 多选（仅 request 节点）
  if (event && (event.ctrlKey || event.metaKey) && data.type === 'request') {
    const idx = selectedRequests.value.findIndex(r => r.id === data.id)
    if (idx === -1) {
      selectedRequests.value.push(data)
    } else {
      selectedRequests.value.splice(idx, 1)
    }
    return  // 不进入正常的单击详情逻辑
  }
  // 非 Ctrl 单击时清空多选
  if (data.type === 'request') {
    selectedRequests.value = []
  }
  // ... 原有逻辑保持不变（下方不需要改动）
```

注意：`onNodeClick` 原签名是 `(data)` 或 `(data, node, treeNode)`，需补全为 `(data, node, treeNode, event)` 并在 el-tree 的 `@node-click` 绑定处同步（el-tree 默认会透传 MouseEvent 作为第四参数，无需改 template）。

- [ ] **Step 3: 为选中节点添加高亮样式**

在 el-tree template 的 `<div class="tree-node">` 上添加动态 class：

找到（约第 78 行）：
```vue
              <div class="tree-node">
```
替换为：
```vue
              <div class="tree-node" :class="{ 'is-multi-selected': data.type === 'request' && selectedRequests.some(r => r.id === data.id) }">
```

在文件末尾样式区域添加：
```css
.tree-node.is-multi-selected {
  background-color: #ede9fe;
  border-radius: 4px;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/api-testing/InterfaceManagement.vue
git commit -m "feat: add ctrl+click multi-select for request nodes"
```

---

## Task 4: 右键菜单新增"移动到集合"入口

**Files:**
- Modify: `frontend/src/views/api-testing/InterfaceManagement.vue`

- [ ] **Step 1: 在右键菜单 ul 中增加移动入口**

找到（约第 1409 行）克隆菜单项：
```vue
      <li
        v-if="rightClickedNode && rightClickedNode.type === 'request'"
        @click="cloneRequestFromContext"
      >
        {{ $t("apiTesting.interface.contextMenu.clone") }}
      </li>
```
在其**后面**插入：
```vue
      <li
        v-if="rightClickedNode && rightClickedNode.type === 'request'"
        @click="openMoveDialog"
      >
        {{ $t("apiTesting.interface.contextMenu.moveToCollection") }}
      </li>
```

- [ ] **Step 2: 新增 `openMoveDialog` 函数**

在 `onNodeRightClick` 函数（约第 2255 行）之后插入：

```javascript
const showMoveDialog = ref(false)
const moveTargetCollectionId = ref(null)  // null = 移到根目录

const openMoveDialog = () => {
  showContextMenu.value = false
  // 若当前未多选，或多选中不含右键节点，则以右键节点为单选目标
  if (
    selectedRequests.value.length === 0 ||
    !selectedRequests.value.some(r => r.id === rightClickedNode.value?.id)
  ) {
    selectedRequests.value = rightClickedNode.value ? [rightClickedNode.value] : []
  }
  moveTargetCollectionId.value = null
  showMoveDialog.value = true
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/api-testing/InterfaceManagement.vue
git commit -m "feat: add move-to-collection entry in context menu"
```

---

## Task 5: 移动弹窗 Dialog

**Files:**
- Modify: `frontend/src/views/api-testing/InterfaceManagement.vue`

### 5A: Dialog 模板

- [ ] **Step 1: 在 `<!-- 数据工厂选择器 -->` 注释之前（约第 1423 行）插入弹窗 HTML**

```vue
    <!-- 移动到集合弹窗 -->
    <el-dialog
      v-model="showMoveDialog"
      :title="$t('apiTesting.interface.moveDialog.title')"
      width="400px"
      :close-on-click-modal="false"
    >
      <div style="margin-bottom: 12px; color: #606266; font-size: 13px;">
        {{ $t('apiTesting.interface.moveDialog.batchHint', { count: selectedRequests.length }) }}
      </div>
      <el-tree
        :data="collectionsOnlyTree"
        :props="treeProps"
        node-key="id"
        highlight-current
        :expand-on-click-node="false"
        @node-click="onMoveTargetSelect"
        style="max-height: 320px; overflow-y: auto;"
      />
      <div style="margin-top: 12px;">
        <el-checkbox v-model="moveToRoot">
          {{ $t('apiTesting.interface.moveDialog.moveToRoot') }}
        </el-checkbox>
      </div>
      <template #footer>
        <el-button @click="showMoveDialog = false">
          {{ $t('apiTesting.interface.moveDialog.cancel') }}
        </el-button>
        <el-button type="primary" :loading="moving" @click="confirmMove">
          {{ $t('apiTesting.interface.moveDialog.confirm') }}
        </el-button>
      </template>
    </el-dialog>
```

### 5B: computed 集合树（仅集合节点，过滤掉 request）

- [ ] **Step 2: 新增 `collectionsOnlyTree` computed**

在 `treeProps` 定义（约第 1889 行）之后新增：

```javascript
const collectionsOnlyTree = computed(() => {
  const filterRequests = (nodes) =>
    nodes
      .filter(n => n.type === 'collection')
      .map(n => ({ ...n, children: filterRequests(n.children || []) }))
  return filterRequests(collections.value)
})
```

### 5C: 弹窗交互逻辑

- [ ] **Step 3: 新增弹窗相关 ref 和函数**

紧接 `openMoveDialog` 函数之后插入：

```javascript
const moveToRoot = ref(false)
const moving = ref(false)

const onMoveTargetSelect = (data) => {
  if (moveToRoot.value) return
  moveTargetCollectionId.value = data.id
}

const confirmMove = async () => {
  if (!moveToRoot.value && moveTargetCollectionId.value === null) {
    ElMessage.warning(t('apiTesting.interface.moveDialog.noSelection'))
    return
  }
  const ids = selectedRequests.value.map(r => r.id)
  moving.value = true
  try {
    await api.patch('/api-testing/requests/batch-move/', {
      ids,
      collection_id: moveToRoot.value ? null : moveTargetCollectionId.value,
    })
    ElMessage.success(t('apiTesting.interface.moveDialog.success'))
    showMoveDialog.value = false
    selectedRequests.value = []
    moveTargetCollectionId.value = null
    moveToRoot.value = false
    await loadCollections(selectedProject.value)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '移动失败')
  } finally {
    moving.value = false
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/api-testing/InterfaceManagement.vue
git commit -m "feat: add move-to-collection dialog with batch support"
```

---

## Task 6: 端到端验证

- [ ] **Step 1: 启动前后端**

后端：
```bash
cd /d/python/testhub_platform-main && source venv/Scripts/activate && python manage.py runserver
```
前端：
```bash
cd /d/python/testhub_platform-main/frontend && "D:/software/Node/node.exe" node_modules/vite/bin/vite.js
```

- [ ] **Step 2: 验证单个移动**
  1. 打开 http://localhost:3000，进入接口管理页面
  2. 选择一个项目，展开集合树
  3. 右键某个接口节点 → 点击"移动到集合"
  4. 弹窗打开，标题显示"移动到集合"，提示"已选中 1 个接口"
  5. 在树中点击目标集合
  6. 点击"确认移动"
  7. 弹窗关闭，树刷新，接口出现在目标集合下

- [ ] **Step 3: 验证批量移动**
  1. Ctrl+Click 选中多个接口（节点背景变紫色）
  2. 右键其中任意一个 → 点击"移动到集合"
  3. 弹窗显示"已选中 N 个接口"
  4. 选目标集合 → 确认
  5. 所有选中接口出现在目标集合下

- [ ] **Step 4: 验证移到根目录**
  1. 右键一个有集合的接口 → 移动到集合
  2. 勾选"移动到根目录（无集合）"
  3. 确认 → 接口出现在树的顶层（不属于任何集合）

- [ ] **Step 5: 验证无集合可见性**
  - 若接口 visibility='private' 且不是当前用户创建的，后端 batch_move 会过滤掉，前端移动后数量不匹配属正常权限保护。

- [ ] **Step 6: 最终 commit（如有遗漏改动）**

```bash
git add -p
git commit -m "feat: move request to collection - e2e verified"
```
