# UI 自动化脚本录制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a browser-based script recording feature that captures user actions via Playwright CDP screencast, converts them to TestCaseSteps referencing the Element library (match existing / update changed / create new).

**Architecture:** Backend launches Playwright browser, streams frames via WebSocket to a Vue Canvas. User interactions on Canvas are forwarded back to Playwright. Each action is recorded with CDP-extracted element info. On stop, ElementMatcher runs three-layer matching against the project's Element library. User confirms, then steps are saved as TestCase + TestCaseSteps.

**Tech Stack:** Django Channels (WebSocket), Playwright async API + CDP, Vue 3 + Canvas API, Element Plus UI

## Global Constraints

- Python 3.11+, Django 4.2, DRF
- Vue 3 Composition API (`<script setup>`), Vite 5, Element Plus
- All new Python code must have **Chinese comments** (module docstring, class/method docstrings, key inline comments)
- Follow existing import patterns: models from `apps.ui_automation.models`, API from `@/utils/api`
- No new model files — add to existing `models.py`
- Playwright already installed (`playwright==1.52.0` in requirements.txt)
- pytest for backend tests

## File Structure

### Backend — New Files

| File | Responsibility |
|------|----------------|
| `apps/ui_automation/recording/__init__.py` | Package init |
| `apps/ui_automation/recording/action_recorder.py` | CDP-based element extraction + locator generation |
| `apps/ui_automation/recording/element_matcher.py` | Three-layer element matching logic |
| `apps/ui_automation/recording/consumer.py` | WebSocket consumer: Playwright lifecycle, screencast, event forwarding |
| `apps/ui_automation/recording_views.py` | REST API views for recording sessions |
| `apps/ui_automation/recording_serializers.py` | DRF serializers for recording |
| `backend/routing.py` | Django Channels WebSocket URL routing |
| `apps/ui_automation/tests/__init__.py` | Test package init |
| `apps/ui_automation/tests/test_element_matcher.py` | ElementMatcher unit tests |
| `apps/ui_automation/tests/test_recording_api.py` | Recording REST API tests |

### Backend — Modified Files

| File | Change |
|------|--------|
| `apps/ui_automation/models.py` | Add `RecordingSession` model |
| `apps/ui_automation/urls.py` | Register recording API routes |
| `backend/settings.py` | Add `channels` to INSTALLED_APPS, configure CHANNEL_LAYERS, set ASGI_APPLICATION |
| `backend/asgi.py` | Rewrite with ProtocolTypeRouter for HTTP + WebSocket |
| `requirements.txt` | Add `channels>=4.0.0`, `channels-redis>=4.0.0` (optional, in-memory layer for dev) |

### Frontend — New Files

| File | Responsibility |
|------|----------------|
| `frontend/src/views/ui-automation/recorder/RecorderView.vue` | Main recording page layout |
| `frontend/src/views/ui-automation/recorder/RecorderCanvas.vue` | Canvas frame rendering + mouse/keyboard event capture |
| `frontend/src/views/ui-automation/recorder/RecorderToolbar.vue` | URL input, start/stop controls, viewport settings |
| `frontend/src/views/ui-automation/recorder/RecorderStepList.vue` | Real-time step list during recording |
| `frontend/src/views/ui-automation/recorder/RecorderConfirmDialog.vue` | Post-recording confirmation: match results + edit + save |
| `frontend/src/api/recording.js` | Recording REST API calls |

### Frontend — Modified Files

| File | Change |
|------|--------|
| `frontend/src/router/index.js` | Add `/ui-automation/recorder` route |
| `frontend/src/layout/index.vue` | Add sidebar menu item for recorder |
| `frontend/src/locales/lang/zh-cn/ui-automation.js` | Add `recorder` i18n section |
| `frontend/src/locales/lang/en/ui-automation.js` | Add `recorder` i18n section |

---

### Task 1: Django Channels Setup + RecordingSession Model

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/settings.py:30-38` (THIRD_PARTY_APPS) and end of file
- Modify: `backend/asgi.py` (full rewrite)
- Create: `backend/routing.py`
- Modify: `apps/ui_automation/models.py` (append RecordingSession)
- Create: `apps/ui_automation/recording/__init__.py`

**Interfaces:**
- Produces: `RecordingSession` model with fields `project`, `test_case`, `target_url`, `status`, `recorded_steps`, `match_results`, `viewport_width`, `viewport_height`, `created_by`, `created_at`, `finished_at`
- Produces: ASGI application with WebSocket routing at `ws/ui-automation/recording/<session_id>/`

- [ ] **Step 1: Install channels**

```bash
pip install "channels>=4.0.0"
```

Add to `requirements.txt`:
```
channels>=4.0.0
```

- [ ] **Step 2: Update settings.py**

In `backend/settings.py`, add `'daphne'` to the **beginning** of `THIRD_PARTY_APPS` and `'channels'` after it:

```python
THIRD_PARTY_APPS = [
    'daphne',
    'channels',
    'rest_framework',
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
]
```

At the end of `settings.py`, add:

```python
# ---------- Django Channels (WebSocket) ----------
ASGI_APPLICATION = 'backend.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}
```

- [ ] **Step 3: Rewrite asgi.py**

```python
"""
ASGI 配置 — 支持 HTTP 和 WebSocket 双协议。
HTTP 请求走 Django 默认处理，WebSocket 请求走 Channels routing。
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from backend.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        URLRouter(websocket_urlpatterns)
    ),
})
```

- [ ] **Step 4: Create routing.py skeleton**

```python
"""
WebSocket URL 路由配置。
所有 WebSocket 连接统一在此注册。
"""
from django.urls import re_path

# Consumer 将在 Task 5 中实现，此处先用占位导入
# from apps.ui_automation.recording.consumer import RecordingConsumer

websocket_urlpatterns = [
    # re_path(r'ws/ui-automation/recording/(?P<session_id>\d+)/$', RecordingConsumer.as_asgi()),
]
```

- [ ] **Step 5: Create recording package init**

Create `apps/ui_automation/recording/__init__.py` (empty file).

- [ ] **Step 6: Add RecordingSession model**

Append to `apps/ui_automation/models.py`:

```python
class RecordingSession(models.Model):
    """录制会话模型 — 管理一次脚本录制的完整生命周期"""
    STATUS_CHOICES = [
        ('recording', '录制中'),
        ('matching', '元素匹配中'),
        ('confirming', '待确认'),
        ('saved', '已保存'),
        ('cancelled', '已取消'),
    ]

    project = models.ForeignKey(UiProject, on_delete=models.CASCADE, related_name='recording_sessions', verbose_name='所属项目')
    test_case = models.ForeignKey(TestCase, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='关联测试用例')
    target_url = models.URLField(verbose_name='录制目标URL')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='recording', verbose_name='会话状态')
    recorded_steps = models.JSONField(default=list, blank=True, verbose_name='录制的原始步骤数据')
    match_results = models.JSONField(default=list, blank=True, verbose_name='元素匹配结果')
    viewport_width = models.IntegerField(default=1280, verbose_name='视口宽度')
    viewport_height = models.IntegerField(default=720, verbose_name='视口高度')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='创建人')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name='结束时间')

    class Meta:
        db_table = 'ui_recording_sessions'
        verbose_name = '录制会话'
        verbose_name_plural = '录制会话'
        ordering = ['-created_at']

    def __str__(self):
        return f'Recording #{self.id} - {self.target_url} ({self.get_status_display()})'
```

- [ ] **Step 7: Generate and run migration**

```bash
cd D:\python\testhub_platform-main
python manage.py makemigrations ui_automation --name recording_session
python manage.py migrate
```

- [ ] **Step 8: Verify Django starts with channels**

```bash
python manage.py check
```

- [ ] **Step 9: Commit**

```bash
git add requirements.txt backend/settings.py backend/asgi.py backend/routing.py apps/ui_automation/recording/__init__.py apps/ui_automation/models.py apps/ui_automation/migrations/
git commit -m "feat(recording): add Django Channels setup and RecordingSession model"
```

---

### Task 2: ActionRecorder — CDP Element Extraction + Locator Generation

**Files:**
- Create: `apps/ui_automation/recording/action_recorder.py`

**Interfaces:**
- Consumes: Playwright `Page` object (from consumer, Task 5)
- Produces: `ActionRecorder` class with methods:
  - `async record_click(page: Page, x: float, y: float) -> dict` — returns recorded step dict
  - `async record_fill(page: Page, x: float, y: float, text: str) -> dict`
  - `async record_hover(page: Page, x: float, y: float) -> dict`
  - `async record_scroll(page: Page, x: float, y: float, delta_x: float, delta_y: float) -> dict`
  - `get_steps() -> list[dict]` — returns all recorded steps
  - `clear()` — resets step list

- [ ] **Step 1: Write action_recorder.py**

```python
"""
ActionRecorder — 操作捕获与定位器提取模块。

