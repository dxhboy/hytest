# Swagger API 文档优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `/api/docs/` Swagger UI 按模块分组显示，并随前端 i18n 设置自动切换中英文标签

**Architecture:** 新建 `backend/schema_hooks.py` 提供双语标签后处理 Hook；新建 `templates/drf_spectacular/swagger_ui_lang.js` 替换默认 JS，从 `localStorage['app-lang']` 读取语言并动态拼接 schema URL；新建 `backend/schema_views.py` 继承 `SpectacularSwaggerView` 并切换到自定义 JS 模板；修改 `settings.py` 注册 Hook 并添加模板目录；修改 `urls.py` 替换 Swagger UI 路由

**Tech Stack:** Django 4.2, drf-spectacular, Swagger UI (CDN)

---

## 文件清单

| 文件 | 操作 |
|------|------|
| `backend/schema_hooks.py` | 新建 |
| `backend/schema_views.py` | 新建 |
| `templates/drf_spectacular/swagger_ui_lang.js` | 新建 |
| `backend/settings.py` | 修改 `SPECTACULAR_SETTINGS` + `TEMPLATES[0]['DIRS']` |
| `backend/urls.py` | 修改 `api/docs/` 路由 |

---

## Task 1: 创建双语标签 Hook

**Files:**
- Create: `backend/schema_hooks.py`
- Create: `tests/test_schema_hooks.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/test_schema_hooks.py`（若 `tests/` 目录不存在，先建）：

```python
# tests/test_schema_hooks.py
import pytest
from unittest.mock import MagicMock


def make_request(lang='zh-cn'):
    req = MagicMock()
    req.GET.get.side_effect = lambda key, default=None: lang if key == 'lang' else default
    return req


def make_result(*paths):
    return {'paths': {p: {'get': {}} for p in paths}}


def test_zh_tags_applied():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/projects/', '/api/testcases/')
    out = auto_tag_hook(result, None, make_request('zh-cn'), False)
    assert out['paths']['/api/projects/']['get']['tags'] == ['项目管理']
    assert out['paths']['/api/testcases/']['get']['tags'] == ['测试用例']


def test_en_tags_applied():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/projects/', '/api/testcases/')
    out = auto_tag_hook(result, None, make_request('en'), False)
    assert out['paths']['/api/projects/']['get']['tags'] == ['Projects']
    assert out['paths']['/api/testcases/']['get']['tags'] == ['Test Cases']


def test_existing_tags_not_overwritten():
    from backend.schema_hooks import auto_tag_hook
    result = {'paths': {'/api/projects/': {'get': {'tags': ['Custom']}}}}
    out = auto_tag_hook(result, None, make_request('zh-cn'), False)
    assert out['paths']['/api/projects/']['get']['tags'] == ['Custom']


def test_none_request_defaults_to_zh():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/users/')
    out = auto_tag_hook(result, None, None, False)
    assert out['paths']['/api/users/']['get']['tags'] == ['用户管理']


def test_unknown_lang_defaults_to_zh():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/executions/')
    out = auto_tag_hook(result, None, make_request('fr'), False)
    assert out['paths']['/api/executions/']['get']['tags'] == ['测试执行']


def test_api_testing_fallback():
    from backend.schema_hooks import auto_tag_hook
    result = make_result('/api/environments/')
    out = auto_tag_hook(result, None, make_request('zh-cn'), False)
    assert out['paths']['/api/environments/']['get']['tags'] == ['接口测试']


def test_multiple_methods_all_tagged():
    from backend.schema_hooks import auto_tag_hook
    result = {'paths': {'/api/projects/': {'get': {}, 'post': {}}}}
    out = auto_tag_hook(result, None, make_request('zh-cn'), False)
    assert out['paths']['/api/projects/']['get']['tags'] == ['项目管理']
    assert out['paths']['/api/projects/']['post']['tags'] == ['项目管理']
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd D:/python/testhub_platform-main
venv/Scripts/python.exe -m pytest tests/test_schema_hooks.py -v
```

期望输出：`ModuleNotFoundError: No module named 'backend.schema_hooks'`

