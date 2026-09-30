# UI 自动化脚本录制功能设计

**Date:** 2026-08-25
**Status:** Approved
**Scope:** 后端录制引擎 + WebSocket 投屏 + 元素匹配 + 前端录制界面

## 目标

在 TestHub UI 自动化模块中新增"脚本录制"功能。用户在 TestHub Web 界面中操作目标网站，系统自动捕获操作并生成 TestCaseStep，同时将录制到的元素与项目元素库智能匹配——已有的复用、变更的更新定位器、确实没有的才新增。

支持服务端本地和远端客户端通过浏览器打开 TestHub 界面使用。

## 技术方案

采用 **Playwright CDP 远程投屏**方案：后端启动 Playwright 浏览器打开目标网站，通过 CDP `Page.startScreencast` 获取画面帧，经 WebSocket 实时推送到前端 Canvas；用户在 Canvas 上的操作通过 WebSocket 回传后端，由 Playwright 在真实浏览器上执行。

## 整体架构

```
用户浏览器 (Vue)                    TestHub 后端 (Django)
┌─────────────────────┐           ┌─────────────────────────┐
│  RecorderView.vue   │           │  RecordingSession       │
│  ┌───────────────┐  │  WS帧流   │  ┌───────────────────┐  │
│  │ Canvas 投屏   │◄─┼──────────┼──│ Playwright Browser │  │
│  │ (用户在此操作) │──┼──────────┼─►│ CDP screencast     │  │
│  └───────────────┘  │  WS事件   │  └───────────────────┘  │
│  ┌───────────────┐  │           │  ┌───────────────────┐  │
│  │ 步骤列表实时   │◄─┼──────────┼──│ ActionRecorder     │  │
│  │ 展示已录制步骤 │  │           │  │ (捕获+提取定位器)  │  │
│  └───────────────┘  │           │  └───────────────────┘  │
│  ┌───────────────┐  │           │  ┌───────────────────┐  │
│  │ 录制完成确认   │──┼──────────┼─►│ ElementMatcher     │  │
│  │ 元素关联审核   │◄─┼──────────┼──│ (匹配/更新/新增)   │  │
│  └───────────────┘  │           │  └───────────────────┘  │
└─────────────────────┘           └─────────────────────────┘
```

**三个后端核心组件：**

1. **RecordingConsumer** — Django Channels WebSocket consumer，管理 Playwright 浏览器生命周期，处理投屏帧推送和输入事件转发
2. **ActionRecorder** — 拦截 Playwright 动作，通过 CDP 提取元素信息和多种候选定位器，生成录制记录
3. **ElementMatcher** — 将录制到的元素与项目元素库三层匹配，决定复用/更新/新增

## WebSocket 通信协议

连接路径：`ws://<host>/ws/ui-automation/recording/<session_id>/`

### 后端 → 前端

- `{type: "frame", data: "<base64 jpeg>"}` — 截图帧，约 10-15 fps，JPEG 质量 60-70
- `{type: "action", data: {step_number, action_type, locator, element_info, input_value}}` — 录制到一个操作
- `{type: "status", data: "navigating"|"ready"|"error"}` — 状态变更

### 前端 → 后端

- `{type: "mousedown", x, y, button}` — 鼠标点击
- `{type: "mousemove", x, y}` — 鼠标移动（hover）
- `{type: "keydown", key, modifiers}` — 键盘输入
- `{type: "scroll", x, y, deltaX, deltaY}` — 滚动
- `{type: "input", text}` — 文本输入（前端弹出输入框，一次性发送完整文本作为 fill 操作）
- `{type: "control", action: "start"|"stop"|"navigate", url: "..."}` — 控制录制流程

### 投屏实现细节

- Canvas 尺寸与 Playwright viewport 一致，默认 1280x720
- 鼠标坐标按 Canvas 实际尺寸与 viewport 的比例换算
- 文本输入不逐键发送，在前端弹出输入框填写后一次性发送 fill 操作

## ActionRecorder — 操作捕获与定位器提取

### 捕获时机

不监听 DOM 事件，而是在后端将用户输入事件转换为 Playwright 操作时同步记录：

```
用户 Canvas 点击 (x=200, y=300)
  → Playwright page.mouse.click(200, 300)
  → 同时通过 CDP 在 (200,300) 处获取元素信息
  → 生成一条录制记录
```

### 录制记录结构