在 Playwright 执行用户操作时，通过 CDP 协议获取目标坐标处的 DOM 元素信息，
生成多个候选定位器（按优先级排序），并记录完整的操作步骤。
"""
import json
import logging
import re
from dataclasses import dataclass, field
from playwright.async_api import Page

logger = logging.getLogger(__name__)

# HTML 标签 → Element.ELEMENT_TYPE_CHOICES 映射
TAG_TO_ELEMENT_TYPE = {
    'input': 'INPUT',
    'textarea': 'INPUT',
    'button': 'BUTTON',
    'a': 'LINK',
    'select': 'DROPDOWN',
    'img': 'IMAGE',
    'table': 'TABLE',
    'form': 'FORM',
    'dialog': 'MODAL',
    'th': 'TEXT',
    'td': 'TEXT',
    'label': 'TEXT',
    'span': 'TEXT',
    'p': 'TEXT',
    'h1': 'TEXT', 'h2': 'TEXT', 'h3': 'TEXT', 'h4': 'TEXT',
    'div': 'CONTAINER',
    'section': 'CONTAINER',
    'nav': 'CONTAINER',
}

# 常见的动态 ID 模式（这些 id 不适合作为稳定定位器）
DYNAMIC_ID_PATTERNS = [
    re.compile(r'[0-9a-f]{8,}'),        # 长十六进制串
    re.compile(r':\w+:'),                # Vue/React 生成的 :r1: 格式
    re.compile(r'__\w+_\d+'),            # 框架生成的 __el_123 格式
    re.compile(r'^ember\d+$'),           # Ember.js
    re.compile(r'^react-'),              # React 前缀
]


def _is_dynamic_id(id_value: str) -> bool:
    """判断 id 是否为框架动态生成的（不适合作为稳定定位器）"""
    if not id_value:
        return True
    return any(p.search(id_value) for p in DYNAMIC_ID_PATTERNS)


def _infer_element_type(tag_name: str, attrs: dict) -> str:
    """根据标签名和属性推断元素类型"""
    tag = tag_name.lower()
    input_type = attrs.get('type', '').lower()

    # input 子类型判断
    if tag == 'input':
        if input_type == 'checkbox':
            return 'CHECKBOX'
        if input_type == 'radio':
            return 'RADIO'
        if input_type in ('submit', 'button', 'reset'):
            return 'BUTTON'
        return 'INPUT'

    return TAG_TO_ELEMENT_TYPE.get(tag, 'BUTTON')


def _generate_locators(tag_name: str, attrs: dict, text_content: str) -> list[dict]:
    """
    为元素生成多个候选定位器，按优先级排序：
    1. data-testid → test-id
    2. id（非动态）→ id
    3. placeholder → placeholder
    4. aria-label → label
    5. 可见文本 → text
    6. CSS selector → css
    7. XPath → xpath（兜底）
    """
    locators = []
    tag = tag_name.lower()

    # 优先级1: data-testid / data-test
    test_id = attrs.get('data-testid') or attrs.get('data-test') or attrs.get('data-cy')
    if test_id:
        locators.append({'strategy': 'test-id', 'value': test_id})

    # 优先级2: id（过滤动态 id）
    elem_id = attrs.get('id', '')
    if elem_id and not _is_dynamic_id(elem_id):
        locators.append({'strategy': 'id', 'value': elem_id})

    # 优先级3: placeholder
    placeholder = attrs.get('placeholder', '')
    if placeholder:
        locators.append({'strategy': 'placeholder', 'value': placeholder})

    # 优先级4: aria-label
    aria_label = attrs.get('aria-label', '')
    if aria_label:
        locators.append({'strategy': 'label', 'value': aria_label})

    # 优先级5: 可见文本（短文本才适合做定位器）
    text = text_content.strip()
    if text and len(text) <= 50:
        locators.append({'strategy': 'text', 'value': text})

    # 优先级6: CSS selector（基于 tag + class 或 tag + 属性）
    css = _build_css_selector(tag, attrs)
    if css:
        locators.append({'strategy': 'css', 'value': css})

    # 优先级7: XPath 兜底
    xpath = _build_xpath(tag, attrs, text)
    if xpath:
        locators.append({'strategy': 'xpath', 'value': xpath})

    return locators


def _build_css_selector(tag: str, attrs: dict) -> str:
    """构建一个尽可能具体的 CSS selector"""
    parts = [tag]

    elem_id = attrs.get('id', '')
    if elem_id and not _is_dynamic_id(elem_id):
        return f'#{elem_id}'

    classes = attrs.get('class', '').split()
    # 过滤掉看起来像动态生成的 class（包含哈希后缀等）
    stable_classes = [c for c in classes if not re.search(r'[0-9a-f]{6,}|__', c)]
    if stable_classes:
        parts.append('.' + '.'.join(stable_classes[:3]))  # 最多取3个 class

    # 补充属性选择器
    for attr in ('name', 'type', 'role', 'data-testid'):
        if attr in attrs and attrs[attr]:
            parts.append(f'[{attr}="{attrs[attr]}"]')
            break

    selector = ''.join(parts)
    return selector if selector != tag else ''


def _build_xpath(tag: str, attrs: dict, text: str) -> str:
    """构建 XPath 定位器"""
    if text and len(text) <= 30:
        escaped = text.replace('"', '\\"')
        return f'//{tag}[contains(text(),"{escaped}")]'

    elem_id = attrs.get('id', '')
    if elem_id and not _is_dynamic_id(elem_id):
        return f'//{tag}[@id="{elem_id}"]'

    name = attrs.get('name', '')
    if name:
        return f'//{tag}[@name="{name}"]'

    return ''


def _generate_element_name(tag_name: str, attrs: dict, text_content: str) -> str:
    """为元素自动生成一个可读的名称"""
    text = text_content.strip()
    if text and len(text) <= 30:
        return text

    placeholder = attrs.get('placeholder', '')
    if placeholder:
        return placeholder

    aria_label = attrs.get('aria-label', '')
    if aria_label:
        return aria_label

    name = attrs.get('name', '')
    if name:
        return name

    elem_id = attrs.get('id', '')
    if elem_id and not _is_dynamic_id(elem_id):
        return elem_id

    return f'{tag_name.lower()}_element'


class ActionRecorder:
    """
    操作录制器 — 在 Playwright 执行操作时，同步通过 CDP 提取元素信息。

    用法:
        recorder = ActionRecorder()
        step = await recorder.record_click(page, 200, 300)
        # step 是一个完整的录制步骤 dict
    """

    def __init__(self):
        self._steps: list[dict] = []
        self._step_counter = 0

    async def _extract_element_at(self, page: Page, x: float, y: float) -> dict | None:
        """
        通过 CDP 获取指定坐标处的 DOM 元素信息。
        返回包含 tag_name, text_content, element_type, locators, attrs 的 dict。
        """
        try:
            cdp = await page.context.new_cdp_session(page)
            try:
                # 通过坐标获取 DOM 节点
                doc = await cdp.send('DOM.getDocument')
                node_resp = await cdp.send('DOM.getNodeForLocation', {
                    'x': int(x), 'y': int(y),
                    'includeUserAgentShadowDOM': False,
                })
                node_id = node_resp.get('nodeId') or node_resp.get('backendNodeId')
                if not node_id:
                    return None

                # 如果返回的是 backendNodeId，需要 resolve 成 nodeId
                if 'backendNodeId' in node_resp and 'nodeId' not in node_resp:
                    resolve_resp = await cdp.send('DOM.resolveNode', {
                        'backendNodeId': node_resp['backendNodeId'],
                    })
                    desc_resp = await cdp.send('DOM.describeNode', {
                        'backendNodeId': node_resp['backendNodeId'],
                    })
                else:
                    desc_resp = await cdp.send('DOM.describeNode', {'nodeId': node_id})

                node = desc_resp.get('node', {})
                tag_name = node.get('nodeName', 'unknown')

                # 获取属性（CDP 返回 [key, value, key, value, ...] 扁平数组）
                raw_attrs = node.get('attributes', [])
                attrs = {}
                for i in range(0, len(raw_attrs) - 1, 2):
                    attrs[raw_attrs[i]] = raw_attrs[i + 1]

                # 获取文本内容 — 通过 JS 执行取 innerText
                text_content = ''
                try:
                    remote_obj = await cdp.send('DOM.resolveNode', {
                        'nodeId': node_id if 'nodeId' in node_resp else 0,
                        'backendNodeId': node_resp.get('backendNodeId', 0),
                    })
                    object_id = remote_obj.get('object', {}).get('objectId')
                    if object_id:
                        result = await cdp.send('Runtime.callFunctionOn', {
                            'objectId': object_id,
                            'functionDeclaration': 'function() { return this.innerText || this.textContent || ""; }',
                            'returnByValue': True,
                        })
                        text_content = result.get('result', {}).get('value', '')
                except Exception:
                    pass

                element_type = _infer_element_type(tag_name, attrs)
                locators = _generate_locators(tag_name, attrs, text_content)
                name = _generate_element_name(tag_name, attrs, text_content)

                return {
                    'tag_name': tag_name,
                    'text_content': text_content[:100],  # 截断过长文本
                    'element_type': element_type,
                    'element_name': name,
                    'locators': locators,
                    'attrs': attrs,
                }
            finally:
                await cdp.detach()
        except Exception as e:
            logger.warning('CDP 元素提取失败 (x=%s, y=%s): %s', x, y, e)
            return None

    def _make_step(self, action_type: str, page_url: str,
                   element_info: dict | None, input_value: str = '') -> dict:
        """构建一条录制步骤记录"""
        self._step_counter += 1
        step = {
            'step_number': self._step_counter,
            'action_type': action_type,
            'input_value': input_value,
            'page_url': page_url,
            'element_info': element_info,
        }
        self._steps.append(step)
        return step

    async def record_click(self, page: Page, x: float, y: float) -> dict:
        """录制点击操作"""
        element_info = await self._extract_element_at(page, x, y)
        return self._make_step('click', page.url, element_info)

    async def record_fill(self, page: Page, x: float, y: float, text: str) -> dict:
        """录制文本输入操作"""
        element_info = await self._extract_element_at(page, x, y)
        return self._make_step('fill', page.url, element_info, input_value=text)

    async def record_hover(self, page: Page, x: float, y: float) -> dict:
        """录制悬停操作"""
        element_info = await self._extract_element_at(page, x, y)
        return self._make_step('hover', page.url, element_info)

    async def record_scroll(self, page: Page, x: float, y: float,
                            delta_x: float, delta_y: float) -> dict:
        """录制滚动操作"""
        element_info = await self._extract_element_at(page, x, y)
        step = self._make_step('scroll', page.url, element_info)
        step['scroll_delta'] = {'x': delta_x, 'y': delta_y}
        return step

    def get_steps(self) -> list[dict]:
        """获取所有已录制的步骤"""
        return list(self._steps)

    def clear(self):
        """清空录制数据"""
        self._steps.clear()
        self._step_counter = 0
```

- [ ] **Step 2: Commit**

```bash
git add apps/ui_automation/recording/
git commit -m "feat(recording): add ActionRecorder with CDP element extraction and locator generation"
```

---

### Task 3: ElementMatcher — Three-Layer Element Matching

**Files:**
- Create: `apps/ui_automation/recording/element_matcher.py`
- Create: `apps/ui_automation/tests/__init__.py`
- Create: `apps/ui_automation/tests/test_element_matcher.py`

**Interfaces:**
- Consumes: `Element` model, `LocatorStrategy` model, `ElementGroup` model from `apps.ui_automation.models`
- Consumes: recorded step dicts from `ActionRecorder` (Task 2)
- Produces: `ElementMatcher` class with method:
  - `match_all(project_id: int, steps: list[dict], user) -> list[dict]` — returns match results list, each item has `status` ('reused'|'updated'|'created'), `element_id`, `element_name`, `step_number`, `changes` (for updates)

- [ ] **Step 1: Write the failing test**

Create `apps/ui_automation/tests/__init__.py` (empty).

Create `apps/ui_automation/tests/test_element_matcher.py`:

```python
"""ElementMatcher 三层匹配逻辑单元测试"""
import pytest
from django.contrib.auth import get_user_model
from apps.ui_automation.models import (
    UiProject, Element, LocatorStrategy, ElementGroup,
)
from apps.ui_automation.recording.element_matcher import ElementMatcher

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='tester', password='test1234')


@pytest.fixture
def project(db, user):
    return UiProject.objects.create(name='TestProject', created_by=user)


@pytest.fixture
def css_strategy(db):
    return LocatorStrategy.objects.create(
        name='css', strategy_type='css', description='CSS Selector', priority=5
    )


@pytest.fixture
def text_strategy(db):
    return LocatorStrategy.objects.create(
        name='text', strategy_type='text', description='Text', priority=4
    )


@pytest.fixture
def existing_element(db, project, css_strategy, user):
    """元素库中已有的元素：登录按钮，css定位"""
    return Element.objects.create(
        project=project,
        name='登录按钮',
        element_type='BUTTON',
        locator_strategy=css_strategy,
        locator_value='#login-btn',
        page='/login',
        created_by=user,
    )


class TestElementMatcherExact:
    """第1层：精确匹配 — 定位器完全一致时直接复用"""

    def test_exact_match_reuses_element(self, project, existing_element, user):
        steps = [{
            'step_number': 1,
            'action_type': 'click',
            'page_url': 'https://example.com/login',
            'element_info': {
                'element_type': 'BUTTON',
                'element_name': '登录按钮',
                'locators': [
                    {'strategy': 'css', 'value': '#login-btn'},
                    {'strategy': 'text', 'value': '登录'},
                ],
            },
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert len(results) == 1
        assert results[0]['status'] == 'reused'
        assert results[0]['element_id'] == existing_element.id

    def test_exact_match_via_backup_locator(self, project, existing_element, css_strategy, user):
        """备用定位器也能命中精确匹配"""
        existing_element.backup_locators = [{'strategy': 'text', 'value': '登录'}]
        existing_element.save()

        steps = [{
            'step_number': 1,
            'action_type': 'click',
            'page_url': 'https://example.com/login',
            'element_info': {
                'element_type': 'BUTTON',
                'element_name': '登录按钮',
                'locators': [{'strategy': 'text', 'value': '登录'}],
            },
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert results[0]['status'] == 'reused'


class TestElementMatcherFuzzy:
    """第2层：模糊匹配 — 元素变更但可识别，更新定位器"""

    def test_fuzzy_match_updates_locator(self, project, existing_element, css_strategy, user):
        """同页面、同 test-id → 定位器变了 → 更新"""
        existing_element.backup_locators = [{'strategy': 'test-id', 'value': 'login-btn'}]
        existing_element.save()

        steps = [{
            'step_number': 1,
            'action_type': 'click',
            'page_url': 'https://example.com/login',
            'element_info': {
                'element_type': 'BUTTON',
                'element_name': '登录按钮',
                'locators': [
                    {'strategy': 'test-id', 'value': 'login-btn'},
                    {'strategy': 'css', 'value': '#new-login-btn'},
                ],
            },
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert results[0]['status'] == 'updated'
        assert results[0]['element_id'] == existing_element.id


class TestElementMatcherNew:
    """第3层：无匹配 — 创建新元素"""

    def test_no_match_creates_new(self, project, css_strategy, user):
        steps = [{
            'step_number': 1,
            'action_type': 'click',
            'page_url': 'https://example.com/register',
            'element_info': {
                'element_type': 'BUTTON',
                'element_name': '注册按钮',
                'locators': [{'strategy': 'css', 'value': '#register-btn'}],
            },
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert results[0]['status'] == 'created'
        assert results[0]['element_name'] == '注册按钮'


class TestElementMatcherNoElement:
    """操作没有关联元素（如 wait、screenshot）"""

    def test_step_without_element(self, project, user):
        steps = [{
            'step_number': 1,
            'action_type': 'wait',
            'page_url': 'https://example.com/',
            'element_info': None,
        }]
        matcher = ElementMatcher(project.id, user)
        results = matcher.match_all(steps)
        assert results[0]['status'] == 'no_element'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd D:\python\testhub_platform-main
python -m pytest apps/ui_automation/tests/test_element_matcher.py -v
```

Expected: ImportError or ModuleNotFoundError (element_matcher doesn't exist yet).

- [ ] **Step 3: Implement ElementMatcher**

```python
"""
ElementMatcher — 三层元素匹配引擎。

