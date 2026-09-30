"""
脚本生成器 — 将 TestCase/TestCaseStep 转换为 Playwright 或 Selenium Python 代码。

支持的框架和语言:
  - Playwright + Python
  - Selenium + Python
"""
import textwrap
from typing import Optional


def generate_script(test_case, steps, framework: str = 'playwright',
                    language: str = 'python') -> str:
    """
    根据测试用例和步骤生成自动化脚本代码。

    Args:
        test_case: TestCase 模型实例
        steps: TestCaseStep 查询集或列表，需 select_related('element__locator_strategy')
        framework: 'playwright' 或 'selenium'
        language: 'python'（目前仅支持 Python）

    Returns:
        生成的脚本代码字符串
    """
    if framework == 'selenium':
        return _generate_selenium_python(test_case, steps)
    return _generate_playwright_python(test_case, steps)


def _locator_to_playwright(strategy: str, value: str) -> str:
    """将定位策略转换为 Playwright Python 代码片段"""
    s = strategy.lower()
    escaped = value.replace('"', '\\"')
    if s == 'id':
        return f'page.locator("#{escaped}")'
    if s in ('css', 'css selector'):
        return f'page.locator("{escaped}")'
    if s == 'xpath':
        return f'page.locator("xpath={escaped}")'
    if s == 'text':
        return f'page.get_by_text("{escaped}")'
    if s == 'placeholder':
        return f'page.get_by_placeholder("{escaped}")'
    if s == 'label':
        return f'page.get_by_label("{escaped}")'
    if s == 'test-id':
        return f'page.get_by_test_id("{escaped}")'
    if s == 'name':
        return f'page.locator("[name=\\"{escaped}\\"]")'
    if s == 'role':
        return f'page.get_by_role("{escaped}")'
    if s == 'title':
        return f'page.get_by_title("{escaped}")'
    return f'page.locator("{escaped}")'


def _locator_to_selenium(strategy: str, value: str) -> str:
    """将定位策略转换为 Selenium Python 代码片段"""
    s = strategy.lower()
    escaped = value.replace('"', '\\"')
    if s == 'id':
        return f'driver.find_element(By.ID, "{escaped}")'
    if s in ('css', 'css selector'):
        return f'driver.find_element(By.CSS_SELECTOR, "{escaped}")'
    if s == 'xpath':
        return f'driver.find_element(By.XPATH, "{escaped}")'
    if s == 'text':
        return f'driver.find_element(By.XPATH, "//*[contains(text(), \\"{escaped}\\")]")'
    if s == 'name':
        return f'driver.find_element(By.NAME, "{escaped}")'
    if s == 'placeholder':
        return f'driver.find_element(By.CSS_SELECTOR, "[placeholder=\\"{escaped}\\"]")'
    if s == 'label':
        return f'driver.find_element(By.XPATH, "//label[contains(text(), \\"{escaped}\\")]/following::input[1]")'
    if s == 'test-id':
        return f'driver.find_element(By.CSS_SELECTOR, "[data-testid=\\"{escaped}\\"]")'
    return f'driver.find_element(By.CSS_SELECTOR, "{escaped}")'


def _get_element_locator(step) -> tuple[Optional[str], Optional[str], str]:
    """从步骤中提取元素定位信息，返回 (strategy, value, element_name)"""
    elem = step.element
    if not elem:
        return None, None, ''
    strategy = elem.locator_strategy.name if elem.locator_strategy else 'css'
    return strategy, elem.locator_value, elem.name or ''


def _step_comment(step, element_name: str) -> str:
    """为步骤生成注释"""
    desc = step.description or ''
    action = step.get_action_type_display() if hasattr(step, 'get_action_type_display') else step.action_type
    if element_name:
        return f'# 步骤{step.step_number}: {action} - {element_name}'
    if desc:
        return f'# 步骤{step.step_number}: {action} - {desc}'
    return f'# 步骤{step.step_number}: {action}'


# ---- Playwright Python ----

def _generate_playwright_python(test_case, steps) -> str:
    lines = [
        f'"""',
        f'自动生成的 Playwright 测试脚本',
        f'用例名称: {test_case.name}',
        f'"""',
        f'import asyncio',
        f'from playwright.async_api import async_playwright',
        f'',
        f'',
        f'async def run():',
        f'    async with async_playwright() as p:',
        f'        browser = await p.chromium.launch(headless=False)',
        f'        context = await browser.new_context(',
        f'            viewport={{"width": 1920, "height": 1080}}',
        f'        )',
        f'        page = await context.new_page()',
        f'',
    ]

    navigate_url = _find_navigate_url(test_case, steps)
    if navigate_url:
        lines.append(f'        await page.goto("{navigate_url}")')
        lines.append(f'')

    for step in steps:
        code = _playwright_step_code(step)
        if code:
            lines.append(code)
            lines.append(f'')

    lines.extend([
        f'        # 测试完成，关闭浏览器',
        f'        await context.close()',
        f'        await browser.close()',
        f'',
        f'',
        f'if __name__ == "__main__":',
        f'    asyncio.run(run())',
        f'',
    ])

    return '\n'.join(lines)