- [ ] **Step 3: 创建 `backend/schema_hooks.py`**

```python
# backend/schema_hooks.py

# 有序映射：越具体的前缀越靠前，/api/ 兜底放最后
_TAG_MAP = [
    ('/api/auth/',                 '用户认证',  'Authentication'),
    ('/api/users/',                '用户管理',  'User Management'),
    ('/api/projects/',             '项目管理',  'Projects'),
    ('/api/testcases/',            '测试用例',  'Test Cases'),
    ('/api/testsuites/',           '测试套件',  'Test Suites'),
    ('/api/executions/',           '测试执行',  'Executions'),
    ('/api/reports/',              '测试报告',  'Reports'),
    ('/api/reviews/',              '评审管理',  'Reviews'),
    ('/api/versions/',             '版本管理',  'Versions'),
    ('/api/assistant/',            'AI助手',    'AI Assistant'),
    ('/api/requirement-analysis/', '需求分析',  'Requirement Analysis'),
    ('/api/ui-automation/',        'UI自动化',  'UI Automation'),
    ('/api/data-factory/',         '数据工厂',  'Data Factory'),
    ('/api/core/',                 '核心功能',  'Core'),
    ('/api/',                      '接口测试',  'API Testing'),
]

_SUPPORTED_LANGS = {'zh-cn', 'en'}


def _get_lang(request):
    """从 request.GET 读取 lang 参数，不支持的值回落到 zh-cn。"""
    if request is None:
        return 'zh-cn'
    lang = request.GET.get('lang', 'zh-cn')
    return lang if lang in _SUPPORTED_LANGS else 'zh-cn'


def _resolve_tag(path, lang):
    """按最具体前缀匹配，返回对应语言的标签名。"""
    for prefix, zh_tag, en_tag in _TAG_MAP:
        if path.startswith(prefix):
            return zh_tag if lang == 'zh-cn' else en_tag
    return '其他' if lang == 'zh-cn' else 'Other'


def auto_tag_hook(result, generator, request, public):
    """
    drf-spectacular postprocessing hook。
    为没有 tags 的 operation 自动分配模块标签，语言由 ?lang= 参数决定。
    """
    lang = _get_lang(request)
    for path, methods in result.get('paths', {}).items():
        tag = _resolve_tag(path, lang)
        for method, operation in methods.items():
            if isinstance(operation, dict) and 'tags' not in operation:
                operation['tags'] = [tag]
    return result
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd D:/python/testhub_platform-main
venv/Scripts/python.exe -m pytest tests/test_schema_hooks.py -v
```

期望输出：所有 7 个测试 `PASSED`

- [ ] **Step 5: 提交**

```bash
cd D:/python/testhub_platform-main
git add backend/schema_hooks.py tests/test_schema_hooks.py
git commit -m "feat: add bilingual auto-tag postprocessing hook for swagger docs"
```

---

## Task 2: 更新 settings.py

**Files:**
- Modify: `backend/settings.py`（`SPECTACULAR_SETTINGS` + `TEMPLATES[0]['DIRS']`）

- [ ] **Step 1: 修改 `SPECTACULAR_SETTINGS`**

找到 `backend/settings.py` 中的 `SPECTACULAR_SETTINGS`（约第 281 行），替换为：

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

- [ ] **Step 2: 在 TEMPLATES[0]['DIRS'] 中添加 templates 目录**

找到 `TEMPLATES` 配置（约第 73 行），将 `'DIRS': []` 改为：

```python
'DIRS': [BASE_DIR / 'templates'],
```

- [ ] **Step 3: 验证 Django 能正常启动**

```bash
cd D:/python/testhub_platform-main
venv/Scripts/python.exe manage.py check --deploy 2>&1 | grep -E "Error|Warning|System check"
```

期望输出：无 `Error`（`Warning` 关于 SECRET_KEY/DEBUG 是正常的，可忽略）

- [ ] **Step 4: 提交**

```bash
cd D:/python/testhub_platform-main
git add backend/settings.py
git commit -m "feat: register auto_tag_hook and configure swagger ui settings"
```

---

## Task 3: 创建自定义 Swagger UI JS 模板