将录制到的元素与项目元素库进行匹配：
  第1层：精确匹配 — 任一定位器完全一致 → 直接复用
  第2层：模糊匹配 — 页面+标识性属性相同但定位器变了 → 更新定位器
  第3层：无匹配 — 自动创建新元素

核心原则：匹配优先、变更更新、仅缺失才新增。
"""
import logging
from datetime import datetime
from urllib.parse import urlparse

from django.utils import timezone

from apps.ui_automation.models import (
    Element, LocatorStrategy, ElementGroup, UiProject,
)

logger = logging.getLogger(__name__)

# 模糊匹配时，这些策略具有"身份标识"作用——如果它们一致，认为是同一个元素
IDENTITY_STRATEGIES = {'test-id', 'id', 'placeholder', 'label'}


def _extract_page_path(url: str) -> str:
    """从完整 URL 提取路径部分，用于与 Element.page 字段比较"""
    parsed = urlparse(url)
    return parsed.path or '/'


def _get_all_locators(element: Element) -> list[dict]:
    """获取元素的所有定位器（主 + 备用），统一为 {strategy, value} 格式"""
    locators = [{'strategy': element.locator_strategy.name, 'value': element.locator_value}]
    if element.backup_locators:
        for backup in element.backup_locators:
            locators.append({
                'strategy': backup.get('strategy', ''),
                'value': backup.get('value', ''),
            })
    return locators


class ElementMatcher:
    """
    元素匹配器。

    用法:
        matcher = ElementMatcher(project_id=1, user=request.user)
        results = matcher.match_all(recorded_steps)
    """

    def __init__(self, project_id: int, user):
        self.project_id = project_id
        self.user = user
        # 预加载该项目的所有元素，避免逐步骤查询
        self._elements = list(
            Element.objects.filter(project_id=project_id)
            .select_related('locator_strategy')
        )
        # 按 (page, strategy, value) 构建索引，加速精确匹配
        self._locator_index: dict[tuple[str, str, str], Element] = {}
        for elem in self._elements:
            page = elem.page or ''
            for loc in _get_all_locators(elem):
                key = (page, loc['strategy'], loc['value'])
                self._locator_index[key] = elem

    def match_all(self, steps: list[dict]) -> list[dict]:
        """
        对所有录制步骤执行元素匹配，返回匹配结果列表。
        每个结果包含: step_number, status, element_id, element_name, changes
        """
        results = []
        for step in steps:
            result = self._match_step(step)
            results.append(result)
        return results

    def _match_step(self, step: dict) -> dict:
        """匹配单个步骤"""
        element_info = step.get('element_info')
        base = {
            'step_number': step['step_number'],
            'action_type': step['action_type'],
            'input_value': step.get('input_value', ''),
            'page_url': step.get('page_url', ''),
        }

        # 没有元素信息的操作（wait、screenshot 等）
        if not element_info:
            return {**base, 'status': 'no_element', 'element_id': None, 'element_name': '', 'changes': None}

        page_path = _extract_page_path(step.get('page_url', ''))
        locators = element_info.get('locators', [])

        # 第1层：精确匹配
        matched = self._exact_match(page_path, locators)
        if matched:
            return {**base, 'status': 'reused', 'element_id': matched.id,
                    'element_name': matched.name, 'changes': None}

        # 第2层：模糊匹配（标识性属性一致但定位器变了）
        matched = self._fuzzy_match(page_path, element_info, locators)
        if matched:
            changes = self._apply_update(matched, locators)
            return {**base, 'status': 'updated', 'element_id': matched.id,
                    'element_name': matched.name, 'changes': changes}

        # 第3层：无匹配 — 新增
        return {**base, 'status': 'created', 'element_id': None,
                'element_name': element_info.get('element_name', ''),
                'element_info': element_info, 'changes': None}

    def _exact_match(self, page_path: str, locators: list[dict]) -> Element | None:
        """第1层：在索引中查找任一定位器精确匹配"""
        for loc in locators:
            key = (page_path, loc['strategy'], loc['value'])
            elem = self._locator_index.get(key)
            if elem:
                return elem
        # 也尝试空页面路径（有些元素的 page 字段为空）
        for loc in locators:
            key = ('', loc['strategy'], loc['value'])
            elem = self._locator_index.get(key)
            if elem:
                return elem
        return None

    def _fuzzy_match(self, page_path: str, element_info: dict,
                     locators: list[dict]) -> Element | None:
        """
        第2层：模糊匹配 — 通过身份标识策略（test-id, id, placeholder, label）
        或元素类型+文本相似性判断是否为同一个元素。
        """
        incoming_identity = {}
        for loc in locators:
            if loc['strategy'] in IDENTITY_STRATEGIES:
                incoming_identity[loc['strategy']] = loc['value']

        incoming_type = element_info.get('element_type', '')
        incoming_text = element_info.get('text_content', '').strip()

        for elem in self._elements:
            # 页面必须匹配（或元素页面为空）
            if elem.page and elem.page != page_path:
                continue

            elem_locators = _get_all_locators(elem)

            # 条件a/b: 任一身份标识策略的值相同
            for eloc in elem_locators:
                if eloc['strategy'] in IDENTITY_STRATEGIES:
                    if eloc['strategy'] in incoming_identity:
                        if eloc['value'] == incoming_identity[eloc['strategy']]:
                            return elem

            # 条件c: 同类型 + 文本内容一致（用于没有 test-id 的场景）
            if incoming_type and incoming_type == elem.element_type:
                if incoming_text and incoming_text == (elem.name or ''):
                    return elem

        return None

    def _apply_update(self, element: Element, new_locators: list[dict]) -> dict:
        """
        更新元素的定位器。
        新的最高优先级定位器成为主定位器，其余存入 backup_locators。
        保留 name、description、group 等人工维护字段不变。
        """
        if not new_locators:
            return {}

        old_primary = {
            'strategy': element.locator_strategy.name,
            'value': element.locator_value,
        }

        # 新的主定位器 = 列表中第一个（优先级最高）
        new_primary = new_locators[0]
        new_backups = new_locators[1:]

        # 查找对应的 LocatorStrategy 记录
        strategy_obj = LocatorStrategy.objects.filter(name=new_primary['strategy']).first()
        if not strategy_obj:
            # 策略不存在时不更新主定位器，只更新备用
            changes = {'backup_locators': new_locators}
            element.backup_locators = new_locators
        else:
            changes = {
                'old_primary': old_primary,
                'new_primary': new_primary,
                'new_backups': new_backups,
            }
            element.locator_strategy = strategy_obj
            element.locator_value = new_primary['value']
            element.backup_locators = new_backups if new_backups else None

        element.validation_status = 'VALID'
        element.last_validated = timezone.now()
        element.save()

        # 刷新索引
        self._rebuild_index_for(element)
        return changes

    def _rebuild_index_for(self, element: Element):
        """更新单个元素在索引中的条目"""
        # 先删除该元素的旧索引
        keys_to_remove = [k for k, v in self._locator_index.items() if v.id == element.id]
        for k in keys_to_remove:
            del self._locator_index[k]
        # 重建
        element.refresh_from_db()
        page = element.page or ''
        for loc in _get_all_locators(element):
            self._locator_index[(page, loc['strategy'], loc['value'])] = element
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest apps/ui_automation/tests/test_element_matcher.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/ui_automation/recording/element_matcher.py apps/ui_automation/tests/
git commit -m "feat(recording): add ElementMatcher with three-layer matching logic and tests"
```

---

### Task 4: WebSocket Consumer — Playwright Screencast + Event Forwarding

**Files:**
- Create: `apps/ui_automation/recording/consumer.py`
- Modify: `backend/routing.py` (uncomment route)

**Interfaces:**
- Consumes: `ActionRecorder` from Task 2
- Consumes: `RecordingSession` model from Task 1
- Produces: `RecordingConsumer(AsyncWebsocketConsumer)` handling:
  - `connect()` — validate session, launch Playwright, start screencast
  - `receive()` — parse JSON messages, dispatch to handler
  - `disconnect()` — cleanup browser
  - Frame streaming loop pushes `{type: "frame", data: base64}` at ~10 fps

- [ ] **Step 1: Write consumer.py**

```python
"""
RecordingConsumer — WebSocket 消费者，管理录制会话的完整生命周期。