def _playwright_step_code(step) -> Optional[str]:
    """生成单步的 Playwright 代码"""
    action = step.action_type
    strategy, value, elem_name = _get_element_locator(step)
    comment = _step_comment(step, elem_name)
    indent = '        '

    if action == 'click':
        if not strategy:
            return None
        loc = _locator_to_playwright(strategy, value)
        return f'{indent}{comment}\n{indent}await {loc}.click()'

    if action == 'fill':
        if not strategy:
            return None
        loc = _locator_to_playwright(strategy, value)
        input_val = (step.input_value or '').replace('"', '\\"')
        return f'{indent}{comment}\n{indent}await {loc}.fill("{input_val}")'

    if action == 'hover':
        if not strategy:
            return None
        loc = _locator_to_playwright(strategy, value)
        return f'{indent}{comment}\n{indent}await {loc}.hover()'

    if action == 'scroll':
        return f'{indent}{comment}\n{indent}await page.mouse.wheel(0, 300)'

    if action == 'wait':
        wait_sec = (step.wait_time or 1000) / 1000
        return f'{indent}{comment}\n{indent}await page.wait_for_timeout({int(wait_sec * 1000)})'

    if action == 'waitFor':
        if not strategy:
            return None
        loc = _locator_to_playwright(strategy, value)
        timeout = step.wait_time or 5000
        return f'{indent}{comment}\n{indent}await {loc}.wait_for(timeout={timeout})'

    if action == 'screenshot':
        return f'{indent}{comment}\n{indent}await page.screenshot(path="screenshot_{step.step_number}.png")'

    if action == 'getText':
        if not strategy:
            return None
        loc = _locator_to_playwright(strategy, value)
        return f'{indent}{comment}\n{indent}text_{step.step_number} = await {loc}.inner_text()'

    if action == 'assert':
        return _playwright_assert_code(step, strategy, value, elem_name, indent)

    if action == 'switchTab':
        input_val = step.input_value or ''
        if input_val.isdigit():
            return f'{indent}{comment}\n{indent}page = context.pages[{input_val}]\n{indent}await page.bring_to_front()'
        return f'{indent}{comment}\n{indent}page = context.pages[-1]\n{indent}await page.bring_to_front()'

    return None


def _playwright_assert_code(step, strategy, value, elem_name, indent) -> Optional[str]:
    """生成 Playwright 断言代码"""
    comment = _step_comment(step, elem_name)
    assert_type = step.assert_type
    assert_val = (step.assert_value or '').replace('"', '\\"')

    if not strategy:
        return None
    loc = _locator_to_playwright(strategy, value)

    if assert_type == 'textContains':
        return f'{indent}{comment}\n{indent}from playwright.async_api import expect\n{indent}await expect({loc}).to_contain_text("{assert_val}")'
    if assert_type == 'textEquals':
        return f'{indent}{comment}\n{indent}from playwright.async_api import expect\n{indent}await expect({loc}).to_have_text("{assert_val}")'
    if assert_type == 'isVisible':
        return f'{indent}{comment}\n{indent}from playwright.async_api import expect\n{indent}await expect({loc}).to_be_visible()'
    if assert_type == 'exists':
        return f'{indent}{comment}\n{indent}assert await {loc}.count() > 0'
    if assert_type == 'hasAttribute':
        parts = assert_val.split('=', 1)
        if len(parts) == 2:
            return f'{indent}{comment}\n{indent}from playwright.async_api import expect\n{indent}await expect({loc}).to_have_attribute("{parts[0]}", "{parts[1]}")'

    return None


# ---- Selenium Python ----

def _generate_selenium_python(test_case, steps) -> str:
    lines = [
        f'"""',
        f'自动生成的 Selenium 测试脚本',
        f'用例名称: {test_case.name}',
        f'"""',
        f'import time',
        f'from selenium import webdriver',
        f'from selenium.webdriver.common.by import By',
        f'from selenium.webdriver.common.keys import Keys',
        f'from selenium.webdriver.support.ui import WebDriverWait',
        f'from selenium.webdriver.support import expected_conditions as EC',
        f'',
        f'',
        f'def run():',
        f'    options = webdriver.ChromeOptions()',
        f'    driver = webdriver.Chrome(options=options)',
        f'    driver.set_window_size(1920, 1080)',
        f'    wait = WebDriverWait(driver, 10)',
        f'',
    ]

    navigate_url = _find_navigate_url(test_case, steps)
    if navigate_url:
        lines.append(f'    driver.get("{navigate_url}")')
        lines.append(f'')

    for step in steps:
        code = _selenium_step_code(step)
        if code:
            lines.append(code)
            lines.append(f'')

    lines.extend([
        f'    # 测试完成，关闭浏览器',
        f'    driver.quit()',
        f'',
        f'',
        f'if __name__ == "__main__":',
        f'    run()',
        f'',
    ])

    return '\n'.join(lines)


