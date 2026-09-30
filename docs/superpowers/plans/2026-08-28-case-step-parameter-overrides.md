# Case & Step Parameter Overrides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow test cases and individual steps to override project-level `{{paramName}}` variables, so the same element (with a parameterized locator) can be reused across test cases with different variable values.

**Architecture:** Add `case_parameters` (JSONField) on `TestCase` and `step_parameters` (JSONField) on `TestCaseStep`. Modify the parameter resolution function to accept an optional override dict that merges step > case > project parameters. Both engines and the frontend step editor get updated to pass and edit these new fields.

**Tech Stack:** Django 4.x, Django REST Framework, Vue 3 + Element Plus, Playwright/Selenium engines

## Global Constraints

- Resolution priority: step_parameters > case_parameters > project parameters (DB)
- `{{paramName}}` syntax unchanged — no new syntax
- Both Playwright and Selenium engines must behave identically
- JSONField stores `{"param_name": "value", ...}` — flat key-value, same shape as project parameters
- Backward-compatible: existing test cases with no parameters continue to work (empty dict default)

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `apps/ui_automation/models.py:688-765` | Add `case_parameters` to `TestCase`, `step_parameters` to `TestCaseStep` |
| Create | `apps/ui_automation/migrations/0011_case_step_parameters.py` | Auto-generated migration |
| Modify | `apps/ui_automation/parameter_resolver.py` | Accept `overrides` dict in `resolve_project_parameters()` |
| Modify | `apps/ui_automation/serializers.py:526-555` | Include new JSON fields in serializers |
| Modify | `apps/ui_automation/views.py:1130-1280` | Persist new fields in `perform_create`/`perform_update`; pass `case_parameters` into engine execution |
| Modify | `apps/ui_automation/views.py:1493-1670` | Build merged overrides dict in `run()` action and pass to engines |
| Modify | `apps/ui_automation/playwright_engine.py:17-36,140-266` | Accept + use overrides in `__init__` and `execute_step` |
| Modify | `apps/ui_automation/selenium_engine.py` (same pattern) | Accept + use overrides in `__init__` and `execute_step` |
| Modify | `apps/ui_automation/test_executor.py` | Pass case_parameters/step_parameters through suite execution |
| Modify | `frontend/src/views/ui-automation/test-cases/TestCaseManager.vue` | UI for editing case_parameters and step_parameters |
| Modify | `frontend/src/api/ui_automation.js` | No change needed — generic PATCH/POST already sends all data |
| Modify | `frontend/src/locales/lang/zh-cn/ui-automation.js` | i18n keys for new UI |
| Modify | `frontend/src/locales/lang/en/ui-automation.js` | i18n keys for new UI |

---

### Task 1: Model + Migration + Parameter Resolver

**Files:**
- Modify: `apps/ui_automation/models.py:688-765`
- Modify: `apps/ui_automation/parameter_resolver.py`
- Create: `apps/ui_automation/migrations/0011_case_step_parameters.py` (auto-generated)

**Interfaces:**
- Produces: `TestCase.case_parameters` (JSONField, default=dict), `TestCaseStep.step_parameters` (JSONField, default=dict)
- Produces: `resolve_project_parameters(text, project_id, cache=None, overrides=None)` — `overrides` is an optional `dict` that takes priority over DB values

- [ ] **Step 1: Add `case_parameters` field to `TestCase` model**

In `apps/ui_automation/models.py`, after line 711 (`updated_at` field), add:

```python
case_parameters = models.JSONField(default=dict, blank=True, verbose_name='用例级参数覆盖')
```

- [ ] **Step 2: Add `step_parameters` field to `TestCaseStep` model**

In `apps/ui_automation/models.py`, after line 753 (`assert_value` field), add:

```python
step_parameters = models.JSONField(default=dict, blank=True, verbose_name='步骤级参数覆盖')
```

- [ ] **Step 3: Generate migration**

```bash
cd D:\python\testhub_platform-main
python manage.py makemigrations ui_automation --name case_step_parameters
```

Expected: creates `apps/ui_automation/migrations/0011_case_step_parameters.py`

- [ ] **Step 4: Apply migration**

```bash
python manage.py migrate ui_automation
```

Expected: two columns added, existing rows get `{}` default.

- [ ] **Step 5: Update `resolve_project_parameters()` to accept overrides**