职责:
  1. 启动 Playwright 浏览器并打开目标 URL
  2. 通过 CDP Page.startScreencast 获取截图帧，推送到前端 Canvas
  3. 接收前端转发的鼠标/键盘事件，在 Playwright 中执行
  4. 每次操作同步调用 ActionRecorder 记录步骤
  5. 录制结束时保存步骤到 RecordingSession
"""
import asyncio
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from playwright.async_api import async_playwright

from apps.ui_automation.models import RecordingSession
from .action_recorder import ActionRecorder

logger = logging.getLogger(__name__)

# 截图帧质量（JPEG 0-100），越低越快
FRAME_QUALITY = 65
# 最大帧率（CDP screencast 的 maxWidth/maxHeight 用于控制分辨率）
MAX_FPS = 12


class RecordingConsumer(AsyncWebsocketConsumer):
    """录制会话 WebSocket 消费者"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_id: int = 0
        self.session: RecordingSession | None = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.cdp_session = None
        self.recorder = ActionRecorder()
        self._screencast_running = False
        # 记录最后一次点击坐标，用于 fill 操作关联元素
        self._last_click_x = 0
        self._last_click_y = 0

    async def connect(self):
        """WebSocket 连接建立 — 验证会话并启动浏览器"""
        self.session_id = int(self.scope['url_route']['kwargs']['session_id'])

        # 验证录制会话存在且状态正确
        self.session = await self._get_session()
        if not self.session:
            await self.close(code=4004)
            return

        await self.accept()
        await self._send_status('launching')

        try:
            await self._launch_browser()
            await self._start_screencast()
            await self._send_status('ready')
        except Exception as e:
            logger.exception('启动 Playwright 浏览器失败')
            await self._send_status('error')
            await self.send_json({'type': 'error', 'message': str(e)})
            await self.close()

    async def disconnect(self, close_code):
        """WebSocket 断开 — 清理浏览器资源"""
        await self._stop_screencast()
        await self._cleanup_browser()

    async def receive(self, text_data=None, bytes_data=None):
        """接收前端消息并分发到对应处理器"""
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        msg_type = data.get('type', '')
        handler = {
            'mousedown': self._handle_mouse_click,
            'mousemove': self._handle_mouse_move,
            'keydown': self._handle_key,
            'scroll': self._handle_scroll,
            'input': self._handle_input,
            'control': self._handle_control,
        }.get(msg_type)

        if handler:
            try:
                await handler(data)
            except Exception as e:
                logger.exception('处理 %s 事件失败', msg_type)

    # ---- 事件处理器 ----

    async def _handle_mouse_click(self, data):
        """处理鼠标点击：转发到 Playwright + 录制"""
        x, y = data.get('x', 0), data.get('y', 0)
        self._last_click_x, self._last_click_y = x, y
        button = data.get('button', 'left')

        # 先录制（提取元素信息），再执行点击
        step = await self.recorder.record_click(self.page, x, y)
        await self.page.mouse.click(x, y, button=button)

        await self._send_action(step)

    async def _handle_mouse_move(self, data):
        """处理鼠标移动（不录制，仅同步光标位置）"""
        x, y = data.get('x', 0), data.get('y', 0)
        await self.page.mouse.move(x, y)

    async def _handle_key(self, data):
        """处理键盘按键"""
        key = data.get('key', '')
        if key:
            await self.page.keyboard.press(key)

    async def _handle_scroll(self, data):
        """处理滚动"""
        x, y = data.get('x', 0), data.get('y', 0)
        delta_x = data.get('deltaX', 0)
        delta_y = data.get('deltaY', 0)

        step = await self.recorder.record_scroll(self.page, x, y, delta_x, delta_y)
        await self.page.mouse.wheel(delta_x, delta_y)

        await self._send_action(step)

    async def _handle_input(self, data):
        """处理文本输入（前端输入框确认后一次性发送）"""
        text = data.get('text', '')
        if not text:
            return

        # 用上次点击的坐标定位目标元素
        step = await self.recorder.record_fill(
            self.page, self._last_click_x, self._last_click_y, text
        )

        # 先清空现有内容再输入（triple-click 全选后输入）
        await self.page.mouse.click(self._last_click_x, self._last_click_y, click_count=3)
        await self.page.keyboard.type(text, delay=20)

        await self._send_action(step)

    async def _handle_control(self, data):
        """处理控制命令：导航、停止"""
        action = data.get('action', '')

        if action == 'navigate':
            url = data.get('url', '')
            if url:
                await self._send_status('navigating')
                await self.page.goto(url, wait_until='domcontentloaded')
                await self._send_status('ready')

        elif action == 'stop':
            # 停止录制，保存步骤到数据库
            await self._stop_screencast()
            steps = self.recorder.get_steps()
            await self._save_steps(steps)
            await self.send_json({'type': 'recording_stopped', 'step_count': len(steps)})

    # ---- Playwright 浏览器管理 ----

    async def _launch_browser(self):
        """启动 Playwright chromium 浏览器"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-gpu'],
        )
        self.context = await self.browser.new_context(
            viewport={
                'width': self.session.viewport_width,
                'height': self.session.viewport_height,
            },
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/125.0.0.0 Safari/537.36'
            ),
        )
        self.page = await self.context.new_page()
        await self.page.goto(self.session.target_url, wait_until='domcontentloaded')

    async def _cleanup_browser(self):
        """清理浏览器资源"""
        try:
            if self.cdp_session:
                await self.cdp_session.detach()
        except Exception:
            pass
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception:
            pass

    # ---- CDP Screencast ----

    async def _start_screencast(self):
        """启动 CDP 截图流，将帧推送到前端"""
        self.cdp_session = await self.page.context.new_cdp_session(self.page)
        self._screencast_running = True

        # 注册帧回调
        self.cdp_session.on('Page.screencastFrame', self._on_screencast_frame)

        await self.cdp_session.send('Page.startScreencast', {
            'format': 'jpeg',
            'quality': FRAME_QUALITY,
            'maxWidth': self.session.viewport_width,
            'maxHeight': self.session.viewport_height,
            'everyNthFrame': max(1, 60 // MAX_FPS),  # 每 N 帧取一帧
        })

    def _on_screencast_frame(self, params):
        """CDP screencast 帧回调 — 推送到 WebSocket"""
        session_id = params.get('sessionId', 0)
        data = params.get('data', '')

        # 确认帧已接收（CDP 要求 ack 才会发下一帧）
        asyncio.ensure_future(
            self.cdp_session.send('Page.screencastFrameAck', {'sessionId': session_id})
        )

        # 推送帧到前端
        if self._screencast_running and data:
            asyncio.ensure_future(
                self.send_json({'type': 'frame', 'data': data})
            )

    async def _stop_screencast(self):
        """停止 CDP 截图流"""
        self._screencast_running = False
        if self.cdp_session:
            try:
                await self.cdp_session.send('Page.stopScreencast')
            except Exception:
                pass

    # ---- 辅助方法 ----

    async def send_json(self, data: dict):
        """发送 JSON 消息到前端"""
        await self.send(text_data=json.dumps(data, ensure_ascii=False))

    async def _send_status(self, status: str):
        """发送状态变更通知"""
        await self.send_json({'type': 'status', 'data': status})

    async def _send_action(self, step: dict):
        """发送录制的操作步骤到前端（实时显示在步骤列表中）"""
        await self.send_json({'type': 'action', 'data': step})

    @database_sync_to_async
    def _get_session(self) -> RecordingSession | None:
        """从数据库获取录制会话"""
        try:
            return RecordingSession.objects.get(
                id=self.session_id, status='recording'
            )
        except RecordingSession.DoesNotExist:
            return None

    @database_sync_to_async
    def _save_steps(self, steps: list[dict]):
        """保存录制步骤到数据库"""
        RecordingSession.objects.filter(id=self.session_id).update(
            recorded_steps=steps,
            status='matching',
        )
```

- [ ] **Step 2: Update routing.py — uncomment the route**

Replace the placeholder in `backend/routing.py`:

```python
"""
WebSocket URL 路由配置。
所有 WebSocket 连接统一在此注册。
"""
from django.urls import re_path
from apps.ui_automation.recording.consumer import RecordingConsumer

websocket_urlpatterns = [
    re_path(r'ws/ui-automation/recording/(?P<session_id>\d+)/$', RecordingConsumer.as_asgi()),
]
```

- [ ] **Step 3: Commit**

```bash
git add apps/ui_automation/recording/consumer.py backend/routing.py
git commit -m "feat(recording): add WebSocket consumer with Playwright screencast and event forwarding"
```

---

### Task 5: Recording REST API — Views, Serializers, URLs

**Files:**
- Create: `apps/ui_automation/recording_serializers.py`
- Create: `apps/ui_automation/recording_views.py`
- Modify: `apps/ui_automation/urls.py`
- Create: `apps/ui_automation/tests/test_recording_api.py`

**Interfaces:**
- Consumes: `RecordingSession` model (Task 1), `ElementMatcher` (Task 3)
- Produces: REST endpoints: `POST recording/start/`, `POST recording/<id>/stop/`, `GET recording/<id>/match-results/`, `POST recording/<id>/confirm/`, `POST recording/<id>/cancel/`

- [ ] **Step 1: Write serializers**

```python
"""
录制功能序列化器。
"""
from rest_framework import serializers
from .models import RecordingSession, TestCase, TestCaseStep, Element


class StartRecordingSerializer(serializers.Serializer):
    """开始录制请求参数"""
    project_id = serializers.IntegerField(help_text='项目ID')
    target_url = serializers.URLField(help_text='录制目标URL')
    viewport_width = serializers.IntegerField(default=1280, required=False)
    viewport_height = serializers.IntegerField(default=720, required=False)


class RecordingSessionSerializer(serializers.ModelSerializer):
    """录制会话序列化"""
    class Meta:
        model = RecordingSession
        fields = [
            'id', 'project', 'test_case', 'target_url', 'status',
            'recorded_steps', 'match_results',
            'viewport_width', 'viewport_height',
            'created_by', 'created_at', 'finished_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


class ConfirmRecordingSerializer(serializers.Serializer):
    """确认录制请求参数"""
    test_case_name = serializers.CharField(max_length=200, help_text='测试用例名称')
    steps = serializers.ListField(
        child=serializers.DictField(),
        help_text='确认后的步骤列表（用户可能调整了顺序、删除了步骤、修改了元素关联）'
    )
```

- [ ] **Step 2: Write views**

```python
"""
录制功能 REST API 视图。