def _selenium_step_code(step) -> Optional[str]:
    """生成单步的 Selenium 代码"""
    action = step.action_type
    strategy, value, elem_name = _get_element_locator(step)
    comment = _step_comment(step, elem_name)
    indent = '    '

    if action == 'click':
        if not strategy:
            return None
        loc = _locator_to_selenium(strategy, value)
        return f'{indent}{comment}\n{indent}{loc}.click()'

    if action == 'fill':
        if not strategy:
            return None
        loc = _locator_to_selenium(strategy, value)
        input_val = (step.input_value or '').replace('"', '\\"')
        return f'{indent}{comment}\n{indent}element = {loc}\n{indent}element.clear()\n{indent}element.send_keys("{input_val}")'

    if action == 'hover':
        if not strategy:
            return None
        loc = _locator_to_selenium(strategy, value)
        return (
            f'{indent}{comment}\n'
            f'{indent}from selenium.webdriver.common.action_chains import ActionChains\n'
            f'{indent}ActionChains(driver).move_to_element({loc}).perform()'
        )

    if action == 'scroll':
        return f'{indent}{comment}\n{indent}driver.execute_script("window.scrollBy(0, 300)")'

    if action == 'wait':
        wait_sec = (step.wait_time or 1000) / 1000
        return f'{indent}{comment}\n{indent}time.sleep({wait_sec})'

    if action == 'waitFor':
        if not strategy:
            return None
        by, val = _selenium_by_args(strategy, value)
        timeout = (step.wait_time or 5000) / 1000
        return f'{indent}{comment}\n{indent}wait.until(EC.presence_of_element_located(({by}, "{val}")))'

    if action == 'screenshot':
        return f'{indent}{comment}\n{indent}driver.save_screenshot("screenshot_{step.step_number}.png")'

    if action == 'getText':
        if not strategy:
            return None
        loc = _locator_to_selenium(strategy, value)
        return f'{indent}{comment}\n{indent}text_{step.step_number} = {loc}.text'

    if action == 'assert':
        return _selenium_assert_code(step, strategy, value, elem_name, indent)

    if action == 'switchTab':
        input_val = step.input_value or ''
        if input_val.isdigit():
            return f'{indent}{comment}\n{indent}driver.switch_to.window(driver.window_handles[{input_val}])'
        return f'{indent}{comment}\n{indent}driver.switch_to.window(driver.window_handles[-1])'

    return None


def _selenium_by_args(strategy: str, value: str) -> tuple[str, str]:
    """将定位策略转为 Selenium By.XXX 常量名和值"""
    s = strategy.lower()
    escaped = value.replace('"', '\\"')
    if s == 'id':
        return 'By.ID', escaped
    if s in ('css', 'css selector'):
        return 'By.CSS_SELECTOR', escaped
    if s == 'xpath':
        return 'By.XPATH', escaped
    if s == 'name':
        return 'By.NAME', escaped
    if s == 'text':
        return 'By.XPATH', f'//*[contains(text(), "{escaped}")]'
    return 'By.CSS_SELECTOR', escaped


def _selenium_assert_code(step, strategy, value, elem_name, indent) -> Optional[str]:
    """生成 Selenium 断言代码"""
    comment = _step_comment(step, elem_name)
    assert_type = step.assert_type
    assert_val = (step.assert_value or '').replace('"', '\\"')

    if not strategy:
        return None
    loc = _locator_to_selenium(strategy, value)

    if assert_type == 'textContains':
        return f'{indent}{comment}\n{indent}assert "{assert_val}" in {loc}.text'
    if assert_type == 'textEquals':
        return f'{indent}{comment}\n{indent}assert {loc}.text == "{assert_val}"'
    if assert_type == 'isVisible':
        return f'{indent}{comment}\n{indent}assert {loc}.is_displayed()'
    if assert_type == 'exists':
        by, val = _selenium_by_args(strategy, value)
        return f'{indent}{comment}\n{indent}assert len(driver.find_elements({by}, "{val}")) > 0'
    if assert_type == 'hasAttribute':
        parts = assert_val.split('=', 1)
        if len(parts) == 2:
            return f'{indent}{comment}\n{indent}assert {loc}.get_attribute("{parts[0]}") == "{parts[1]}"'

    return None


def _find_navigate_url(test_case, steps) -> str:
    """从用例描述或步骤中提取目标 URL"""
    desc = test_case.description or ''
    if 'http' in desc:
        import re
        match = re.search(r'https?://\S+', desc)
        if match:
            return match.group(0)
    return ''
