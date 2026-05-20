# Pre-request Script & Tests — Python pm API 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Python + `pm` 对象注入替换旧的正则脚本解析器，让 Pre-request Script 和 Tests 支持完整 Python 语法及 Postman 风格 `pm.*` API；同时移除 Tests 脚本里 `assertions = {...}` 的自动解析逻辑，断言统一由"断言"Tab 的 UI 配置驱动。

**Architecture:** 后端新建 `apps/core/pm_context.py`，定义 `PmObject` 及其子代理对象，通过 Python `exec()` 注入执行上下文；`VariableResolver` 新增 `execute_pm_script()` 方法取代旧的 `parse_and_execute` / `execute_script_with_response`；`views.py` 执行流程调用新方法并将结果（变量更新、额外请求头、console 输出）写入响应；前端更新 placeholder 并在响应区新增 Console 折叠面板展示 print 输出。

**Tech Stack:** Python 3.x `exec()`、Django REST Framework、Vue 3、Element Plus

---

## 文件改动一览

| 文件 | 操作 | 说明 |
|------|------|------|
| `apps/core/pm_context.py` | **新建** | PmObject 及子代理对象 |
| `apps/core/variable_resolver.py` | **修改** | 新增 `execute_pm_script()`，保留旧方法供其他调用者 |
| `apps/api_testing/views.py` | **修改** | 执行流程换用新方法，移除 script_assertions 段 |
| `frontend/src/views/api-testing/InterfaceManagement.vue` | **修改** | 更新 placeholder、新增 Console 面板 |

---

## Task 1: 新建 `PmObject` — 核心 pm 上下文

**Files:**
- Create: `apps/core/pm_context.py`

- [ ] **Step 1: 创建文件**

```python
# apps/core/pm_context.py
import json as _json


class _EnvironmentProxy:
    def __init__(self, variables: dict):
        self._vars = variables
        self._updated: dict = {}

    def set(self, key: str, value):
        self._vars[str(key)] = value
        self._updated[str(key)] = value

    def get(self, key: str, default=None):
        return self._vars.get(str(key), default)


class _VariablesProxy(_EnvironmentProxy):
    """临时变量，行为与 environment 相同，共享同一 dict"""
    pass


class _RequestProxy:
    def __init__(self):
        self._extra_headers: dict = {}

    def headers(self):
        return self._extra_headers

    class _HeadersHelper:
        def __init__(self, proxy):
            self._proxy = proxy

        def add(self, key: str, value: str):
            self._proxy._extra_headers[str(key)] = str(value)

    def __init__(self):
        self._extra_headers: dict = {}
        self.headers = self._HeadersHelper(self)


class _ResponseProxy:
    def __init__(self, response):
        self._response = response

    def json(self):
        if self._response is None:
            return {}
        try:
            return self._response.json()
        except Exception:
            return {}

    @property
    def text(self) -> str:
        if self._response is None:
            return ''
        return self._response.text

    @property
    def code(self) -> int:
        if self._response is None:
            return 0
        return self._response.status_code

    def headers(self) -> dict:
        if self._response is None:
            return {}
        return dict(self._response.headers)


class PmObject:
    def __init__(self, variables: dict, response=None):
        self.environment = _EnvironmentProxy(variables)
        self.variables = _VariablesProxy(variables)
        self.request = _RequestProxy()
        self.response = _ResponseProxy(response)


def execute_pm_script(script: str, variables: dict, response=None) -> dict:
    """执行 Python 脚本，注入 pm 对象。

    Returns:
        {
          'variables': dict,        # 新增/修改的变量
          'extra_headers': dict,    # 需合并到请求头的额外头
          'console': list[str],     # print() 输出
          'errors': list[str],      # 执行期间的异常信息
        }
    """
    pm = PmObject(variables, response)
    console_output = []
    errors = []

    def _print(*args, **kwargs):
        sep = kwargs.get('sep', ' ')
        console_output.append(sep.join(str(a) for a in args))

    exec_context = {
        'pm': pm,
        'print': _print,
        'json': _json,
        '__builtins__': __builtins__,
    }

    try:
        exec(compile(script, '<pm_script>', 'exec'), exec_context)
    except Exception as e:
        errors.append(str(e))

    return {
        'variables': pm.environment._updated,
        'extra_headers': pm.request._extra_headers,
        'console': console_output,
        'errors': errors,
    }
```

- [ ] **Step 2: 验证模块可导入**

```bash
cd D:/python/testhub_platform-main
source venv/Scripts/activate
python -c "from apps.core.pm_context import execute_pm_script; r = execute_pm_script('pm.environment.set(\"x\", 1)', {}); print(r)"
```

期望输出：`{'variables': {'x': 1}, 'extra_headers': {}, 'console': [], 'errors': []}`

- [ ] **Step 3: 提交**

```bash
git add apps/core/pm_context.py
git commit -m "feat: add PmObject and execute_pm_script for Python script execution"
```

---