提供录制会话的创建、停止、匹配结果查看、确认保存和取消等操作。
"""
import logging
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import (
    RecordingSession, UiProject, TestCase, TestCaseStep,
    Element, LocatorStrategy, ElementGroup,
)
from .recording_serializers import (
    StartRecordingSerializer, RecordingSessionSerializer, ConfirmRecordingSerializer,
)
from .recording.element_matcher import ElementMatcher

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_recording(request):
    """创建录制会话，返回 session_id 和 WebSocket 地址"""
    ser = StartRecordingSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    data = ser.validated_data
    project = UiProject.objects.filter(id=data['project_id']).first()
    if not project:
        return Response({'error': '项目不存在'}, status=status.HTTP_404_NOT_FOUND)

    session = RecordingSession.objects.create(
        project=project,
        target_url=data['target_url'],
        viewport_width=data.get('viewport_width', 1280),
        viewport_height=data.get('viewport_height', 720),
        created_by=request.user,
    )

    # 构建 WebSocket 地址（前端根据当前 host 拼接）
    ws_path = f'/ws/ui-automation/recording/{session.id}/'

    return Response({
        'session_id': session.id,
        'ws_path': ws_path,
        'status': session.status,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def stop_recording(request, session_id):
    """停止录制，触发元素匹配"""
    session = RecordingSession.objects.filter(
        id=session_id, created_by=request.user
    ).first()
    if not session:
        return Response({'error': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)
    if session.status not in ('recording', 'matching'):
        return Response({'error': f'会话状态不允许此操作: {session.status}'}, status=status.HTTP_400_BAD_REQUEST)

    # 执行元素匹配
    matcher = ElementMatcher(session.project_id, request.user)
    match_results = matcher.match_all(session.recorded_steps)

    session.match_results = match_results
    session.status = 'confirming'
    session.finished_at = timezone.now()
    session.save()

    return Response({
        'session_id': session.id,
        'status': session.status,
        'match_results': match_results,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_match_results(request, session_id):
    """获取元素匹配结果供前端确认"""
    session = RecordingSession.objects.filter(
        id=session_id, created_by=request.user
    ).first()
    if not session:
        return Response({'error': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'session_id': session.id,
        'status': session.status,
        'recorded_steps': session.recorded_steps,
        'match_results': session.match_results,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_recording(request, session_id):
    """确认录制结果，保存为 TestCase + TestCaseSteps + 元素变更"""
    session = RecordingSession.objects.filter(
        id=session_id, created_by=request.user, status='confirming'
    ).first()
    if not session:
        return Response({'error': '会话不存在或状态不正确'}, status=status.HTTP_404_NOT_FOUND)

    ser = ConfirmRecordingSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    data = ser.validated_data
    confirmed_steps = data['steps']

    # 创建测试用例
    test_case = TestCase.objects.create(
        project=session.project,
        name=data['test_case_name'],
        description=f'由脚本录制自动生成，目标URL: {session.target_url}',
        status='active',
        created_by=request.user,
    )

    # 逐步骤创建 TestCaseStep 并处理元素
    for step_data in confirmed_steps:
        element = None
        match_status = step_data.get('status', '')

        if match_status == 'reused' or match_status == 'updated':
            # 复用或已更新的元素 — 直接关联
            element_id = step_data.get('element_id')
            if element_id:
                element = Element.objects.filter(id=element_id).first()

        elif match_status == 'created':
            # 新增元素 — 在此创建
            element_info = step_data.get('element_info', {})
            if element_info:
                element = _create_element(
                    session.project, element_info, step_data.get('page_url', ''), request.user
                )

        TestCaseStep.objects.create(
            test_case=test_case,
            step_number=step_data.get('step_number', 0),
            action_type=step_data.get('action_type', 'click'),
            element=element,
            input_value=step_data.get('input_value', ''),
            description=step_data.get('description', ''),
        )

    # 更新会话状态
    session.test_case = test_case
    session.status = 'saved'
    session.save()

    return Response({
        'session_id': session.id,
        'test_case_id': test_case.id,
        'test_case_name': test_case.name,
        'step_count': len(confirmed_steps),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_recording(request, session_id):
    """取消录制会话"""
    session = RecordingSession.objects.filter(
        id=session_id, created_by=request.user
    ).exclude(status__in=['saved', 'cancelled']).first()
    if not session:
        return Response({'error': '会话不存在'}, status=status.HTTP_404_NOT_FOUND)

    session.status = 'cancelled'
    session.finished_at = timezone.now()
    session.save()

    return Response({'session_id': session.id, 'status': 'cancelled'})


def _create_element(project, element_info: dict, page_url: str, user) -> Element:
    """根据录制到的元素信息创建新的 Element 记录"""
    from urllib.parse import urlparse
    page_path = urlparse(page_url).path or '/'

    locators = element_info.get('locators', [])
    if not locators:
        # 没有定位器时用 xpath 兜底
        locators = [{'strategy': 'xpath', 'value': '//body'}]

    # 主定位器 = 第一个
    primary = locators[0]
    strategy = LocatorStrategy.objects.filter(name=primary['strategy']).first()
    if not strategy:
        strategy = LocatorStrategy.objects.first()

    # 备用定位器 = 剩余
    backups = locators[1:] if len(locators) > 1 else None

    return Element.objects.create(
        project=project,
        name=element_info.get('element_name', 'unnamed_element'),
        element_type=element_info.get('element_type', 'BUTTON'),
        locator_strategy=strategy,
        locator_value=primary['value'],
        backup_locators=backups,
        page=page_path,
        created_by=user,
    )
```

- [ ] **Step 3: Register URL routes**

Add to `apps/ui_automation/urls.py`, before `urlpatterns = [...]`:

```python
from .recording_views import (
    start_recording, stop_recording, get_match_results,
    confirm_recording, cancel_recording,
)
```

Add these paths inside the `urlpatterns` list, before the `path('', include(router.urls))` line:

```python
    path('recording/start/', start_recording, name='recording-start'),
    path('recording/<int:session_id>/stop/', stop_recording, name='recording-stop'),
    path('recording/<int:session_id>/match-results/', get_match_results, name='recording-match-results'),
    path('recording/<int:session_id>/confirm/', confirm_recording, name='recording-confirm'),
    path('recording/<int:session_id>/cancel/', cancel_recording, name='recording-cancel'),
```

- [ ] **Step 4: Write API tests**

Create `apps/ui_automation/tests/test_recording_api.py`:

```python
"""录制 REST API 集成测试"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.ui_automation.models import UiProject, RecordingSession, LocatorStrategy

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username='recorder', password='test1234')


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def project(db, user):
    return UiProject.objects.create(name='RecordProject', created_by=user)


