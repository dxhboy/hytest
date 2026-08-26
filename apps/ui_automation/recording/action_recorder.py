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
