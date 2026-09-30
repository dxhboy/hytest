"""
AI 智能模式执行记录（AIExecutionRecord）的收尾处理逻辑。

背景：这两个函数以前分别在 AICaseViewSet 和 AIExecutionRecordViewSet 里各写了
一份逐字节相同的拷贝（`_process_gif_recording` / `_auto_mark_completed_tasks`），
且都不访问 `self.request`/`self.queryset` 等任何 ViewSet 状态，只依赖传入的
`execution_record`/`history` 参数——本质上是两个被误放进 ViewSet 里的纯函数。

apps/ui_automation/tasks.py 里的 Celery 任务为了调用它们，一度专门"裸实例化"
一个没有 request 上下文的 ViewSet 对象（`AICaseViewSet()`）只为借用这两个方法，
这个写法容易让人误以为这两个方法依赖 DRF 的请求上下文，其实不需要。

现在把它们提出来做成模块级函数，ViewSet 和 Celery 任务都直接 import 调用。
"""
import logging
import os
import shutil
from datetime import datetime

from django.conf import settings

logger = logging.getLogger(__name__)


def process_gif_recording(execution_record, history):
    """
    处理 AI 智能模式的 GIF 录制文件。

    在执行完成后查找 browser-use 生成的 GIF 文件（固定文件名 agent_history.gif，
    生成在进程当前工作目录下），移动到 media/ai_recording/ 目录并按用例名+时间戳
    重命名，把相对路径写回 execution_record.gif_path（调用方负责最终 save()）。

    注意：固定文件名意味着并发执行多个 AI 任务时，多个任务会争抢同一个源文件
    （见架构评审记录），这里暂未修复，只是把原来重复的两份实现合并成一份。
    """
    try:
        # browser-use 默认生成的GIF文件名（固定为agent_history.gif）
        default_gif_path = os.path.join(os.getcwd(), 'agent_history.gif')

        # 如果找到GIF文件，移动到media/ai_recording目录并重命名
        if os.path.exists(default_gif_path):
            # 创建录制文件目录
            gif_dir = os.path.join(settings.MEDIA_ROOT, 'ai_recording')
            os.makedirs(gif_dir, exist_ok=True)

            # 生成新的文件名：用例名称+年月日时分秒
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            # 清理用例名称中的非法字符
            safe_case_name = "".join(
                [c if c.isalnum() or c in (' ', '_', '-') else '_' for c in execution_record.case_name])
            new_gif_filename = f"{safe_case_name}_{timestamp}.gif"
            new_gif_path = os.path.join(gif_dir, new_gif_filename)

            # 移动并重命名文件
            shutil.move(default_gif_path, new_gif_path)

            # 保存相对路径到数据库（使用正斜杠，确保跨平台兼容）
            relative_path = f'media/ai_recording/{new_gif_filename}'
            execution_record.gif_path = relative_path

            logger.info(f"✅ GIF recording saved to: {relative_path}")
        else:
            logger.warning(f"⚠️ GIF file not found at: {default_gif_path}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to process GIF recording: {e}")


def auto_mark_completed_tasks(execution_record):
    """
    自动标记已完成的任务。

    通过分析执行历史和当前任务状态，自动标记那些已经执行但未被标记完成的任务
    （目前的规则很简单：整体执行成功时，把所有还是 pending 的任务标记成
    completed；更细粒度的"部分完成"识别还没有实现，见下面的 TODO）。
    """
    try:
        # 记录初始状态
        initial_completed = 0
        initial_pending = 0
        if execution_record.planned_tasks:
            initial_completed = len([t for t in execution_record.planned_tasks if t.get('status') == 'completed'])
            initial_pending = len([t for t in execution_record.planned_tasks if t.get('status') == 'pending'])
            logger.info(f"📊 Before auto-mark: {initial_completed} completed, {initial_pending} pending tasks")

        # 如果执行成功，标记所有任务为完成
        if execution_record.status == 'passed' and execution_record.planned_tasks:
            auto_marked_count = 0
            for task in execution_record.planned_tasks:
                # 只对标记为pending的任务进行处理
                if task.get('status') == 'pending':
                    task['status'] = 'completed'
                    auto_marked_count += 1
                    logger.info(f"🔒 Auto-marked task {task['id']} as completed")

            if auto_marked_count > 0:
                logger.info(f"✨ Auto-marked {auto_marked_count} tasks as completed")
            else:
                logger.info("📋 No pending tasks needed auto-marking")

        # TODO: 可以添加更智能的分析逻辑来识别部分完成的任务

    except Exception as e:
        logger.warning(f"⚠️ Failed to auto-mark completed tasks: {e}")


def extract_step_info(s, step_index):
    """提取步骤信息的辅助函数，确保返回可读的步骤描述"""
    step_info = {'step': step_index}

    # 尝试多种方式提取可读信息
    if hasattr(s, 'action'):
        # 如果有action属性
        action_data = s.action
        if isinstance(action_data, str):
            step_info['action'] = action_data
        elif hasattr(action_data, '__dict__'):
            # 如果是对象，提取关键属性
            attrs = {}
            for key in ['type', 'description', 'goal', 'coordinate', 'text', 'output', 'result']:
                if hasattr(action_data, key):
                    value = getattr(action_data, key)
                    if isinstance(value, str):
                        attrs[key] = value
                    elif callable(value):
                        attrs[key] = getattr(value, '__name__', str(value))
                    else:
                        attrs[key] = str(value)
            if attrs:
                step_info['action'] = attrs
        else:
            step_info['action'] = str(action_data)
    elif hasattr(s, 'model_output'):
        # 如果有model_output属性
        output_data = s.model_output
        if isinstance(output_data, str):
            step_info['action'] = output_data
        elif hasattr(output_data, '__dict__'):
            # 提取model_output的关键信息
            attrs = {'type': 'model_output'}
            for key in ['action', 'description', 'goal', 'coordinate', 'text']:
                if hasattr(output_data, key):
                    value = getattr(output_data, key)
                    attrs[key] = str(value) if value else None
            step_info['action'] = attrs
        else:
            step_info['action'] = str(output_data)
    elif hasattr(s, '__dict__'):
        # 通用的对象提取
        attrs = {}
        for key in dir(s):
            if not key.startswith('_'):
                try:
                    value = getattr(s, key)
                    if not callable(value):
                        attrs[key] = str(value)
                except:
                    pass
        if attrs:
            step_info['action'] = attrs
    else:
        # 最后回退，但检查是否是函数对象
        if callable(s):
            step_info['action'] = f"<Action: {getattr(s, '__name__', 'unknown action')}>"
        else:
            step_info['action'] = str(s)

    return step_info