## Task 2: 在 `VariableResolver` 中暴露新方法

**Files:**
- Modify: `apps/core/variable_resolver.py`（末尾，约 944-949 行）

- [ ] **Step 1: 在文件末尾追加便捷函数**

在 `variable_resolver.py` 末尾（`parse_and_execute_script` 函数之后）追加：

```python
from apps.core.pm_context import execute_pm_script as _execute_pm_script


def run_pre_request_script(script_text: str, variables: dict) -> dict:
    """执行 pre-request 脚本，返回变量更新和额外请求头。"""
    if not script_text or not script_text.strip():
        return {'variables': {}, 'extra_headers': {}, 'console': [], 'errors': []}
    return _execute_pm_script(script_text, variables, response=None)


def run_tests_script(script_text: str, variables: dict, response) -> dict:
    """执行 tests 脚本，返回变量更新和 console 输出。"""
    if not script_text or not script_text.strip():
        return {'variables': {}, 'extra_headers': {}, 'console': [], 'errors': []}
    return _execute_pm_script(script_text, variables, response=response)
```

- [ ] **Step 2: 验证导入**

```bash
python -c "from apps.core.variable_resolver import run_pre_request_script, run_tests_script; print('OK')"
```

期望：`OK`

- [ ] **Step 3: 提交**

```bash
git add apps/core/variable_resolver.py
git commit -m "feat: expose run_pre_request_script and run_tests_script helpers"
```

---

## Task 3: 修改 `views.py` 执行流程

**Files:**
- Modify: `apps/api_testing/views.py`（Lines 1127-1173）

- [ ] **Step 1: 在文件顶部 import 区添加新导入**

找到 `views.py` 中已有的导入行（有 `from apps.core.variable_resolver import VariableResolver` 附近），添加：

```python
from apps.core.variable_resolver import run_pre_request_script, run_tests_script
```

- [ ] **Step 2: 替换执行流程中的脚本执行段**

将 Lines 1127-1173 的以下代码：

```python
            # 执行预处理脚本
            if api_request.pre_request_script:
                resolver.parse_and_execute_script(script_text=api_request.pre_request_script)

            # 替换变量
            url = executor._replace_variables(request_url or '', variables)
            url = resolver.resolve(url)

            headers = executor.prepare_headers(request_headers, variables)
            params = executor.prepare_params(request_params, variables)
            body_data, body_type = executor.prepare_body(request_body, request_method, variables)

            # 执行请求
            response, response_time = executor.execute(
                method=request_method,
                url=url,
                headers=headers,
                params=params,
                body=body_data,
                body_type=body_type
            )

            # 执行后处理脚本，提取 Tests 中的 MongoDB 断言
            script_assertions = []
            if api_request.post_request_script:
                try:
                    script_result = resolver.execute_script_with_response(api_request.post_request_script, response)
                    for _i, _sa in enumerate(script_result.get('assertions', [])):
                        _expected = _sa.get('expected')
                        if _expected is not None and isinstance(_expected, (dict, list)):
                            script_assertions.append({
                                'type': 'mongo_match',
                                'name': f'Tests断言 {_i + 1}',
                                'expected': _expected,
                            })
                except Exception as _se:
                    logger.warning(f"后处理脚本执行失败: {str(_se)}")

            # 合并运行时变量（post_request_script 中赋值的变量）
            variables.update(resolver.runtime_variables)

            # 执行断言验证
            assertions = request.data.get('assertions', api_request.assertions) or []
            for assertion in assertions:
                if assertion.get('type') == 'response_time':
                    assertion['actual_time'] = response_time
            assertions_results = execute_assertions(response, assertions + script_assertions, variables=variables)
```

替换为：

```python
            # 执行 pre-request 脚本
            pre_script_result = run_pre_request_script(
                api_request.pre_request_script or '', variables
            )
            variables.update(pre_script_result['variables'])
            pre_console = pre_script_result['console']
            # 将脚本中设置的额外请求头合并进去
            if pre_script_result['extra_headers']:
                if isinstance(request_headers, list):
                    for k, v in pre_script_result['extra_headers'].items():
                        request_headers.append({'key': k, 'value': v, 'enabled': True})
                elif isinstance(request_headers, dict):
                    request_headers.update(pre_script_result['extra_headers'])

            # 替换变量
            url = executor._replace_variables(request_url or '', variables)
            url = resolver.resolve(url)

            headers = executor.prepare_headers(request_headers, variables)
            params = executor.prepare_params(request_params, variables)
            body_data, body_type = executor.prepare_body(request_body, request_method, variables)

            # 执行请求
            response, response_time = executor.execute(
                method=request_method,
                url=url,
                headers=headers,
                params=params,
                body=body_data,
                body_type=body_type
            )

            # 执行 tests 脚本（仅变量赋值 + console 输出，不再提取断言）
            tests_console = []
            if api_request.post_request_script:
                tests_result = run_tests_script(
                    api_request.post_request_script, variables, response
                )
                variables.update(tests_result['variables'])
                tests_console = tests_result['console']

            # 执行断言验证（断言完全由 Assertions UI 配置驱动）
            assertions = request.data.get('assertions', api_request.assertions) or []
            for assertion in assertions:
                if assertion.get('type') == 'response_time':
                    assertion['actual_time'] = response_time
            assertions_results = execute_assertions(response, assertions, variables=variables)
```