In `apps/ui_automation/parameter_resolver.py`, modify the function signature and `_replace` logic:

```python
def resolve_project_parameters(text, project_id, cache=None, overrides=None):
    """把 text 里的 "{{参数名}}" 替换成对应的参数值。

    解析优先级: overrides > 项目参数 (UiProjectParameter)。

    Args:
        text: 待解析的原始文本。
        project_id: 归属项目 id。
        cache: 可选，批量执行时复用的缓存 dict。
        overrides: 可选，额外的键值对 dict，优先于项目参数；
            典型用法是把 step_parameters 与 case_parameters 合并后传入，
            step 层的同名 key 会覆盖 case 层（调用方负责合并顺序）。

    Returns:
        替换后的文本。找不到对应参数的 "{{name}}" 原样保留。
    """
    if not text or '{{' not in text:
        return text

    # 即使 project_id 为 None，只要有 overrides 也能解析
    params = _load_params(project_id, cache) if project_id is not None else {}

    if overrides:
        params = {**params, **overrides}

    if not params:
        return text

    def _replace(match):
        name = match.group(1)
        return params.get(name, match.group(0))

    return _PARAM_PATTERN.sub(_replace, text)
```

- [ ] **Step 6: Verify migration applied and models work**

```bash
python manage.py shell -c "
from apps.ui_automation.models import TestCase, TestCaseStep
tc = TestCase.objects.first()
if tc:
    print('case_parameters:', tc.case_parameters)
    step = tc.steps.first()
    if step:
        print('step_parameters:', step.step_parameters)
print('OK')
"
```

Expected: prints `{}` for both fields, then `OK`.

- [ ] **Step 7: Commit**

```bash
git add apps/ui_automation/models.py apps/ui_automation/parameter_resolver.py apps/ui_automation/migrations/0011_case_step_parameters.py
git commit -m "feat: add case_parameters and step_parameters fields with resolver overrides"
```

---

### Task 2: Serializers + Views (Backend API)

**Files:**
- Modify: `apps/ui_automation/serializers.py:526-555`
- Modify: `apps/ui_automation/views.py:1130-1280` (perform_create/perform_update)

**Interfaces:**
- Consumes: `TestCase.case_parameters`, `TestCaseStep.step_parameters` from Task 1
- Produces: API endpoints that accept and return `case_parameters` on TestCase and `step_parameters` on each step

- [ ] **Step 1: Add `step_parameters` to `TestCaseStepSerializer`**

In `apps/ui_automation/serializers.py`, update the `TestCaseStepSerializer.Meta.fields` list (line 533-536):

```python
class TestCaseStepSerializer(serializers.ModelSerializer):
    """测试用例步骤序列化器"""
    element_name = serializers.CharField(source='element.name', read_only=True)
    element_locator = serializers.CharField(source='element.locator_value', read_only=True)

    class Meta:
        model = TestCaseStep
        fields = [
            'id', 'step_number', 'action_type', 'element', 'element_name', 'element_locator',
            'input_value', 'wait_time', 'assert_type', 'assert_value', 'step_parameters',
            'description', 'created_at'
        ]
```

- [ ] **Step 2: Add `case_parameters` to `TestCaseSerializer`**

In `apps/ui_automation/serializers.py`, update the `TestCaseSerializer.Meta.fields` list (line 547-550):

```python
class TestCaseSerializer(serializers.ModelSerializer):
    """测试用例序列化器"""
    steps = TestCaseStepSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = TestCase
        fields = [
            'id', 'name', 'description', 'project', 'project_name', 'status', 'priority',
            'case_parameters', 'created_by', 'created_by_name', 'created_at', 'updated_at', 'steps'
        ]
        read_only_fields = ['created_by']
```

- [ ] **Step 3: Persist `step_parameters` in `perform_create`**

In `apps/ui_automation/views.py`, inside `perform_create` (around line 1163), add `step_parameters` to the `TestCaseStep.objects.create()` call:

```python
TestCaseStep.objects.create(
    test_case=instance,
    step_number=step_data.get('step_number', i + 1),
    action_type=step_data.get('action_type', 'click'),
    element_id=step_data.get('element') if step_data.get('element') else None,
    input_value=step_data.get('input_value', ''),
    wait_time=step_data.get('wait_time', 1000),
    assert_type=step_data.get('assert_type', ''),
    assert_value=step_data.get('assert_value', ''),
    step_parameters=step_data.get('step_parameters', {}),
    description=step_data.get('description', '')
)
```