```python
{
    "step_number": 1,
    "action_type": "click",           # click/fill/hover/scroll 等
    "input_value": "",                # fill 操作的输入内容
    "page_url": "https://...",        # 当前页面 URL
    "element_info": {
        "tag_name": "button",
        "text_content": "Submit",
        "element_type": "BUTTON",     # 自动推断，映射到 Element.ELEMENT_TYPE_CHOICES
        "locators": [                 # 多个候选定位器
            {"strategy": "test-id", "value": "submit-btn"},
            {"strategy": "text", "value": "Submit"},
            {"strategy": "css", "value": "#form > button.primary"},
            {"strategy": "xpath", "value": "//button[text()='Submit']"}
        ],
        "screenshot": "<base64>"      # 元素截图缩略图
    }
}
```

### 定位器生成优先级

1. `data-testid` / `data-test` 属性 → `test-id` 策略
2. `id` 属性（非动态生成的） → `id` 策略
3. `placeholder` / `aria-label` → `placeholder` / `label` 策略
4. 可见文本 → `text` 策略
5. CSS selector → `css` 策略
6. XPath → `xpath` 策略（兜底）

通过 CDP `DOM.describeNode` + `DOM.getAttributes` + `DOM.getOuterHTML` 获取元素信息，不依赖页面注入 JS。

## ElementMatcher — 元素匹配逻辑

核心原则：**匹配优先、变更更新、仅缺失才新增。**

### 三层匹配流程

```
录制到的元素 (带多个候选定位器)
  │
  ├─ 第1层: 精确匹配
  │   查找条件：同项目 + 同页面 + 任一定位器（主定位器或备用定位器）完全一致
  │   → 命中: 直接复用，不做任何修改
  │
  ├─ 第2层: 模糊匹配 (元素变更场景)
  │   查找条件：同项目 + 同页面 + 满足以下任一:
  │     a) text/placeholder 内容相同 + css/xpath 变了
  │     b) test-id 相同 + 其他定位器变了
  │     c) 元素类型相同 + 名称编辑距离 < 阈值
  │   → 命中: 更新该元素的定位器（见下方更新策略）
  │
  └─ 第3层: 无匹配
      → 自动创建新 Element，归入该页面的默认分组
```

### 更新策略

- 新的最高优先级定位器成为主定位器（`locator_strategy` + `locator_value`）
- 其他候选定位器存入 `backup_locators`
- 保留原元素的 `name`、`description`、`group` 等人工维护的字段不动
- 更新 `last_validated` 为当前时间，`validation_status` 设为 `VALID`

### 匹配结果标记

- **复用** — 精确匹配命中，元素无变化
- **已更新** — 模糊匹配命中，定位器已更新
- **新增** — 无匹配，将创建新元素

## 数据模型

### 新增模型：RecordingSession

```python
class RecordingSession(models.Model):
    """录制会话模型"""
    STATUS_CHOICES = [
        ('recording', '录制中'),
        ('matching', '元素匹配中'),
        ('confirming', '待确认'),
        ('saved', '已保存'),
        ('cancelled', '已取消'),
    ]
    project = models.ForeignKey(UiProject, on_delete=models.CASCADE)
    test_case = models.ForeignKey(TestCase, null=True, blank=True, on_delete=models.SET_NULL)
    target_url = models.URLField(verbose_name='录制目标URL')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='recording')
    recorded_steps = models.JSONField(default=list, verbose_name='录制的原始步骤数据')
    match_results = models.JSONField(default=list, verbose_name='元素匹配结果')
    viewport_width = models.IntegerField(default=1280)
    viewport_height = models.IntegerField(default=720)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
```

原始步骤暂存在 `recorded_steps` JSONField 中，确认保存后写入已有的 `TestCaseStep` 表。不新增 Step 模型。

## API 端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/ui-automation/recording/start/` | POST | 创建录制会话，返回 session_id 和 ws 地址 |
| `/api/ui-automation/recording/<id>/stop/` | POST | 停止录制，触发元素匹配 |
| `/api/ui-automation/recording/<id>/match-results/` | GET | 获取匹配结果供前端确认 |
| `/api/ui-automation/recording/<id>/confirm/` | POST | 确认保存为 TestCase + Steps + 元素变更 |
| `/api/ui-automation/recording/<id>/cancel/` | POST | 取消录制会话 |
| `ws://host/ws/ui-automation/recording/<id>/` | WebSocket | 实时投屏和操作转发 |