- [ ] **Step 3: 在响应数据中加入 console 输出**

找到 Lines 1204-1205：

```python
            history_data = RequestHistorySerializer(history).data
            history_data['assertions_results'] = assertions_results
```

改为：

```python
            history_data = RequestHistorySerializer(history).data
            history_data['assertions_results'] = assertions_results
            history_data['console_output'] = pre_console + tests_console
```

- [ ] **Step 4: 验证后端启动无错误**

```bash
python manage.py check
```

期望：`System check identified no issues (0 silenced).`

- [ ] **Step 5: 提交**

```bash
git add apps/api_testing/views.py
git commit -m "feat: replace legacy script parser with pm-based execution in execute view"
```

---

## Task 4: 前端 — 更新 placeholder

**Files:**
- Modify: `frontend/src/views/api-testing/InterfaceManagement.vue`（Lines 437-501）

- [ ] **Step 1: 更新 Pre-request Script placeholder（Line 443）**

将：
```
placeholder="// 请求前脚本，使用JavaScript语法"
```
改为：
```
placeholder="# 使用 Python 语法，通过 pm 对象操作变量
# pm.environment.set('token', 'value')   # 设置环境变量
# val = pm.environment.get('base_url')   # 读取变量
# pm.request.headers.add('X-Key', 'v')  # 添加请求头
# print('debug info')                    # 控制台输出"
```

- [ ] **Step 2: 更新 Tests placeholder（Line 476）**

将：
```
placeholder="// 请求后脚本和测试，使用JavaScript语法"
```
改为：
```
placeholder="# 使用 Python 语法，通过 pm 对象提取响应数据
# data = pm.response.json()
# pm.environment.set('token', data['data']['token'])
# print('status:', pm.response.code)"
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/api-testing/InterfaceManagement.vue
git commit -m "feat: update script editor placeholders to Python pm syntax"
```

---

## Task 5: 前端 — 新增 Console 折叠面板

**Files:**
- Modify: `frontend/src/views/api-testing/InterfaceManagement.vue`（响应区，约 Lines 1153-1160 附近）

- [ ] **Step 1: 在 "断言结果" tab-pane 之后添加 Console tab-pane**

找到响应区的 `<el-tab-pane ... name="assertions" ...>` 标签块结束位置（约 Line 1160 区域），在其**之后**插入：

```vue
<el-tab-pane
  label="Console"
  name="console"
  v-if="response.console_output && response.console_output.length > 0"
>
  <div class="console-output">
    <div
      v-for="(line, idx) in response.console_output"
      :key="idx"
      class="console-line"
    >{{ line }}</div>
  </div>
</el-tab-pane>
```

- [ ] **Step 2: 添加 Console 样式**

在文件末尾 `<style scoped>` 区块中追加：

```css
.console-output {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  min-height: 80px;
  max-height: 300px;
  overflow-y: auto;
}
.console-line {
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/api-testing/InterfaceManagement.vue
git commit -m "feat: add Console output panel to response area"
```

---

## Task 6: 手工冒烟测试

- [ ] **Step 1: 启动后端**

```bash
cd D:/python/testhub_platform-main
source venv/Scripts/activate
python manage.py runserver
```

- [ ] **Step 2: 启动前端**

```bash
cd D:/python/testhub_platform-main/frontend
"D:/software/Node/node.exe" node_modules/vite/bin/vite.js
```

- [ ] **Step 3: 测试 Pre-request Script 变量设置**

在任意接口的 Pre-request Script 中输入：
```python
pm.environment.set("test_var", "hello_from_script")
print("pre-request ran")
```
发送请求后：
- 响应区出现 **Console** tab，内容为 `pre-request ran`
- 若接口 URL 含 `{{test_var}}`，应被替换为 `hello_from_script`

- [ ] **Step 4: 测试 Tests 脚本提取响应字段**

在 Tests 中输入：
```python
data = pm.response.json()
print("status code:", pm.response.code)
pm.environment.set("last_status", str(pm.response.code))
```
发送请求后：Console tab 显示 `status code: 200`（或实际状态码）。

- [ ] **Step 5: 确认断言 Tab 正常工作**

在"断言"Tab 添加一条"状态码"断言（期望 200），发送请求，断言结果 tab 正常展示 passed/failed。

- [ ] **Step 6: 确认旧 `assertions = {...}` 不再产生断言**

在 Tests 中输入：
```python
assertions = {"code": 0}
```
发送请求，断言结果 tab 中**不应**出现由脚本生成的额外断言条目。