- [ ] **Step 4: Persist `step_parameters` in `perform_update`**

Same change in `perform_update` (around line 1264):

```python
TestCaseStep.objects.create(
    test_case=instance,
    step_number=step_data.get('step_number', i + 1),
    action_type=step_data.get('action_type', 'click'),
    element_id=step_data.get('element') if step_data.get('element') else None,
    input_value=step_data.get('input_value', ''),
    wait_time=step_data.get('wait_time', 1000),
    assert_type=step_data.get('assert_type', ''),
    assert_value=step_data.get('assert_value', ''),
    step_parameters=step_data.get('step_parameters', {}),
    description=step_data.get('description', '')
)
```

- [ ] **Step 5: Persist `step_parameters` in `copy_case`**

Find the `copy_case` action (around line 1181) and ensure `step_parameters` is copied. Search for where steps are duplicated and add:

```python
step_parameters=step.step_parameters,
```

Also copy `case_parameters` when duplicating the test case itself.

- [ ] **Step 6: Verify API returns new fields**

```bash
python manage.py shell -c "
from apps.ui_automation.serializers import TestCaseSerializer
from apps.ui_automation.models import TestCase
tc = TestCase.objects.first()
if tc:
    s = TestCaseSerializer(tc)
    print('case_parameters' in s.data)
    if s.data.get('steps'):
        print('step_parameters' in s.data['steps'][0])
print('OK')
"
```

Expected: `True`, `True`, `OK`

- [ ] **Step 7: Commit**

```bash
git add apps/ui_automation/serializers.py apps/ui_automation/views.py
git commit -m "feat: expose case_parameters and step_parameters in API serializers and views"
```

---

### Task 3: Engine Integration (Playwright + Selenium)

**Files:**
- Modify: `apps/ui_automation/playwright_engine.py:17-36,140-266`
- Modify: `apps/ui_automation/selenium_engine.py` (same locations)
- Modify: `apps/ui_automation/views.py:1493-1670` (run action)
- Modify: `apps/ui_automation/test_executor.py`

**Interfaces:**
- Consumes: `resolve_project_parameters(text, project_id, cache, overrides)` from Task 1
- Consumes: `TestCase.case_parameters`, `TestCaseStep.step_parameters` from Task 1
- Produces: engines resolve `{{paramName}}` using merged step > case > project parameters

- [ ] **Step 1: Add `case_parameters` to PlaywrightTestEngine `__init__`**

In `apps/ui_automation/playwright_engine.py`, update `__init__` (line 20):

```python
def __init__(self, browser_type='chromium', headless=True, remote_service=None, project_id=None, case_parameters=None):
    self.browser_type = browser_type
    self.headless = headless
    self.remote_service = remote_service
    self.project_id = project_id
    self.case_parameters = case_parameters or {}
    self.playwright = None
    self.browser: Optional[Browser] = None
    self.context: Optional[BrowserContext] = None
    self.page: Optional[Page] = None
```

- [ ] **Step 2: Build merged overrides in Playwright `execute_step`**

In `apps/ui_automation/playwright_engine.py`, at the top of `execute_step` (around line 145), after the existing variable resolution block, replace the three resolution sites (input_value, assert_value, locator_value) to use overrides.

Add a helper at the top of `execute_step`:

```python
step_params = getattr(step, 'step_parameters', None) or {}
overrides = {**self.case_parameters, **step_params} if (self.case_parameters or step_params) else None
```

Then change all three `resolve_project_parameters` calls to pass `overrides`:

For `input_value` (line 152):
```python
resolved_input_value = resolve_project_parameters(step.input_value, self.project_id, overrides=overrides)
```

For `assert_value` (line 157):
```python
resolved_assert_value = resolve_project_parameters(step.assert_value, self.project_id, overrides=overrides)
```

For `locator_value` (line 265):
```python
locator_value = resolve_project_parameters(locator_value, self.project_id, overrides=overrides)
```

Also update the `navigate` method's `resolve_project_parameters` call (line 820) to pass `overrides=overrides` — but since `navigate` doesn't have step context, use only `case_parameters`:

```python
resolved_url = resolve_project_parameters(url, self.project_id, overrides=self.case_parameters if self.case_parameters else None)
```

- [ ] **Step 3: Same changes for SeleniumTestEngine**

Apply identical changes to `apps/ui_automation/selenium_engine.py`:
- Add `case_parameters=None` to `__init__`
- Build `overrides` dict at top of `execute_step`
- Pass `overrides` to all three `resolve_project_parameters` calls (input_value at line 212, assert_value at line 217, locator_value at line 309)
- Update `navigate` method (line 849) to pass `overrides`

- [ ] **Step 4: Pass `case_parameters` and `step_parameters` through the `run` action**

In `apps/ui_automation/views.py`, in the `run` action (starting at line 1493):

4a. When building `steps_data` (around line 1567-1590), add `step_parameters` to each step's data:

```python
step_data = {
    'step': step,
    'action_type': step.action_type,
    'description': step.description,
    'input_value': step.input_value,
    'wait_time': step.wait_time,
    'assert_type': step.assert_type,
    'assert_value': step.assert_value,
    'step_parameters': step.step_parameters,
}
```

4b. When creating the Selenium engine (around line 1623), pass `case_parameters`:

```python
engine = SeleniumTestEngine(
    browser_type=browser_type, headless=headless, remote_service=remote_service,
    project_id=test_case.project_id,
    case_parameters=test_case.case_parameters,
)
```

4c. When creating the Playwright engine (search for `PlaywrightTestEngine(` in the `run` method), pass `case_parameters`:

```python
engine = PlaywrightTestEngine(
    browser_type=browser_mapping.get(browser, 'chromium'),
    headless=headless,
    remote_service=remote_service,
    project_id=test_case.project_id,
    case_parameters=test_case.case_parameters,
)
```

4d. The `step` object passed to `engine.execute_step(step, element_data)` already carries `step_parameters` as a model attribute, so the engine's `getattr(step, 'step_parameters', None)` will pick it up. However, since `steps_data` uses a dict wrapper for `step`, ensure the `step` object (the actual model instance) is what gets passed. Check that the code passes `sd['step']` (the model instance) to `execute_step`, not the dict.

- [ ] **Step 5: Update test_executor.py for suite execution**

In `apps/ui_automation/test_executor.py`, find where engines are instantiated and pass `case_parameters`:

```python
engine = PlaywrightTestEngine(
    ...,
    case_parameters=test_case.case_parameters,
)
```

and for Selenium:

```python
engine = SeleniumTestEngine(
    ...,
    case_parameters=test_case.case_parameters,
)
```

- [ ] **Step 6: Manual verification**

Create a test case with `case_parameters = {"env": "staging"}` and a step with `step_parameters = {"env": "production"}`. The step should resolve `{{env}}` to `"production"` (step wins). A step without `step_parameters` should resolve to `"staging"` (case wins). With neither, it falls back to the project parameter.

- [ ] **Step 7: Commit**

```bash
git add apps/ui_automation/playwright_engine.py apps/ui_automation/selenium_engine.py apps/ui_automation/views.py apps/ui_automation/test_executor.py
git commit -m "feat: engines resolve parameters with step > case > project priority"
```

---

### Task 4: Frontend — Case Parameters Editor

**Files:**
- Modify: `frontend/src/views/ui-automation/test-cases/TestCaseManager.vue`
- Modify: `frontend/src/locales/lang/zh-cn/ui-automation.js`
- Modify: `frontend/src/locales/lang/en/ui-automation.js`

**Interfaces:**
- Consumes: API returns `case_parameters` on TestCase, `step_parameters` on each step (Task 2)
- Produces: UI for editing case-level parameters (key-value table), step-level parameter overrides (inline key-value editor per step)

- [ ] **Step 1: Add i18n keys for Chinese**

In `frontend/src/locales/lang/zh-cn/ui-automation.js`, inside the `testCase` block (after line 1188):

```javascript
caseParameters: "用例参数",
caseParametersHint: "用例级参数覆盖项目参数，对该用例所有步骤生效",
stepParameters: "步骤参数",
stepParametersHint: "步骤级参数覆盖用例参数和项目参数，仅对当前步骤生效",
paramName: "参数名",
paramValue: "参数值",
addParameter: "添加参数",
noParameters: "暂无参数覆盖",
parameterOverrides: "参数覆盖",
inheritFromCase: "继承用例参数",
inheritFromProject: "继承项目参数",
```