## 前端组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `RecorderView.vue` | `views/ui-automation/recorder/` | 主录制页面：Canvas 投屏区 + 步骤列表 + 控制栏 |
| `RecorderCanvas.vue` | 同上 | Canvas 画布，渲染帧流，捕获鼠标/键盘事件转发 WS |
| `RecorderToolbar.vue` | 同上 | 顶部工具栏：URL 输入、开始/停止/暂停、viewport 设置 |
| `RecorderStepList.vue` | 同上 | 右侧实时步骤列表 |
| `RecorderConfirmDialog.vue` | 同上 | 录制完成确认弹窗：步骤 + 匹配结果 + 编辑/保存 |

### 用户操作流程

1. 进入 UI 自动化 → 侧栏"脚本录制"
2. 输入目标 URL → 选择所属项目 → 点击"开始录制"
3. 左侧 Canvas 显示目标网站，右侧实时步骤列表
4. 用户在 Canvas 上操作，每个操作实时追加到步骤列表
5. 点击"停止录制"
6. 确认弹窗展示匹配结果：
   - 🟢 复用 — "登录按钮 (已匹配)"
   - 🟠 更新 — "搜索框 (定位器已更新)"
   - 🔵 新增 — 可编辑名称、选择分组、或手动关联已有元素
7. 用户可删除/调整步骤，修改元素关联
8. 点击"保存" → 输入测试用例名称 → 写入 TestCase + TestCaseSteps

### 路由新增

`/ui-automation/recorder` 加入 Vue Router，侧栏导航添加入口。

## 依赖新增

- `channels` + `daphne` — Django ASGI/WebSocket 支持
- 项目当前使用 WSGI，需升级为 WSGI + ASGI 混合部署（HTTP 走 WSGI，WebSocket 走 ASGI）

## 文件变更清单

### 后端新增

| 文件 | 说明 |
|------|------|
| `apps/ui_automation/recording/consumer.py` | WebSocket consumer，管理 Playwright 浏览器和投屏 |
| `apps/ui_automation/recording/action_recorder.py` | 操作捕获 + CDP 元素信息提取 + 定位器生成 |
| `apps/ui_automation/recording/element_matcher.py` | 三层元素匹配逻辑 |
| `apps/ui_automation/recording/__init__.py` | 模块初始化 |
| `apps/ui_automation/recording_views.py` | REST API（start/stop/confirm/cancel） |
| `apps/ui_automation/recording_serializers.py` | 序列化器 |
| `backend/routing.py` | ASGI WebSocket 路由 |
| `backend/asgi.py` | ASGI 应用配置（新增或修改） |

### 后端修改

| 文件 | 说明 |
|------|------|
| `apps/ui_automation/models.py` | 新增 RecordingSession 模型 |
| `apps/ui_automation/urls.py` | 新增录制 API 路由 |
| `backend/settings.py` | 添加 channels 到 INSTALLED_APPS |
| `requirements.txt` | 添加 channels、daphne |

### 前端新增

| 文件 | 说明 |
|------|------|
| `frontend/src/views/ui-automation/recorder/RecorderView.vue` | 主录制页面 |
| `frontend/src/views/ui-automation/recorder/RecorderCanvas.vue` | Canvas 投屏组件 |
| `frontend/src/views/ui-automation/recorder/RecorderToolbar.vue` | 工具栏 |
| `frontend/src/views/ui-automation/recorder/RecorderStepList.vue` | 步骤列表 |
| `frontend/src/views/ui-automation/recorder/RecorderConfirmDialog.vue` | 确认弹窗 |
| `frontend/src/api/recording.js` | 录制 API 调用 |

### 前端修改

| 文件 | 说明 |
|------|------|
| `frontend/src/views/ui-automation/Index.vue` | 侧栏添加"脚本录制"菜单 |
| `frontend/src/router/` | 添加 `/ui-automation/recorder` 路由 |
| `frontend/src/locales/lang/zh-cn/ui-automation.js` | 中文 i18n |
| `frontend/src/locales/lang/en/ui-automation.js` | 英文 i18n |

## 代码注释要求

所有新增代码文件必须包含清晰的中文注释，包括：
- 文件顶部的模块说明
- 类和方法的 docstring
- 关键逻辑处的行内注释（特别是 CDP 调用、定位器生成策略、元素匹配算法）

## 不在范围内

- 录制回放（录制产物是 TestCase，通过现有执行引擎回放）
- 录制断言（用户在确认阶段手动添加断言步骤）
- 多标签页录制（首期只支持单标签页）
- 移动端录制
