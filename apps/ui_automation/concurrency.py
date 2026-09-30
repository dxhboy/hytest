"""
浏览器自动化执行的进程内并发限制器。

背景：views.py 里历史上大量执行入口是 `threading.Thread(target=xxx); thread.start()`，
没有任何并发上限——多少个请求进来就起多少个线程、多少个浏览器进程，没有队列、
没有排队等待，容易在并发请求下把服务器资源（内存/浏览器进程数）打满。

这里提供一个有界线程池，作为"还没有迁移到 Celery 任务队列"的执行入口的过渡方案：
- 已经迁移到 Celery 的入口（套件批量执行、AI 智能模式）见 tasks.py，
  真正具备跨进程的任务队列、排队、可独立扩容的 worker。
- 暂未迁移的入口（单用例调试执行、定时任务里的多用例执行）先用这个有界线程池，
  把"无限起线程"变成"最多 N 个并发 + 排队等待"，作为风险可控的过渡修复。
  后续应该把这些也迁移成 Celery task，然后可以整个删除本模块。

用法：
    from .concurrency import run_bounded

    # 原来：thread = threading.Thread(target=func); thread.start(); thread.join()
    run_bounded(func).result()

    # 原来：thread = threading.Thread(target=func, daemon=True); thread.start()（不等待）
    run_bounded(func)  # 不调用 .result()，即为"提交后不等待"
"""
import os
from concurrent.futures import ThreadPoolExecutor

# 同时允许运行的浏览器自动化任务数量，超出的请求会在线程池内部排队等待，
# 而不是无限制地起新线程/新浏览器进程。可以通过环境变量调整。
MAX_CONCURRENT_BROWSER_TASKS = int(os.environ.get('UI_AUTOMATION_MAX_CONCURRENT_BROWSERS', '4'))

_executor = ThreadPoolExecutor(
    max_workers=MAX_CONCURRENT_BROWSER_TASKS,
    thread_name_prefix='ui-automation-exec',
)


def run_bounded(func, *args, **kwargs):
    """
    把一个同步函数提交到有界线程池执行。

    返回 concurrent.futures.Future：
    - 调用方需要像原来 thread.join() 一样阻塞等待结果时，调用 .result(timeout=...)。
    - 调用方原来是"启动后不等待"（fire-and-forget）时，直接忽略返回值即可，
      任务会在池子里排队执行，不会无限占用线程/浏览器资源。
    """
    return _executor.submit(func, *args, **kwargs)
