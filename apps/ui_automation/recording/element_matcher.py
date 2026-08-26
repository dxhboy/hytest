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
        """
        第1层：精确匹配。

        先通过索引快速找出"至少有一个定位器命中"的候选元素，再逐个校验：
        只要该候选元素与本次录制的定位器在任一相同策略（如 css、test-id）上
        取值不一致，就说明定位器发生了变化，不能算精确匹配——要交给第2层
        模糊匹配去判断是否为"同一元素但定位器变了"。
        只有所有重叠策略的取值都完全一致时，才认为是真正的精确匹配。
        """
        candidate_ids: set = set()
        for loc in locators:
            for pp in (page_path, ''):
                elem = self._locator_index.get((pp, loc['strategy'], loc['value']))
                if elem:
                    candidate_ids.add(elem.id)

        if not candidate_ids:
            return None

        for elem in self._elements:
            if elem.id in candidate_ids and self._is_fully_consistent(elem, locators):
                return elem
        return None

    def _is_fully_consistent(self, elem: Element, locators: list[dict]) -> bool:
        """判断候选元素的已有定位器与新录制的定位器在所有重叠策略上取值是否一致"""
        elem_map = {loc['strategy']: loc['value'] for loc in _get_all_locators(elem)}
        incoming_map = {loc['strategy']: loc['value'] for loc in locators}
        common_strategies = set(elem_map) & set(incoming_map)
        if not common_strategies:
            return False
        return all(elem_map[s] == incoming_map[s] for s in common_strategies)

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