**Files:**
- Create: `templates/drf_spectacular/swagger_ui_lang.js`

- [ ] **Step 1: 在项目根目录创建模板目录**

```bash
mkdir -p D:/python/testhub_platform-main/templates/drf_spectacular
```

- [ ] **Step 2: 创建 `templates/drf_spectacular/swagger_ui_lang.js`**

这是 drf-spectacular 默认 `swagger_ui.js` 的修改版本，唯一改动是将 `url` 替换为从 `localStorage` 读取语言的动态值：

```javascript
"use strict";

const swaggerSettings = {{ settings|safe }};
const schemaAuthNames = {{ schema_auth_names|safe }};
let schemaAuthFailed = false;
const plugins = [];

const reloadSchemaOnAuthChange = () => {
  return {
    statePlugins: {
      auth: {
        wrapActions: {
          authorize: (ori) => (...args) => {
            schemaAuthFailed = false;
            setTimeout(() => ui.specActions.download());
            return ori(...args);
          },
          logout: (ori) => (...args) => {
            schemaAuthFailed = false;
            setTimeout(() => ui.specActions.download());
            return ori(...args);
          },
        },
      },
    },
  };
};

if (schemaAuthNames.length > 0) {
  plugins.push(reloadSchemaOnAuthChange);
}

const uiInitialized = () => {
  try {
    ui;
    return true;
  } catch {
    return false;
  }
};

const isSchemaUrl = (url) => {
  if (!uiInitialized()) {
    return false;
  }
  return url === new URL(ui.getConfigs().url, document.baseURI).href;
};

const responseInterceptor = (response, ...args) => {
  if (!response.ok && isSchemaUrl(response.url)) {
    console.warn("schema request received '" + response.status + "'. disabling credentials for schema till logout.");
    if (!schemaAuthFailed) {
      schemaAuthFailed = true;
      setTimeout(() => ui.specActions.download());
    }
  }
  return response;
};

const injectAuthCredentials = (request) => {
  let authorized;
  if (uiInitialized()) {
    const state = ui.getState().get("auth").get("authorized");
    if (state !== undefined && Object.keys(state.toJS()).length !== 0) {
      authorized = state.toJS();
    }
  } else if (![undefined, "{}"].includes(localStorage.authorized)) {
    authorized = JSON.parse(localStorage.authorized);
  }
  if (authorized === undefined) {
    return;
  }
  for (const authName of schemaAuthNames) {
    const authDef = authorized[authName];
    if (authDef === undefined || authDef.schema === undefined) {
      continue;
    }
    if (authDef.schema.type === "http" && authDef.schema.scheme === "bearer") {
      request.headers["Authorization"] = "Bearer " + authDef.value;
      return;
    } else if (authDef.schema.type === "http" && authDef.schema.scheme === "basic") {
      request.headers["Authorization"] = "Basic " + btoa(authDef.value.username + ":" + authDef.value.password);
      return;
    } else if (authDef.schema.type === "apiKey" && authDef.schema.in === "header") {
      request.headers[authDef.schema.name] = authDef.value;
      return;
    } else if (authDef.schema.type === "oauth2" && authDef.token.token_type === "Bearer") {
      request.headers["Authorization"] = `Bearer ${authDef.token.access_token}`;
      return;
    }
  }
};

const requestInterceptor = (request, ...args) => {
  if (request.loadSpec && schemaAuthNames.length > 0 && !schemaAuthFailed) {
    try {
      injectAuthCredentials(request);
    } catch (e) {
      console.error("schema auth injection failed with error: ", e);
    }
  }
  if (!["GET", undefined].includes(request.method) && request.credentials === "same-origin") {
    request.headers["{{ csrf_header_name }}"] = "{{ csrf_token }}";
  }
  return request;
};

// ── 语言感知：从 localStorage 读取前端选择的语言 ──
const _appLang = localStorage.getItem('app-lang') || 'zh-cn';
const _schemaUrl = '/api/schema/?lang=' + _appLang;

const ui = SwaggerUIBundle({
  url: _schemaUrl,
  dom_id: "#swagger-ui",
  presets: [SwaggerUIBundle.presets.apis],
  plugins,
  layout: "BaseLayout",
  requestInterceptor,
  responseInterceptor,
  ...swaggerSettings,
});

{% if oauth2_config %}ui.initOAuth({{ oauth2_config|safe }});{% endif %}
```