- [ ] **Step 2: Add i18n keys for English**

In `frontend/src/locales/lang/en/ui-automation.js`, inside the `testCase` block at the corresponding location:

```javascript
caseParameters: "Case Parameters",
caseParametersHint: "Case-level parameters override project parameters for all steps in this case",
stepParameters: "Step Parameters",
stepParametersHint: "Step-level parameters override case and project parameters for this step only",
paramName: "Parameter Name",
paramValue: "Parameter Value",
addParameter: "Add Parameter",
noParameters: "No parameter overrides",
parameterOverrides: "Parameter Overrides",
inheritFromCase: "Inherited from case",
inheritFromProject: "Inherited from project",
```

- [ ] **Step 3: Add case parameters editor section in TestCaseManager.vue**

In `TestCaseManager.vue`, add a collapsible section for case-level parameters. Place it in the right panel, between the test case header info and the steps list. Find the area after the case name/description/priority display and before `<!-- 步骤列表 -->`.

Add this template block:

```html
<!-- 用例参数覆盖 -->
<el-collapse v-model="activeSections" class="case-params-collapse">
  <el-collapse-item :title="t('uiAutomation.testCase.caseParameters')" name="caseParams">
    <div class="case-params-hint">
      {{ t('uiAutomation.testCase.caseParametersHint') }}
    </div>
    <div class="params-table">
      <div
        v-for="(_, index) in caseParamsList"
        :key="index"
        class="param-row"
      >
        <el-input
          v-model="caseParamsList[index].name"
          :placeholder="t('uiAutomation.testCase.paramName')"
          size="small"
          style="width: 180px"
        />
        <el-input
          v-model="caseParamsList[index].value"
          :placeholder="t('uiAutomation.testCase.paramValue')"
          size="small"
          style="flex: 1"
        />
        <el-button
          size="small"
          type="danger"
          :icon="Delete"
          circle
          @click="removeCaseParam(index)"
        />
      </div>
      <el-button
        size="small"
        type="primary"
        plain
        @click="addCaseParam"
      >
        <el-icon><Plus /></el-icon>
        {{ t('uiAutomation.testCase.addParameter') }}
      </el-button>
    </div>
  </el-collapse-item>
</el-collapse>
```

- [ ] **Step 4: Add reactive state and conversion helpers in `<script setup>`**

In the `<script setup>` section of `TestCaseManager.vue`:

```javascript
const activeSections = ref([]);

// Convert case_parameters object to editable list
const caseParamsList = ref([]);

const syncCaseParamsFromObject = (paramsObj) => {
  caseParamsList.value = Object.entries(paramsObj || {}).map(([name, value]) => ({ name, value }));
};

const syncCaseParamsToObject = () => {
  const obj = {};
  for (const p of caseParamsList.value) {
    if (p.name.trim()) {
      obj[p.name.trim()] = p.value;
    }
  }
  return obj;
};

const addCaseParam = () => {
  caseParamsList.value.push({ name: '', value: '' });
};

const removeCaseParam = (index) => {
  caseParamsList.value.splice(index, 1);
};
```

- [ ] **Step 5: Sync caseParamsList when selecting a test case**

Find `selectTestCase` function and add after setting `selectedTestCase.value`:

```javascript
syncCaseParamsFromObject(selectedTestCase.value.case_parameters);
```

- [ ] **Step 6: Include case_parameters in saveTestCase**

In the `saveTestCase` function (line 1313), merge `case_parameters` into `updateData`:

```javascript
const updateData = {
  ...selectedTestCase.value,
  case_parameters: syncCaseParamsToObject(),
  steps: currentSteps.value,
};
```

- [ ] **Step 7: Add step parameters editor in step expanded content**

In the step expanded content area (after the assert section, before the step description), add a small inline parameter editor for each step:

```html
<!-- 步骤参数覆盖 -->
<div class="step-param step-params-section">
  <label>{{ t('uiAutomation.testCase.stepParameters') }}</label>
  <div class="step-params-editor">
    <div
      v-for="(param, pIdx) in getStepParamsList(element)"
      :key="pIdx"
      class="param-row compact"
    >
      <el-input
        v-model="param.name"
        :placeholder="t('uiAutomation.testCase.paramName')"
        size="small"
        style="width: 140px"
        @change="syncStepParamsToObject(element)"
      />
      <el-input
        v-model="param.value"
        :placeholder="t('uiAutomation.testCase.paramValue')"
        size="small"
        style="flex: 1"
        @change="syncStepParamsToObject(element)"
      />
      <el-button
        size="small"
        type="danger"
        :icon="Delete"
        circle
        @click="removeStepParam(element, pIdx)"
      />
    </div>
    <el-button
      size="small"
      plain
      @click="addStepParam(element)"
    >
      <el-icon><Plus /></el-icon>
      {{ t('uiAutomation.testCase.addParameter') }}
    </el-button>
  </div>
</div>
```

- [ ] **Step 8: Add step parameter helpers in `<script setup>`**

```javascript
const getStepParamsList = (step) => {
  if (!step._stepParamsList) {
    step._stepParamsList = Object.entries(step.step_parameters || {}).map(
      ([name, value]) => ({ name, value })
    );
  }
  return step._stepParamsList;
};

const syncStepParamsToObject = (step) => {
  const obj = {};
  for (const p of (step._stepParamsList || [])) {
    if (p.name.trim()) {
      obj[p.name.trim()] = p.value;
    }
  }
  step.step_parameters = obj;
};

const addStepParam = (step) => {
  if (!step._stepParamsList) {
    step._stepParamsList = [];
  }
  step._stepParamsList.push({ name: '', value: '' });
};

const removeStepParam = (step, index) => {
  step._stepParamsList.splice(index, 1);
  syncStepParamsToObject(step);
};
```

- [ ] **Step 9: Initialize step._stepParamsList when loading steps**

Find where steps are loaded/set (when `selectTestCase` populates `currentSteps`). After setting steps, iterate and initialize:

```javascript
currentSteps.value.forEach(step => {
  step._stepParamsList = Object.entries(step.step_parameters || {}).map(
    ([name, value]) => ({ name, value })
  );
});
```

- [ ] **Step 10: Add CSS for parameter editors**

Add at the end of the `<style>` section:

```css
.case-params-collapse {
  margin-bottom: 15px;
}

.case-params-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-bottom: 8px;
}

.params-table {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.param-row.compact {
  gap: 6px;
}

.step-params-section {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--el-border-color-lighter);
}

.step-params-editor {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}
```

- [ ] **Step 11: Start dev server and verify in browser**

Start the frontend dev server. Navigate to a test case. Verify:
1. Case parameters collapse section appears and can add/remove key-value pairs
2. Expanding a step shows the step parameters section
3. Saving the test case persists both case_parameters and step_parameters
4. Re-loading the test case restores the parameter values

- [ ] **Step 12: Commit**

```bash
git add frontend/src/views/ui-automation/test-cases/TestCaseManager.vue frontend/src/locales/lang/zh-cn/ui-automation.js frontend/src/locales/lang/en/ui-automation.js
git commit -m "feat: add case and step parameter override editors in test case manager UI"
```

---

### Task 5: End-to-End Verification

**Files:**
- No new files

**Interfaces:**
- Consumes: Everything from Tasks 1-4

- [ ] **Step 1: Create a test element with parameterized locator**

In the element library, create an element with locator value: `//div[@data-id="{{item_id}}"]`

- [ ] **Step 2: Set up project parameter**

In project parameters, add: `item_id` = `default_value`

- [ ] **Step 3: Create test case A with case_parameters override**

Create a test case, set `case_parameters`: `{"item_id": "case_a_value"}`
Add a step using the parameterized element.

- [ ] **Step 4: Create test case B with step_parameters override**

Create another test case, set `case_parameters`: `{"item_id": "case_b_value"}`
Add a step using the same element, but set `step_parameters`: `{"item_id": "step_override_value"}`

- [ ] **Step 5: Verify resolution priority**

Run test case A — locator should resolve to `//div[@data-id="case_a_value"]`
Run test case B — locator should resolve to `//div[@data-id="step_override_value"]` (step wins over case)

- [ ] **Step 6: Verify backward compatibility**

Run an existing test case that has no case_parameters or step_parameters. It should resolve `{{paramName}}` from project parameters as before.