@pytest.fixture
def css_strategy(db):
    return LocatorStrategy.objects.create(
        name='css', strategy_type='css', description='CSS', priority=5
    )


class TestStartRecording:
    def test_start_returns_session_and_ws_path(self, client, project):
        resp = client.post('/api/ui-automation/recording/start/', {
            'project_id': project.id,
            'target_url': 'https://example.com',
        }, format='json')
        assert resp.status_code == 201
        assert 'session_id' in resp.data
        assert '/ws/ui-automation/recording/' in resp.data['ws_path']

    def test_start_with_invalid_project(self, client):
        resp = client.post('/api/ui-automation/recording/start/', {
            'project_id': 99999,
            'target_url': 'https://example.com',
        }, format='json')
        assert resp.status_code == 404


class TestConfirmRecording:
    def test_confirm_creates_test_case(self, client, project, css_strategy):
        session = RecordingSession.objects.create(
            project=project,
            target_url='https://example.com',
            status='confirming',
            recorded_steps=[{
                'step_number': 1,
                'action_type': 'click',
                'page_url': 'https://example.com/login',
                'element_info': {
                    'element_type': 'BUTTON',
                    'element_name': '登录',
                    'locators': [{'strategy': 'css', 'value': '#login'}],
                },
            }],
            match_results=[{
                'step_number': 1,
                'status': 'created',
                'element_id': None,
                'action_type': 'click',
                'element_info': {
                    'element_type': 'BUTTON',
                    'element_name': '登录',
                    'locators': [{'strategy': 'css', 'value': '#login'}],
                },
            }],
            created_by=client.handler._force_user,
        )
        resp = client.post(f'/api/ui-automation/recording/{session.id}/confirm/', {
            'test_case_name': '录制测试-登录流程',
            'steps': session.match_results,
        }, format='json')
        assert resp.status_code == 200
        assert resp.data['test_case_name'] == '录制测试-登录流程'
        assert resp.data['step_count'] == 1


class TestCancelRecording:
    def test_cancel_updates_status(self, client, project):
        session = RecordingSession.objects.create(
            project=project,
            target_url='https://example.com',
            status='recording',
            created_by=client.handler._force_user,
        )
        resp = client.post(f'/api/ui-automation/recording/{session.id}/cancel/')
        assert resp.status_code == 200
        assert resp.data['status'] == 'cancelled'
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest apps/ui_automation/tests/test_recording_api.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/ui_automation/recording_serializers.py apps/ui_automation/recording_views.py apps/ui_automation/urls.py apps/ui_automation/tests/test_recording_api.py
git commit -m "feat(recording): add REST API endpoints for recording session lifecycle"
```

---

### Task 6: Frontend — API Client + RecorderCanvas + RecorderToolbar

**Files:**
- Create: `frontend/src/api/recording.js`
- Create: `frontend/src/views/ui-automation/recorder/RecorderCanvas.vue`
- Create: `frontend/src/views/ui-automation/recorder/RecorderToolbar.vue`

**Interfaces:**
- Produces: `recording.js` API functions: `startRecording(data)`, `stopRecording(id)`, `getMatchResults(id)`, `confirmRecording(id, data)`, `cancelRecording(id)`
- Produces: `RecorderCanvas` component emitting `mousedown`, `mousemove`, `scroll`, `keydown` events
- Produces: `RecorderToolbar` component emitting `start`, `stop`, `navigate` events

- [ ] **Step 1: Create recording.js**

```javascript
import request from "@/utils/api";

// 创建录制会话
export function startRecording(data) {
  return request({
    url: "/ui-automation/recording/start/",
    method: "post",
    data,
  });
}

// 停止录制并触发元素匹配
export function stopRecording(sessionId) {
  return request({
    url: `/ui-automation/recording/${sessionId}/stop/`,
    method: "post",
  });
}

// 获取元素匹配结果
export function getMatchResults(sessionId) {
  return request({
    url: `/ui-automation/recording/${sessionId}/match-results/`,
    method: "get",
  });
}

// 确认录制结果并保存
export function confirmRecording(sessionId, data) {
  return request({
    url: `/ui-automation/recording/${sessionId}/confirm/`,
    method: "post",
    data,
  });
}

// 取消录制会话
export function cancelRecording(sessionId) {
  return request({
    url: `/ui-automation/recording/${sessionId}/cancel/`,
    method: "post",
  });
}
```

- [ ] **Step 2: Create RecorderCanvas.vue**

```vue
<template>
  <!-- 投屏画布：渲染 Playwright 截图帧，捕获用户操作事件 -->
  <div class="recorder-canvas-wrapper" ref="wrapperRef">
    <canvas
      ref="canvasRef"
      :width="viewportWidth"
      :height="viewportHeight"
      class="recorder-canvas"
      @mousedown="onMouseDown"
      @mousemove="onMouseMove"
      @wheel.prevent="onWheel"
      @contextmenu.prevent
      tabindex="0"
      @keydown="onKeyDown"
    />
    <!-- 文本输入浮层：点击输入框元素后弹出 -->
    <div v-if="showInputOverlay" class="input-overlay" :style="inputOverlayStyle">
      <el-input
        ref="inputRef"
        v-model="inputText"
        :placeholder="$t('recorder.inputPlaceholder')"
        @keydown.enter="submitInput"
        @keydown.esc="cancelInput"
        autofocus
      />
      <div class="input-actions">
        <el-button size="small" type="primary" @click="submitInput">{{ $t('recorder.confirm') }}</el-button>
        <el-button size="small" @click="cancelInput">{{ $t('recorder.cancel') }}</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({
  viewportWidth: { type: Number, default: 1280 },
  viewportHeight: { type: Number, default: 720 },
})

const emit = defineEmits(['mousedown', 'mousemove', 'scroll', 'keydown', 'input'])

const canvasRef = ref(null)
const wrapperRef = ref(null)
const showInputOverlay = ref(false)
const inputText = ref('')
const inputRef = ref(null)
const inputOverlayStyle = ref({})

// 缓存 Image 对象，避免每帧创建
let frameImage = null

/**
 * 渲染一帧截图到 Canvas
 * @param {string} base64Data - JPEG base64 编码的帧数据
 */
function renderFrame(base64Data) {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')

  if (!frameImage) {
    frameImage = new Image()
    frameImage.onload = () => {
      ctx.drawImage(frameImage, 0, 0, canvas.width, canvas.height)
    }
  }
  frameImage.src = `data:image/jpeg;base64,${base64Data}`
}

/**
 * 将 Canvas 上的鼠标坐标映射到 Playwright viewport 坐标
 */
function mapCoordinates(event) {
  const canvas = canvasRef.value
  const rect = canvas.getBoundingClientRect()
  const scaleX = props.viewportWidth / rect.width
  const scaleY = props.viewportHeight / rect.height
  return {
    x: Math.round((event.clientX - rect.left) * scaleX),
    y: Math.round((event.clientY - rect.top) * scaleY),
  }
}

function onMouseDown(event) {
  const { x, y } = mapCoordinates(event)
  const button = event.button === 2 ? 'right' : 'left'
  emit('mousedown', { x, y, button })
}

function onMouseMove(event) {
  // 节流：每 50ms 最多发一次
  if (onMouseMove._throttled) return
  onMouseMove._throttled = true
  setTimeout(() => { onMouseMove._throttled = false }, 50)

  const { x, y } = mapCoordinates(event)
  emit('mousemove', { x, y })
}