- [ ] **Step 3: 提交**

```bash
cd D:/python/testhub_platform-main
git add templates/drf_spectacular/swagger_ui_lang.js
git commit -m "feat: add language-aware swagger ui js template"
```

---

## Task 4: 创建 LangAwareSwaggerView

**Files:**
- Create: `backend/schema_views.py`

- [ ] **Step 1: 创建 `backend/schema_views.py`**

```python
# backend/schema_views.py
from drf_spectacular.views import SpectacularSwaggerView


class LangAwareSwaggerView(SpectacularSwaggerView):
    """
    Swagger UI View，使用自定义 JS 模板。
    JS 模板从 localStorage['app-lang'] 读取语言，
    动态请求 /api/schema/?lang=<zh-cn|en>，
    由 auto_tag_hook 返回对应语言的接口标签。
    """
    template_name_js = 'drf_spectacular/swagger_ui_lang.js'
```

- [ ] **Step 2: 验证导入正常**

```bash
cd D:/python/testhub_platform-main
venv/Scripts/python.exe -c "from backend.schema_views import LangAwareSwaggerView; print('OK')"
```

期望输出：`OK`

- [ ] **Step 3: 提交**

```bash
cd D:/python/testhub_platform-main
git add backend/schema_views.py
git commit -m "feat: add LangAwareSwaggerView with custom js template"
```

---

## Task 5: 更新路由 urls.py

**Files:**
- Modify: `backend/urls.py`

- [ ] **Step 1: 修改 `backend/urls.py`**

在文件顶部的 import 区域，将原来的：

```python
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
```

替换为：

```python
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
)
from backend.schema_views import LangAwareSwaggerView
```

然后将 urlpatterns 中的：

```python
path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
```

替换为：

```python
path('api/docs/', LangAwareSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
```

- [ ] **Step 2: 验证 Django URL 配置无误**

```bash
cd D:/python/testhub_platform-main
venv/Scripts/python.exe manage.py show_urls 2>/dev/null | grep "api/docs\|api/schema\|api/redoc" || venv/Scripts/python.exe manage.py check
```

期望输出：包含 `api/docs/`、`api/schema/`、`api/redoc/` 三条路由

- [ ] **Step 3: 提交**

```bash
cd D:/python/testhub_platform-main
git add backend/urls.py
git commit -m "feat: wire LangAwareSwaggerView to /api/docs/ route"
```

---

## Task 6: 端到端验证

**Files:** 无新增，手动测试

- [ ] **Step 1: 启动 Django 开发服务器**

```bash
cd D:/python/testhub_platform-main
venv/Scripts/python.exe manage.py runserver
```

- [ ] **Step 2: 验证中文模式**

浏览器开发者控制台执行：

```javascript
localStorage.setItem('app-lang', 'zh-cn')
```

然后访问 `http://127.0.0.1:8000/api/docs/`，确认：
- 侧边栏出现中文分组（用户认证、项目管理、测试用例、测试执行等）
- 各接口归属于对应模块组
- `persistAuthorization` 生效（刷新后不丢失 Token）

- [ ] **Step 3: 验证英文模式**

浏览器开发者控制台执行：

```javascript
localStorage.setItem('app-lang', 'en')
location.reload()
```

确认：
- 侧边栏切换为英文分组（Authentication、Projects、Test Cases、Executions 等）

- [ ] **Step 4: 验证 schema 端点**

直接访问以下两个 URL，确认返回 JSON/YAML 且 tags 字段正确：
- `http://127.0.0.1:8000/api/schema/?lang=zh-cn` → tags 为中文
- `http://127.0.0.1:8000/api/schema/?lang=en` → tags 为英文

- [ ] **Step 5: 验证 ReDoc 不受影响**

访问 `http://127.0.0.1:8000/api/redoc/`，确认 ReDoc 页面仍正常显示（默认中文 tags）

---
