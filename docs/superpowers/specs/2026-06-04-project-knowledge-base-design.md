# 项目知识库与 Skills 功能设计

**日期：** 2026-06-04
**状态：** 待实施

---

## 1. 背景与目标

TestHub 平台已支持从需求文档和 Jira issue 自动生成测试用例，但 AI 生成时缺乏项目专属上下文：

- 没有项目特有的测试规范和业务约束（Skills）
- 没有项目历史文档（需求规范、术语表等）可供参考

**目标：** 在配置中心新增「项目知识库」页面，支持按项目维护知识库文档和 Skills，并在生成测试用例时自动检索注入。

---

## 2. 用户故事

- 作为测试负责人，我可以为每个项目上传知识库文档（PDF/Word/Markdown），以便 AI 生成用例时参考项目背景
- 作为测试负责人，我可以为每个项目编写 Skills（Markdown 格式的测试规范），以便 AI 遵守项目约束
- 作为测试人员，当我触发需求或 Jira 生成时，AI 会自动检索知识库并应用 Skills，无需手动干预

---

## 3. 整体架构

```
配置中心
└── /configuration/knowledge-base     ← 新增路由
    ├── 顶部：项目选择下拉
    ├── Tab 1：知识库文档
    │   ├── 文件列表（名称/大小/状态/操作）
    │   └── 右上角「+ 上传文档」按钮
    └── Tab 2：Skills 配置
        ├── Markdown 编辑框
        └── 保存 / 预览按钮

AI 生成流程（需求 & Jira）
└── _build_knowledge_context(task)    ← 新增
    ├── 1. 查询 ProjectSkill → 追加到系统提示词末尾
    └── 2. 全文检索 KnowledgeDocument → 追加到用户消息前
```

---

## 4. 后端设计

### 4.1 新增模型（`apps/requirement_analysis/models.py`）

#### KnowledgeDocument

```python
class KnowledgeDocument(models.Model):
    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('processing', '处理中'),
        ('indexed', '已索引'),
        ('failed', '失败'),
    ]

    project      = models.ForeignKey('projects.Project', on_delete=models.CASCADE, related_name='knowledge_docs')
    name         = models.CharField(max_length=255)           # 原始文件名
    file         = models.FileField(upload_to='knowledge/')   # 文件存储路径
    file_size    = models.PositiveIntegerField(default=0)     # 字节数
    content_text = models.TextField(blank=True)               # 提取的全文（建 FULLTEXT 索引）
    chunks       = models.JSONField(default=list)             # 切分后的段落列表
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_msg    = models.TextField(blank=True)
    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def search(cls, query: str, project_id: int, top_k: int = 3) -> list[str]:
        """BM25 全文检索，返回最相关的 top_k 个段落。"""
        if not query or not query.strip():
            return []
        docs = cls.objects.filter(
            project_id=project_id,
            status='indexed'
        ).extra(
            where=["MATCH(content_text) AGAINST (%s IN BOOLEAN MODE)"],
            params=[query[:200]],       # 截取前 200 字符作查询词
            select={'relevance': "MATCH(content_text) AGAINST (%s IN BOOLEAN MODE)"},
            select_params=[query[:200]],
        ).order_by('-relevance')[:top_k]

        results = []
        for doc in docs:
            # 返回匹配度最高的段落（简单取前 500 字符）
            if doc.chunks:
                results.append(doc.chunks[0])
            elif doc.content_text:
                results.append(doc.content_text[:500])
        return results
```

**迁移：** 对 `content_text` 字段额外执行 `ALTER TABLE ... ADD FULLTEXT INDEX`（在迁移文件中用 `RunSQL` 实现）。

#### ProjectSkill

```python
class ProjectSkill(models.Model):
    project    = models.OneToOneField('projects.Project', on_delete=models.CASCADE, related_name='skill')
    content    = models.TextField(blank=True)     # Markdown 格式的 Skills 内容
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    updated_at = models.DateTimeField(auto_now=True)
```

### 4.2 文档处理流程

上传文件后，异步处理（Django management command 或直接同步处理，视文件大小）：

1. 根据文件扩展名提取纯文本：
   - `.pdf` → `pdfminer.six`
   - `.docx` → `python-docx`
   - `.md` / `.txt` → 直接读取