function onWheel(event) {
  const { x, y } = mapCoordinates(event)
  emit('scroll', { x, y, deltaX: event.deltaX, deltaY: event.deltaY })
}

function onKeyDown(event) {
  emit('keydown', { key: event.key, modifiers: {
    ctrl: event.ctrlKey,
    shift: event.shiftKey,
    alt: event.altKey,
    meta: event.metaKey,
  }})
}

/**
 * 弹出文本输入浮层（由父组件调用，当检测到点击的是输入框类元素时）
 */
function showInput(x, y) {
  const canvas = canvasRef.value
  const rect = canvas.getBoundingClientRect()
  const scaleX = rect.width / props.viewportWidth
  const scaleY = rect.height / props.viewportHeight
  inputOverlayStyle.value = {
    left: `${x * scaleX}px`,
    top: `${y * scaleY}px`,
  }
  inputText.value = ''
  showInputOverlay.value = true
  nextTick(() => inputRef.value?.focus())
}

function submitInput() {
  if (inputText.value) {
    emit('input', { text: inputText.value })
  }
  showInputOverlay.value = false
}

function cancelInput() {
  showInputOverlay.value = false
}

// 暴露方法给父组件
defineExpose({ renderFrame, showInput })
</script>

<style scoped>
.recorder-canvas-wrapper {
  position: relative;
  display: inline-block;
  background: #1a1a1a;
  border-radius: 4px;
  overflow: hidden;
}
.recorder-canvas {
  display: block;
  max-width: 100%;
  height: auto;
  cursor: crosshair;
  outline: none;
}
.input-overlay {
  position: absolute;
  z-index: 10;
  background: white;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  padding: 8px;
  min-width: 200px;
}
.input-actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
  justify-content: flex-end;
}
</style>
```

- [ ] **Step 3: Create RecorderToolbar.vue**

```vue
<template>
  <!-- 录制工具栏：URL 输入、开始/停止按钮 -->
  <div class="recorder-toolbar">
    <el-input
      v-model="targetUrl"
      :placeholder="$t('recorder.urlPlaceholder')"
      :disabled="isRecording"
      class="url-input"
      @keydown.enter="onNavigate"
    >
      <template #prepend>URL</template>
      <template #append>
        <el-button @click="onNavigate" :disabled="!targetUrl || isRecording">
          {{ $t('recorder.go') }}
        </el-button>
      </template>
    </el-input>

    <el-select v-model="selectedProjectId" :placeholder="$t('recorder.selectProject')" :disabled="isRecording" class="project-select">
      <el-option
        v-for="p in projects"
        :key="p.id"
        :label="p.name"
        :value="p.id"
      />
    </el-select>

    <div class="toolbar-actions">
      <el-button
        v-if="!isRecording"
        type="danger"
        :icon="VideoCamera"
        :disabled="!targetUrl || !selectedProjectId"
        @click="onStart"
      >
        {{ $t('recorder.startRecording') }}
      </el-button>

      <el-button
        v-else
        type="warning"
        :icon="VideoPause"
        @click="onStop"
      >
        {{ $t('recorder.stopRecording') }}
      </el-button>

      <el-button
        v-if="isRecording"
        @click="$emit('cancel')"
      >
        {{ $t('recorder.cancel') }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { VideoCamera, VideoPause } from '@element-plus/icons-vue'
import { getUiProjects } from '@/api/ui_automation'

const props = defineProps({
  isRecording: { type: Boolean, default: false },
})

const emit = defineEmits(['start', 'stop', 'navigate', 'cancel'])

const targetUrl = ref('')
const selectedProjectId = ref(null)
const projects = ref([])

onMounted(async () => {
  try {
    const resp = await getUiProjects()
    projects.value = resp.data?.results || resp.data || []
  } catch (e) {
    console.error('加载项目列表失败', e)
  }
})

function onStart() {
  emit('start', {
    projectId: selectedProjectId.value,
    targetUrl: targetUrl.value,
  })
}

function onStop() {
  emit('stop')
}

function onNavigate() {
  if (targetUrl.value) {
    emit('navigate', targetUrl.value)
  }
}

defineExpose({ targetUrl, selectedProjectId })
</script>

<style scoped>
.recorder-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}
.url-input {
  flex: 1;
  min-width: 300px;
}
.project-select {
  width: 200px;
}
.toolbar-actions {
  display: flex;
  gap: 8px;
}
</style>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/recording.js frontend/src/views/ui-automation/recorder/
git commit -m "feat(recording): add frontend API client, RecorderCanvas and RecorderToolbar components"
```

---

### Task 7: Frontend — StepList, ConfirmDialog, RecorderView + Routing

**Files:**
- Create: `frontend/src/views/ui-automation/recorder/RecorderStepList.vue`
- Create: `frontend/src/views/ui-automation/recorder/RecorderConfirmDialog.vue`
- Create: `frontend/src/views/ui-automation/recorder/RecorderView.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layout/index.vue`
- Modify: `frontend/src/locales/lang/zh-cn/ui-automation.js`
- Modify: `frontend/src/locales/lang/en/ui-automation.js`

**Interfaces:**
- Consumes: `RecorderCanvas`, `RecorderToolbar` (Task 6), recording API (Task 6)
- Produces: Complete recording UI accessible at `/ui-automation/recorder`

- [ ] **Step 1: Create RecorderStepList.vue**

```vue
<template>
  <!-- 实时步骤列表：录制过程中每个操作实时追加 -->
  <div class="step-list">
    <div class="step-list-header">
      <h4>{{ $t('recorder.steps') }} ({{ steps.length }})</h4>
    </div>
    <div class="step-list-body">
      <div v-for="step in steps" :key="step.step_number" class="step-item">
        <span class="step-number">#{{ step.step_number }}</span>
        <el-tag :type="actionTagType(step.action_type)" size="small">
          {{ step.action_type }}
        </el-tag>
        <span class="step-target" :title="step.element_info?.element_name || ''">
          {{ step.element_info?.element_name || '(no element)' }}
        </span>
        <span v-if="step.input_value" class="step-value">
          "{{ step.input_value }}"
        </span>
      </div>
      <div v-if="steps.length === 0" class="empty-hint">
        {{ $t('recorder.noStepsYet') }}
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  steps: { type: Array, default: () => [] },
})

function actionTagType(action) {
  const map = { click: 'primary', fill: 'success', hover: 'info', scroll: 'warning' }
  return map[action] || ''
}
</script>

