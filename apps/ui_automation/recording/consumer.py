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