2. 按段落切分（以双换行为分隔，超过 500 字符则硬切），存入 `chunks` JSONField
3. 将全文存入 `content_text`
4. 状态更新为 `indexed`；失败则写入 `error_msg`，状态为 `failed`

### 4.3 新增 API 端点（`apps/requirement_analysis/`）

新建 `knowledge_views.py`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/requirement-analysis/knowledge/documents/` | 列出项目知识库文档（`?project_id=`） |
| POST | `/requirement-analysis/knowledge/documents/` | 上传文档（multipart） |
| DELETE | `/requirement-analysis/knowledge/documents/{id}/` | 删除文档 |
| GET | `/requirement-analysis/knowledge/skill/` | 获取项目 Skills（`?project_id=`） |
| PUT | `/requirement-analysis/knowledge/skill/` | 保存项目 Skills |

### 4.4 生成时上下文注入

在 `AIModelService`（`apps/requirement_analysis/models.py`）中，修改 `generate_test_cases` 和 `generate_test_cases_stream` 方法，在组装 messages 之前调用：

```python
def _build_knowledge_context(self, task) -> tuple[str, str]:
    """
    返回 (extra_system, extra_user)：
    - extra_system 追加到系统提示词末尾
    - extra_user   前置到用户消息前
    """
    extra_system = ""
    extra_user = ""

    # 1. Skills 注入
    if task.project_id:
        skill = ProjectSkill.objects.filter(project_id=task.project_id).first()
        if skill and skill.content.strip():
            extra_system = "\n\n## 项目测试规范\n" + skill.content

    # 2. 知识库检索
    if task.project_id and task.requirement_text:
        chunks = KnowledgeDocument.search(
            query=task.requirement_text,
            project_id=task.project_id,
            top_k=3
        )
        if chunks:
            extra_user = "## 参考知识库\n" + "\n---\n".join(chunks) + "\n\n"

    return extra_system, extra_user
```

注入点：

```python
system_content = writer_prompt + extra_system
user_content   = extra_user + "请深入分析以下需求文档...\n" + task.requirement_text
```

Jira 导入（`jira_views.py`）在创建 `TestCaseGenerationTask` 时已绑定 `project_id`，无需额外改动，复用同一路径。

---

## 5. 前端设计

### 5.1 新增路由（`frontend/src/router/index.js`）

```js
{
  path: 'knowledge-base',
  name: 'ConfigKnowledgeBase',
  component: () => import('@/views/configuration/KnowledgeBase.vue'),
  meta: { title: '项目知识库' }
}
```

同时在配置中心侧边栏 / 菜单中添加「项目知识库」入口。

### 5.2 KnowledgeBase.vue 结构

```
<顶部>
  项目选择器（el-select，联动下方内容）

<el-tabs>
  Tab 1：知识库文档
    - el-table：文件名 / 大小 / 状态（el-tag） / 删除按钮
    - 右上角「+ 上传文档」→ el-upload（accept=".pdf,.docx,.md,.txt"，limit 20MB）
    - 上传后轮询状态直到 indexed / failed

  Tab 2：Skills 配置
    - 说明文字（该内容将追加到 AI 提示词中）
    - el-input type="textarea"（Markdown 编辑，autosize）
    - 右下角「预览」（el-dialog 渲染 Markdown）+ 「保存」按钮
    - 最后保存时间提示
```

### 5.3 新增 API 服务（`frontend/src/api/knowledge.js`）

```js
export const getKnowledgeDocs  = (projectId) => ...
export const uploadKnowledgeDoc = (projectId, file) => ...
export const deleteKnowledgeDoc = (id) => ...
export const getProjectSkill   = (projectId) => ...
export const saveProjectSkill  = (projectId, content) => ...
```

### 5.4 i18n

在 `zh-cn/` 和 `en/` 的 `requirement.js`（或新建 `knowledge.js`）中新增对应翻译 key。

---

## 6. 不在本次范围内

- 向量语义检索（RAG）：现有 MySQL 全文检索已满足需求，后续可升级
- 知识库文档的版本管理
- 跨项目共享知识库
- 文档预览（在线查看 PDF/Word 内容）

---

## 7. 依赖

后端新增 Python 包：
- `pdfminer.six`：PDF 文本提取
- `python-docx`：Word 文本提取（项目可能已安装，需确认）

前端无新增依赖（使用现有 Element Plus 组件）。