<style scoped>
.step-list { display: flex; flex-direction: column; height: 100%; }
.step-list-header { padding: 12px 16px; border-bottom: 1px solid #e4e7ed; }
.step-list-header h4 { margin: 0; }
.step-list-body { flex: 1; overflow-y: auto; padding: 8px; }
.step-item { display: flex; align-items: center; gap: 8px; padding: 8px; border-radius: 4px; margin-bottom: 4px; background: #fafafa; }
.step-number { color: #909399; font-size: 12px; min-width: 28px; }
.step-target { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.step-value { color: #67c23a; font-size: 12px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty-hint { text-align: center; color: #c0c4cc; padding: 40px; }
</style>
```

- [ ] **Step 2: Create RecorderConfirmDialog.vue**

```vue
<template>
  <!-- 录制确认弹窗：步骤列表 + 元素匹配结果 + 编辑/保存 -->
  <el-dialog
    v-model="visible"
    :title="$t('recorder.confirmTitle')"
    width="800px"
    :close-on-click-modal="false"
  >
    <el-form :model="form" label-position="top" style="margin-bottom: 16px;">
      <el-form-item :label="$t('recorder.testCaseName')" required>
        <el-input v-model="form.testCaseName" :placeholder="$t('recorder.testCaseNamePlaceholder')" />
      </el-form-item>
    </el-form>

    <el-table :data="editableSteps" border size="small" max-height="400">
      <el-table-column type="index" label="#" width="50" />
      <el-table-column :label="$t('recorder.actionType')" width="100">
        <template #default="{ row }">
          <el-tag :type="actionTagType(row.action_type)" size="small">{{ row.action_type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('recorder.elementName')" min-width="150">
        <template #default="{ row }">
          <span v-if="row.status === 'no_element'" style="color: #c0c4cc;">—</span>
          <span v-else>{{ row.element_name || row.element_info?.element_name || '' }}</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('recorder.matchStatus')" width="140">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'reused'" type="success" size="small">{{ $t('recorder.statusReused') }}</el-tag>
          <el-tag v-else-if="row.status === 'updated'" type="warning" size="small">{{ $t('recorder.statusUpdated') }}</el-tag>
          <el-tag v-else-if="row.status === 'created'" type="primary" size="small">{{ $t('recorder.statusCreated') }}</el-tag>
          <el-tag v-else size="small" type="info">—</el-tag>
        </template>
      </el-table-column>
      <el-table-column :label="$t('recorder.inputValue')" min-width="100">
        <template #default="{ row }">
          <span v-if="row.input_value">"{{ row.input_value }}"</span>
        </template>
      </el-table-column>
      <el-table-column :label="$t('recorder.actions')" width="80" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeStep($index)">
            {{ $t('recorder.delete') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="visible = false">{{ $t('recorder.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" :disabled="!form.testCaseName" @click="onConfirm">
        {{ $t('recorder.saveTestCase') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  matchResults: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const visible = ref(false)
const saving = ref(false)
const form = ref({ testCaseName: '' })
const editableSteps = ref([])

watch(() => props.modelValue, (val) => { visible.value = val })
watch(visible, (val) => { emit('update:modelValue', val) })
watch(() => props.matchResults, (results) => {
  editableSteps.value = results.map(r => ({ ...r }))
}, { immediate: true })

function actionTagType(action) {
  const map = { click: 'primary', fill: 'success', hover: 'info', scroll: 'warning' }
  return map[action] || ''
}

function removeStep(index) {
  editableSteps.value.splice(index, 1)
  // 重新编号
  editableSteps.value.forEach((s, i) => { s.step_number = i + 1 })
}

async function onConfirm() {
  saving.value = true
  emit('confirm', {
    testCaseName: form.value.testCaseName,
    steps: editableSteps.value,
  })
}

defineExpose({ resetSaving: () => { saving.value = false } })
</script>
```

- [ ] **Step 3: Create RecorderView.vue**

```vue
<template>
  <!-- 脚本录制主页面 -->
  <div class="recorder-view">
    <RecorderToolbar
      :is-recording="isRecording"
      @start="handleStart"
      @stop="handleStop"
      @navigate="handleNavigate"
      @cancel="handleCancel"
    />

    <div class="recorder-body">
      <!-- 左侧：Canvas 投屏区 -->
      <div class="recorder-main">
        <div v-if="!isConnected" class="recorder-placeholder">
          <el-icon :size="64" color="#c0c4cc"><VideoCamera /></el-icon>
          <p>{{ $t('recorder.placeholderText') }}</p>
        </div>
        <RecorderCanvas
          v-show="isConnected"
          ref="canvasRef"
          :viewport-width="viewportWidth"
          :viewport-height="viewportHeight"
          @mousedown="sendWs({ type: 'mousedown', ...$event })"
          @mousemove="sendWs({ type: 'mousemove', ...$event })"
          @scroll="sendWs({ type: 'scroll', ...$event })"
          @keydown="sendWs({ type: 'keydown', ...$event })"
          @input="sendWs({ type: 'input', ...$event })"
        />
      </div>

      <!-- 右侧：步骤列表 -->
      <div class="recorder-sidebar">
        <RecorderStepList :steps="recordedSteps" />
      </div>
    </div>

    <!-- 确认弹窗 -->
    <RecorderConfirmDialog
      v-model="showConfirmDialog"
      :match-results="matchResults"
      @confirm="handleConfirm"
    />
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import { VideoCamera } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { startRecording, stopRecording, confirmRecording, cancelRecording } from '@/api/recording'
import RecorderCanvas from './RecorderCanvas.vue'
import RecorderToolbar from './RecorderToolbar.vue'
import RecorderStepList from './RecorderStepList.vue'
import RecorderConfirmDialog from './RecorderConfirmDialog.vue'

const router = useRouter()
const canvasRef = ref(null)

// 状态
const isRecording = ref(false)
const isConnected = ref(false)
const sessionId = ref(null)
const recordedSteps = ref([])
const matchResults = ref([])
const showConfirmDialog = ref(false)
const viewportWidth = ref(1280)
const viewportHeight = ref(720)

let ws = null

// ---- WebSocket 管理 ----

function connectWebSocket(wsPath) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${location.host}${wsPath}`
  ws = new WebSocket(url)

  ws.onopen = () => {
    isConnected.value = true
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    handleWsMessage(data)
  }

  ws.onclose = () => {
    isConnected.value = false
  }

  ws.onerror = (err) => {
    console.error('WebSocket 连接错误', err)
    ElMessage.error('WebSocket 连接失败')
  }
}

function sendWs(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data))
  }
}

function handleWsMessage(data) {
  switch (data.type) {
    case 'frame':
      // 渲染截图帧到 Canvas
      canvasRef.value?.renderFrame(data.data)
      break
    case 'action':
      // 实时追加录制步骤
      recordedSteps.value.push(data.data)
      break
    case 'status':
      // 状态更新（navigating, ready, error）
      if (data.data === 'error') {
        ElMessage.error('浏览器出现错误')
      }
      break
    case 'recording_stopped':
      // 录制已停止，请求匹配结果
      handleRecordingStopped()
      break
  }
}

// ---- 操作处理 ----

async function handleStart({ projectId, targetUrl }) {
  try {
    const resp = await startRecording({
      project_id: projectId,
      target_url: targetUrl,
      viewport_width: viewportWidth.value,
      viewport_height: viewportHeight.value,
    })
    sessionId.value = resp.data.session_id
    isRecording.value = true
    recordedSteps.value = []
    connectWebSocket(resp.data.ws_path)
  } catch (e) {
    ElMessage.error('启动录制失败: ' + (e.response?.data?.error || e.message))
  }
}

async function handleStop() {
  // 通知后端停止（通过 WebSocket 控制命令）
  sendWs({ type: 'control', action: 'stop' })
}

async function handleRecordingStopped() {
  try {
    const resp = await stopRecording(sessionId.value)
    matchResults.value = resp.data.match_results || []
    isRecording.value = false
    showConfirmDialog.value = true
  } catch (e) {
    ElMessage.error('停止录制失败')
  }
}

function handleNavigate(url) {
  sendWs({ type: 'control', action: 'navigate', url })
}

async function handleCancel() {
  if (sessionId.value) {
    await cancelRecording(sessionId.value)
  }
  cleanup()
  ElMessage.info('录制已取消')
}

async function handleConfirm({ testCaseName, steps }) {
  try {
    const resp = await confirmRecording(sessionId.value, {
      test_case_name: testCaseName,
      steps,
    })
    ElMessage.success(`测试用例「${resp.data.test_case_name}」已保存，共 ${resp.data.step_count} 步`)
    showConfirmDialog.value = false
    cleanup()
    // 跳转到测试用例管理页面
    router.push('/ui-automation/test-cases')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.error || e.message))
  }
}

function cleanup() {
  if (ws) {
    ws.close()
    ws = null
  }
  isRecording.value = false
  isConnected.value = false
  sessionId.value = null
  recordedSteps.value = []
}

onUnmounted(cleanup)
</script>

<style scoped>
.recorder-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.recorder-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}
.recorder-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1a1a1a;
  min-height: 500px;
}
.recorder-placeholder {
  text-align: center;
  color: #c0c4cc;
}
.recorder-placeholder p {
  margin-top: 16px;
  font-size: 14px;
}
.recorder-sidebar {
  width: 350px;
  border-left: 1px solid #e4e7ed;
  background: #fff;
}
</style>
```

- [ ] **Step 4: Add route and sidebar entry**

In `frontend/src/router/index.js`, add import at top alongside other ui-automation imports:

```javascript
import RecorderView from '@/views/ui-automation/recorder/RecorderView.vue'
```

Add child route under the `/ui-automation` children array:

```javascript
{
  path: 'recorder',
  name: 'UiRecorder',
  component: RecorderView,
  meta: { page: 'recorder' },
},
```

In `frontend/src/layout/index.vue`, add a new menu item after the "Dashboard" item (after the line with `/ui-automation/dashboard`):

```html
<el-menu-item index="/ui-automation/recorder">
  <el-icon><VideoCamera /></el-icon>
  <span>{{ $t("menu.scriptRecorder") }}</span>
</el-menu-item>
```

Add `VideoCamera` to the icon imports if not already present.

- [ ] **Step 5: Add i18n keys**

In `frontend/src/locales/lang/zh-cn/ui-automation.js`, add a new top-level `recorder` section:

```javascript
recorder: {
  urlPlaceholder: "输入目标网站 URL",
  selectProject: "选择项目",
  startRecording: "开始录制",
  stopRecording: "停止录制",
  go: "前往",
  cancel: "取消",
  confirm: "确认",
  steps: "录制步骤",
  noStepsYet: "开始录制后操作步骤将在此显示",
  placeholderText: "选择项目并输入 URL 后点击「开始录制」",
  inputPlaceholder: "输入文本内容，按 Enter 确认",
  confirmTitle: "确认录制结果",
  testCaseName: "测试用例名称",
  testCaseNamePlaceholder: "请输入测试用例名称",
  actionType: "操作类型",
  elementName: "元素名称",
  matchStatus: "匹配状态",
  inputValue: "输入值",
  actions: "操作",
  delete: "删除",
  saveTestCase: "保存测试用例",
  statusReused: "已匹配",
  statusUpdated: "已更新",
  statusCreated: "新增",
},
```

In `frontend/src/locales/lang/en/ui-automation.js`, add the same section:

```javascript
recorder: {
  urlPlaceholder: "Enter target website URL",
  selectProject: "Select project",
  startRecording: "Start Recording",
  stopRecording: "Stop Recording",
  go: "Go",
  cancel: "Cancel",
  confirm: "Confirm",
  steps: "Recorded Steps",
  noStepsYet: "Steps will appear here after recording starts",
  placeholderText: "Select a project and enter URL, then click Start Recording",
  inputPlaceholder: "Type text content, press Enter to confirm",
  confirmTitle: "Confirm Recording Results",
  testCaseName: "Test Case Name",
  testCaseNamePlaceholder: "Enter test case name",
  actionType: "Action",
  elementName: "Element",
  matchStatus: "Match Status",
  inputValue: "Input Value",
  actions: "Actions",
  delete: "Delete",
  saveTestCase: "Save Test Case",
  statusReused: "Matched",
  statusUpdated: "Updated",
  statusCreated: "New",
},
```

Also add to `frontend/src/locales/lang/zh-cn/menu.js` (or wherever menu labels are):

```javascript
scriptRecorder: "脚本录制",
```

And English:

```javascript
scriptRecorder: "Script Recorder",
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/ui-automation/recorder/ frontend/src/api/recording.js frontend/src/router/index.js frontend/src/layout/index.vue frontend/src/locales/
git commit -m "feat(recording): add complete recording UI with Canvas, step list, confirmation dialog, routing and i18n"
```

---
