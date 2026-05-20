# Swagger API 文档优化设计

**日期**: 2026-04-10  
**状态**: 已审批  
**目标**: 让 `/api/docs/` Swagger UI 可用，并支持中英文分组标签随系统语言切换

---

## 背景

项目已集成 `drf-spectacular`，`/api/docs/` 和 `/api/redoc/` 路由已存在，但：
- 无任何 `@extend_schema` 注解，所有接口无中文描述
- Swagger UI 中接口全部堆叠，无模块分组
- 语言无法跟随前端 i18n 设置切换

目标：**不修改任何 views.py / serializers.py**，仅通过 Hook + 自定义模板实现按模块分组 + 中英双语标签。

---

## 架构

```
用户打开 /api/docs/
    → LangAwareSwaggerView 渲染自定义模板 swagger_ui_lang.html
    → 模板 JS 读取 localStorage["app-lang"]（"zh-cn" 或 "en"）
    → 请求 /api/schema/?lang=zh-cn（或 en）
    → auto_tag_hook 读取 lang 参数，写入对应语言的 tags
    → Swagger UI 显示分组后的中文或英文接口文档
```

---

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/schema_hooks.py` | 新建 | 双语标签映射 + postprocessing hook |
| `backend/schema_views.py` | 新建 | 继承 SpectacularSwaggerView 的自定义 View |
| `templates/swagger_ui_lang.html` | 新建 | 自定义 Swagger UI 模板（读 localStorage） |
| `backend/settings.py` | 修改 | 更新 SPECTACULAR_SETTINGS，注册 hook，添加 TEMPLATES dirs |
| `backend/urls.py` | 修改 | 将 `api/docs/` 路由指向 LangAwareSwaggerView |

---

## 详细设计

### 1. `backend/schema_hooks.py`

双语标签映射表（有序列表，越具体的 URL 前缀越靠前）：

| URL 前缀 | 中文标签 | 英文标签 |
|----------|----------|----------|
| `/api/auth/` | 用户认证 | Authentication |
| `/api/users/` | 用户管理 | User Management |
| `/api/projects/` | 项目管理 | Projects |
| `/api/testcases/` | 测试用例 | Test Cases |
| `/api/testsuites/` | 测试套件 | Test Suites |
| `/api/executions/` | 测试执行 | Executions |
| `/api/reports/` | 测试报告 | Reports |
| `/api/reviews/` | 评审管理 | Reviews |
| `/api/versions/` | 版本管理 | Versions |
| `/api/assistant/` | AI助手 | AI Assistant |
| `/api/requirement-analysis/` | 需求分析 | Requirement Analysis |
| `/api/ui-automation/` | UI自动化 | UI Automation |
| `/api/data-factory/` | 数据工厂 | Data Factory |
| `/api/core/` | 核心功能 | Core |
| `/api/` | 接口测试 | API Testing |

`auto_tag_hook(result, generator, request, public)` 函数逻辑：
1. 读取 `request.GET.get('lang', 'zh-cn')`（request 可能为 None，默认 zh-cn）
2. 选择对应语言的映射表
3. 遍历 `result['paths']`，对每条 operation：若无 `tags`，按最具体前缀匹配，写入 `tags`
4. 返回修改后的 result

### 2. `backend/schema_views.py`

```python
from drf_spectacular.views import SpectacularSwaggerView

class LangAwareSwaggerView(SpectacularSwaggerView):
    template_name = 'swagger_ui_lang.html'
```

继承标准 View，仅替换模板，其余鉴权/配置逻辑不变。

### 3. `templates/swagger_ui_lang.html`

基于 drf-spectacular 默认 Swagger UI 模板结构，核心改动：

将 SwaggerUI 初始化脚本中的 `url` 参数替换为动态计算值：

```javascript
const lang = localStorage.getItem('app-lang') || 'zh-cn';
const ui = SwaggerUIBundle({
  url: '/api/schema/?lang=' + lang,
  dom_id: '#swagger-ui',
  presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
  layout: 'StandaloneLayout',
  deepLinking: true,
  persistAuthorization: true,
  displayOperationId: false,
});
```

同时引入 Swagger UI 所需的 CSS/JS（复用 drf-spectacular 默认 CDN 链接）。

### 4. `backend/settings.py` — SPECTACULAR_SETTINGS

```python
SPECTACULAR_SETTINGS = {
    'TITLE': 'TestHub API',
    'DESCRIPTION': 'AI 驱动的测试管理平台 API 文档',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
        'backend.schema_hooks.auto_tag_hook',
    ],
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayOperationId': False,
    },
}
```

在 `TEMPLATES[0]['DIRS']` 中添加项目根目录下的 `templates/` 目录，确保自定义模板可被 Django 发现。

### 5. `backend/urls.py`

```python
from backend.schema_views import LangAwareSwaggerView

# 替换原有路由：
path('api/docs/', LangAwareSwaggerView.as_view(), name='swagger-ui'),
```

`/api/redoc/` 保持不变。

---

## 边界情况

| 情况 | 处理方式 |
|------|----------|
| `localStorage["app-lang"]` 不存在 | 默认 `zh-cn` |
| `lang` 参数值不是 zh-cn/en | 默认 `zh-cn` |
| hook 中 `request` 为 None（CLI 生成 schema 时）| 默认 `zh-cn` |
| 某接口已有 `tags`（未来手动标注时）| Hook 不覆盖，跳过 |

---

## 不在范围内

- 添加接口参数描述、请求/响应示例（后续可按模块逐步添加 `@extend_schema`）
- ReDoc 页面语言切换（与 Swagger UI 复用同一 schema，tag 已同步，但 ReDoc 页面本身无 JS 注入）
