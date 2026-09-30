"""uvicorn 自定义事件循环：`uvicorn backend.asgi:application --loop backend.event_loop:loop_factory`

uvicorn 在 Windows 上只要开启 --reload 或 workers>1，就会改用 SelectorEventLoop；
而脚本录制（apps/ui_automation/recording/consumer.py）在 ASGI 进程的事件循环里直接启动
Playwright 浏览器，需要创建子进程，SelectorEventLoop 不支持，会抛 NotImplementedError。
这里在 Windows 上固定使用 ProactorEventLoop，其他平台保持默认。
"""
import asyncio
import sys


def loop_factory():
    if sys.platform == 'win32':
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()
