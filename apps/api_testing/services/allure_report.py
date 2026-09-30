"""测试执行的 Allure 报告生成（结果文件、报告目录、摘要页）

供 TestExecutionViewSet.generate_allure_report 与 tasks._generate_allure_report 共用。
"""
import json
import os
import time
import logging

from django.conf import settings

from ..models import RequestHistory
from .masking import _mask_sensitive_data

# 获取logger实例
logger = logging.getLogger(__name__)


def generate_allure_report_with_fallback(execution, results_dir, report_output_dir):
    """生成Allure报告，带降级策略"""
    import subprocess
    import shutil
    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    allure_executable = 'allure.bat' if os.name == 'nt' else 'allure'
    allure_cmd = str(base_dir / 'allure' / 'bin' / allure_executable)

    if not os.path.exists(allure_cmd):
        possible_paths = [
            base_dir / 'allure' / 'bin' / allure_executable,
            Path('/usr/local/bin/allure'),
            Path('/usr/bin/allure'),
        ]
        for path in possible_paths:
            if path.exists():
                allure_cmd = str(path)
                break
        else:
            allure_cmd = None

    os.makedirs(results_dir, exist_ok=True)

    if allure_cmd:
        try:
            if os.path.exists(report_output_dir):
                shutil.rmtree(report_output_dir)

            subprocess.run([
                allure_cmd, 'generate',
                results_dir,
                '--clean',
                '--output', report_output_dir
            ], check=True, capture_output=True, text=True, timeout=60)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.warning(f"Allure命令失败: {str(e)}，使用降级方案")
            _copy_static_allure_files(report_output_dir)

    _ensure_report_exists(execution, report_output_dir)


def _copy_static_allure_files(report_output_dir):
    """复制静态Allure文件"""
    import shutil
    static_dir = os.path.join(settings.MEDIA_ROOT, 'allure-static')
    if os.path.exists(static_dir):
        for item in os.listdir(static_dir):
            source = os.path.join(static_dir, item)
            destination = os.path.join(report_output_dir, item)
            if os.path.isdir(source):
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)


def _ensure_report_exists(execution, report_output_dir):
    """确保报告文件存在"""
    if not os.path.exists(os.path.join(report_output_dir, 'index.html')):
        fallback_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>测试报告 - {execution.test_suite.name}</title>
</head>
<body>
    <h1>测试报告</h1>
    <p>测试套件: {execution.test_suite.name}</p>
    <p>状态: {execution.get_status_display()}</p>
    <p>总请求数: {execution.total_requests}</p>
    <p>通过: {execution.passed_requests}</p>
    <p>失败: {execution.failed_requests}</p>
</body>
</html>
"""
        with open(os.path.join(report_output_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(fallback_html)


def generate_summary_html(execution, report_output_dir):
    """生成摘要HTML - 仪表盘设计"""
    import math

    project_name = execution.test_suite.project.name
    suite_name = execution.test_suite.name
    total = execution.total_requests or 0
    passed = execution.passed_requests or 0
    failed = execution.failed_requests or 0
    skipped = max(0, total - passed - failed)
    pass_rate = round(passed / total * 100, 1) if total > 0 else 0.0
    status_is_ok = execution.status == "COMPLETED"
    status_text = execution.get_status_display()
    exec_time = execution.created_at.strftime('%Y-%m-%d %H:%M:%S') if execution.created_at else 'N/A'

    duration_text = 'N/A'
    if execution.start_time and execution.end_time:
        secs = (execution.end_time - execution.start_time).total_seconds()
        duration_text = f"{secs:.1f} 秒" if secs < 60 else f"{int(secs // 60)} 分 {int(secs % 60)} 秒"

    # SVG donut chart 参数（半径 54, 圆心 60,60）
    r = 60
    circ = round(2 * math.pi * r, 2)
    pass_arc = round(pass_rate / 100 * circ, 2)
    fail_arc = round(circ - pass_arc, 2)

    index_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name} - 接口测试报告</title>
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #1a1a2e; }}

        /* ── Header ── */
        .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #7c3aed 100%); color: #fff; padding: 0; }}
        .header-inner {{ max-width: 1280px; margin: 0 auto; padding: 2rem 2rem 1.8rem; display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; }}
        .header-left h1 {{ font-size: 1.75rem; font-weight: 700; letter-spacing: -0.5px; }}
        .header-left .subtitle {{ margin-top: 0.4rem; opacity: 0.85; font-size: 0.95rem; }}
        .header-left .subtitle span {{ margin-right: 1.2rem; }}
        .header-right {{ display: flex; align-items: center; gap: 0.75rem; flex-shrink: 0; }}
        .badge {{ display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.45rem 1rem; border-radius: 999px; font-weight: 600; font-size: 0.85rem; }}
        .badge-ok  {{ background: #22c55e; color: #fff; }}
        .badge-err {{ background: #ef4444; color: #fff; }}
        .btn-allure {{ display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.5rem 1.1rem; background: rgba(255,255,255,0.15); border: 1.5px solid rgba(255,255,255,0.35); border-radius: 6px; color: #fff; text-decoration: none; font-size: 0.88rem; font-weight: 600; transition: background 0.2s; }}
        .btn-allure:hover {{ background: rgba(255,255,255,0.28); text-decoration: none; }}

        /* ── Main ── */
        .main {{ max-width: 1280px; margin: 0 auto; padding: 2rem; }}

        /* ── Metric cards ── */
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
        .metric-card {{ background: #fff; border-radius: 12px; padding: 1.4rem 1.6rem; box-shadow: 0 1px 4px rgba(0,0,0,0.07); border-top: 4px solid transparent; }}
        .metric-card.c-total  {{ border-top-color: #6366f1; }}
        .metric-card.c-passed {{ border-top-color: #22c55e; }}
        .metric-card.c-failed {{ border-top-color: #ef4444; }}
        .metric-card.c-rate   {{ border-top-color: #f59e0b; }}
        .metric-card.c-time   {{ border-top-color: #06b6d4; }}
        .metric-card.c-dur    {{ border-top-color: #8b5cf6; }}
        .metric-val {{ font-size: 2.1rem; font-weight: 800; line-height: 1; }}
        .metric-val.v-total  {{ color: #6366f1; }}
        .metric-val.v-passed {{ color: #22c55e; }}
        .metric-val.v-failed {{ color: #ef4444; }}
        .metric-val.v-rate   {{ color: #f59e0b; }}
        .metric-val.v-time   {{ color: #06b6d4; font-size: 1.25rem; }}
        .metric-val.v-dur    {{ color: #8b5cf6; font-size: 1.35rem; }}
        .metric-label {{ margin-top: 0.4rem; font-size: 0.82rem; color: #6b7280; font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }}

        /* ── Dashboard row ── */
        .dashboard {{ display: grid; grid-template-columns: 280px 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }}
        @media (max-width: 768px) {{ .dashboard {{ grid-template-columns: 1fr; }} }}

        .chart-card {{ background: #fff; border-radius: 12px; padding: 1.5rem; box-shadow: 0 1px 4px rgba(0,0,0,0.07); display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        .chart-card h3 {{ font-size: 0.95rem; color: #374151; font-weight: 600; margin-bottom: 1rem; align-self: flex-start; }}
        .donut-wrap {{ position: relative; width: 160px; height: 160px; }}
        .donut-center {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
        .donut-pct {{ font-size: 1.9rem; font-weight: 800; color: #1a1a2e; line-height: 1; }}
        .donut-sub {{ font-size: 0.72rem; color: #6b7280; margin-top: 0.2rem; }}
        .legend {{ display: flex; gap: 1rem; margin-top: 1rem; flex-wrap: wrap; justify-content: center; }}
        .legend-item {{ display: flex; align-items: center; gap: 0.35rem; font-size: 0.82rem; color: #374151; }}
        .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}

        .bar-card {{ background: #fff; border-radius: 12px; padding: 1.5rem; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }}
        .bar-card h3 {{ font-size: 0.95rem; color: #374151; font-weight: 600; margin-bottom: 1.2rem; }}
        .bar-row {{ display: flex; align-items: center; gap: 0.8rem; margin-bottom: 0.9rem; }}
        .bar-label {{ width: 3.5rem; font-size: 0.82rem; color: #6b7280; text-align: right; flex-shrink: 0; }}
        .bar-track {{ flex: 1; height: 22px; background: #f3f4f6; border-radius: 6px; overflow: hidden; }}
        .bar-fill {{ height: 100%; border-radius: 6px; display: flex; align-items: center; padding-left: 8px; color: #fff; font-size: 0.78rem; font-weight: 700; min-width: 2rem; transition: width 0.6s ease; }}
        .bar-fill.b-pass {{ background: linear-gradient(90deg, #22c55e, #16a34a); }}
        .bar-fill.b-fail {{ background: linear-gradient(90deg, #ef4444, #dc2626); }}
        .bar-fill.b-skip {{ background: linear-gradient(90deg, #9ca3af, #6b7280); }}
        .bar-count {{ width: 2rem; font-size: 0.82rem; font-weight: 700; color: #374151; flex-shrink: 0; }}

        /* ── Test results table ── */
        .results-card {{ background: #fff; border-radius: 12px; padding: 1.5rem; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }}
        .results-card h3 {{ font-size: 0.95rem; color: #374151; font-weight: 600; margin-bottom: 1rem; }}
        .results-table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
        .results-table th {{ background: #f9fafb; padding: 0.7rem 0.8rem; text-align: left; font-size: 0.78rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid #e5e7eb; }}
        .results-table td {{ padding: 0.75rem 0.8rem; border-bottom: 1px solid #f3f4f6; vertical-align: top; }}
        .results-table tr:last-child td {{ border-bottom: none; }}
        .results-table tr:hover td {{ background: #fafafa; }}
        .tag-method {{ display: inline-block; padding: 0.18rem 0.55rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; color: #fff; }}
        .m-get    {{ background: #3b82f6; }}
        .m-post   {{ background: #22c55e; }}
        .m-put    {{ background: #f59e0b; }}
        .m-patch  {{ background: #8b5cf6; }}
        .m-delete {{ background: #ef4444; }}
        .m-other  {{ background: #6b7280; }}
        .tag-status {{ display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.2rem 0.65rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }}
        .s-pass {{ background: #dcfce7; color: #15803d; }}
        .s-fail {{ background: #fee2e2; color: #b91c1c; }}
        .cell-url {{ color: #6b7280; word-break: break-all; max-width: 340px; }}
        .assertions-list {{ margin-top: 6px; padding-left: 0; list-style: none; }}
        .assertions-list li {{ font-size: 0.8rem; padding: 3px 0; display: flex; align-items: flex-start; gap: 0.4rem; }}
        .a-ok  {{ color: #15803d; }}
        .a-err {{ color: #b91c1c; }}
        .err-box {{ margin-top: 4px; padding: 0.4rem 0.6rem; background: #fff1f2; border-radius: 4px; font-size: 0.8rem; color: #b91c1c; }}

        /* ── Footer ── */
        .footer {{ text-align: center; padding: 1.5rem; color: #9ca3af; font-size: 0.82rem; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-inner">
            <div class="header-left">
                <h1>{project_name} - 接口测试报告</h1>
                <div class="subtitle">
                    <span>测试套件：{suite_name}</span>
                    <span>执行时间：{exec_time}</span>
                </div>
            </div>
            <div class="header-right">
                <span class="badge {'badge-ok' if status_is_ok else 'badge-err'}">
                    {'✓' if status_is_ok else '✗'} {status_text}
                </span>
                <a href="index.html" target="_blank" class="btn-allure">&#128196; 查看 Allure 详情报告</a>
            </div>
        </div>
    </div>

    <div class="main">
        <!-- 指标卡片 -->
        <div class="metrics">
            <div class="metric-card c-total">
                <div class="metric-val v-total">{total}</div>
                <div class="metric-label">总用例数</div>
            </div>
            <div class="metric-card c-passed">
                <div class="metric-val v-passed">{passed}</div>
                <div class="metric-label">通过</div>
            </div>
            <div class="metric-card c-failed">
                <div class="metric-val v-failed">{failed}</div>
                <div class="metric-label">失败</div>
            </div>
            <div class="metric-card c-rate">
                <div class="metric-val v-rate">{pass_rate}%</div>
                <div class="metric-label">通过率</div>
            </div>
            <div class="metric-card c-time">
                <div class="metric-val v-time">{exec_time}</div>
                <div class="metric-label">执行时间</div>
            </div>
            <div class="metric-card c-dur">
                <div class="metric-val v-dur">{duration_text}</div>
                <div class="metric-label">执行耗时</div>
            </div>
        </div>

        <!-- 仪表盘 -->
        <div class="dashboard">
            <!-- 甜甜圈图 -->
            <div class="chart-card">
                <h3>执行结果分布</h3>
                <div class="donut-wrap">
                    <svg viewBox="0 0 120 120" width="160" height="160">
                        <!-- 背景圆 -->
                        <circle cx="60" cy="60" r="{r}" fill="none" stroke="#f3f4f6" stroke-width="16"/>
                        <!-- 失败弧（先画，在通过弧下面） -->
                        <circle cx="60" cy="60" r="{r}" fill="none" stroke="#ef4444" stroke-width="16"
                            stroke-dasharray="{fail_arc} {circ}"
                            stroke-dashoffset="-{pass_arc}"
                            transform="rotate(-90 60 60)"/>
                        <!-- 通过弧 -->
                        <circle cx="60" cy="60" r="{r}" fill="none" stroke="#22c55e" stroke-width="16"
                            stroke-dasharray="{pass_arc} {circ}"
                            stroke-dashoffset="0"
                            transform="rotate(-90 60 60)"/>
                    </svg>
                    <div class="donut-center">
                        <span class="donut-pct">{pass_rate}%</span>
                        <span class="donut-sub">通过率</span>
                    </div>
                </div>
                <div class="legend">
                    <div class="legend-item"><div class="legend-dot" style="background:#22c55e"></div>通过 {passed}</div>
                    <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div>失败 {failed}</div>
                    {"<div class='legend-item'><div class='legend-dot' style='background:#9ca3af'></div>跳过 " + str(skipped) + "</div>" if skipped > 0 else ""}
                </div>
            </div>

            <!-- 水平进度条 -->
            <div class="bar-card">
                <h3>各类结果统计</h3>
                <div class="bar-row">
                    <span class="bar-label">通过</span>
                    <div class="bar-track">
                        <div class="bar-fill b-pass" style="width:{round(passed/total*100) if total else 0}%">{passed}</div>
                    </div>
                    <span class="bar-count">{passed}</span>
                </div>
                <div class="bar-row">
                    <span class="bar-label">失败</span>
                    <div class="bar-track">
                        <div class="bar-fill b-fail" style="width:{round(failed/total*100) if total else 0}%">{failed}</div>
                    </div>
                    <span class="bar-count">{failed}</span>
                </div>
                {"<div class='bar-row'><span class='bar-label'>跳过</span><div class='bar-track'><div class='bar-fill b-skip' style='width:" + str(round(skipped/total*100) if total else 0) + "%'>" + str(skipped) + "</div></div><span class='bar-count'>" + str(skipped) + "</span></div>" if skipped > 0 else ""}
                <div style="margin-top:1.5rem; padding:1rem; background:#f9fafb; border-radius:8px;">
                    <table style="width:100%; font-size:0.85rem; border-collapse:collapse;">
                        <tr>
                            <td style="color:#6b7280; padding:4px 0;">总用例数</td>
                            <td style="font-weight:700; text-align:right;">{total}</td>
                            <td style="color:#6b7280; padding:4px 0 4px 2rem;">通过率</td>
                            <td style="font-weight:700; text-align:right; color:#f59e0b;">{pass_rate}%</td>
                        </tr>
                        <tr>
                            <td style="color:#6b7280; padding:4px 0;">执行状态</td>
                            <td style="font-weight:700; text-align:right; color:{'#22c55e' if status_is_ok else '#ef4444'};">{status_text}</td>
                            <td style="color:#6b7280; padding:4px 0 4px 2rem;">执行耗时</td>
                            <td style="font-weight:700; text-align:right;">{duration_text}</td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>

        <!-- 测试结果明细 -->
        <div class="results-card">
            <h3>测试结果明细</h3>
            <table class="results-table">
                <thead>
                    <tr>
                        <th style="width:2.5rem;">#</th>
                        <th style="width:5rem;">方法</th>
                        <th>接口名称 / URL</th>
                        <th style="width:5rem;">状态码</th>
                        <th style="width:5rem;">耗时(ms)</th>
                        <th style="width:5rem;">结果</th>
                        <th>断言详情</th>
                    </tr>
                </thead>
                <tbody>
"""

    if execution.results:
        for i, result in enumerate(execution.results):
            is_passed = result.get('passed', False)
            method = result.get('method', 'GET').upper()
            method_cls = f"m-{method.lower()}" if method.lower() in ('get','post','put','patch','delete') else 'm-other'
            name = result.get('name', f'请求 {i+1}')
            url = result.get('url', '')
            sc = result.get('status_code', '-')
            rt = result.get('response_time', None)
            rt_text = f"{rt:.1f}" if rt is not None else '-'
            error = result.get('error', '')
            assertions = result.get('assertions_results', [])

            assertions_html = ''
            if assertions:
                assertions_html = '<ul class="assertions-list">'
                for a in assertions:
                    a_ok = a.get('passed', False)
                    icon = '✓' if a_ok else '✗'
                    cls = 'a-ok' if a_ok else 'a-err'
                    msg = a.get('message', a.get('name', '断言'))
                    a_type = a.get('type', '')
                    if a_type == 'status_code':
                        msg = f"状态码: 期望 {a.get('expected','?')}，实际 {a.get('actual','?')}"
                    elif a_type == 'response_time':
                        msg = f"响应时间: 期望 ≤{a.get('expected','?')}ms，实际 {a.get('actual_time', a.get('actual','?'))}ms"
                    elif a_type == 'json_path':
                        msg = f"JSON路径 [{a.get('json_path','')}]: 期望 {a.get('expected','?')}，实际 {a.get('actual','?')}"
                    elif a_type == 'contains':
                        msg = f"包含断言: 关键词 &quot;{a.get('expected','?')}&quot; {'存在' if a_ok else '不存在'}"
                    elif a_type == 'header':
                        msg = f"响应头 [{a.get('header_name','')}]: 期望 {a.get('expected','?')}，实际 {a.get('actual','?')}"
                    assertions_html += f'<li class="{cls}"><span>{icon}</span><span>{msg}</span></li>'
                assertions_html += '</ul>'

            if error and not assertions:
                assertions_html = f'<div class="err-box">{error}</div>'

            index_content += f"""
                <tr>
                    <td style="color:#9ca3af;">{i + 1}</td>
                    <td><span class="tag-method {method_cls}">{method}</span></td>
                    <td>
                        <div style="font-weight:600; margin-bottom:3px;">{name}</div>
                        <div class="cell-url">{url}</div>
                    </td>
                    <td style="font-weight:600;">{sc}</td>
                    <td>{rt_text}</td>
                    <td><span class="tag-status {'s-pass' if is_passed else 's-fail'}">{'PASS' if is_passed else 'FAILL'}</span></td>
                    <td>{assertions_html}</td>
                </tr>"""

    index_content += f"""
                </tbody>
            </table>
        </div>

        <div class="footer">报告生成时间：{exec_time} &nbsp;|&nbsp; 测试套件：{suite_name} &nbsp;|&nbsp; 项目：{project_name}</div>
    </div>
</body>
</html>"""

    summary_file = os.path.join(report_output_dir, 'summary.html')
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(index_content)

    return summary_file


def generate_test_result_files(execution, report_dir):
    """生成测试结果文件（含详细入参、响应及断言比对）"""
    try:
        if not execution.results:
            logger.warning(f"执行记录 {execution.id} 没有结果数据")
            return

        # 批量加载请求历史，避免 N+1 查询
        history_ids = [r.get('history_id') for r in execution.results if r.get('history_id')]
        histories = {}
        if history_ids:
            for h in RequestHistory.objects.filter(id__in=history_ids).values(
                    'id', 'request_data', 'response_data', 'status_code', 'response_time'):
                histories[h['id']] = h

        container_data = {
            "uuid": str(execution.id),
            "name": execution.test_suite.name,
            "children": [f"{execution.id}-{i}" for i in range(len(execution.results))]
        }

        container_file_path = os.path.join(report_dir, f'{execution.id}-container.json')
        with open(container_file_path, 'w', encoding='utf-8') as f:
            json.dump(container_data, f, ensure_ascii=False, indent=2)

        # 使用执行开始时间作为基准，每个用例间隔 2 秒，确保按先执行在前排序
        import math as _math
        base_ts = int(
            (execution.start_time or execution.created_at).timestamp() * 1000
        ) if (execution.start_time or execution.created_at) else int(time.time() * 1000)

        for i, result in enumerate(execution.results):
            test_start = base_ts + i * 2000
            test_stop = test_start + 1800

            # ── 构建 Parameters（入参，密码字段已掩码） ──────────────────
            parameters = [
                {"name": "method",        "value": result.get('method', 'GET')},
                {"name": "url",           "value": result.get('url', '')},
                {"name": "status_code",   "value": str(result.get('status_code', 'N/A'))},
                {"name": "response_time", "value": f"{result.get('response_time', 0):.2f}ms"
                 if result.get('response_time') is not None else 'N/A'},
            ]

            history = histories.get(result.get('history_id'))
            req_data = {}
            resp_data = {}
            if history:
                req_data  = history.get('request_data')  or {}
                resp_data = history.get('response_data') or {}

                # 请求头（过滤敏感字段）
                req_headers = _mask_sensitive_data(req_data.get('headers') or {})
                if req_headers and isinstance(req_headers, dict):
                    for k, v in req_headers.items():
                        parameters.append({"name": f"header.{k}", "value": str(v)})

                # 查询参数
                req_params = _mask_sensitive_data(req_data.get('params') or {})
                if req_params and isinstance(req_params, dict):
                    for k, v in req_params.items():
                        parameters.append({"name": f"query.{k}", "value": str(v)})
                elif req_params and isinstance(req_params, str) and req_params:
                    parameters.append({"name": "query_string", "value": req_params})

                # 请求体（掩码敏感字段，截断超长内容）
                req_body = _mask_sensitive_data(req_data.get('body'))
                if req_body is not None:
                    if isinstance(req_body, (dict, list)):
                        body_str = json.dumps(req_body, ensure_ascii=False, indent=2)
                    else:
                        body_str = str(req_body)
                    if len(body_str) > 1000:
                        body_str = body_str[:1000] + '\n...(内容已截断)'
                    parameters.append({"name": "request_body", "value": body_str})

            # ── 构建 Steps（Test Body） ────────────────────────────────

            # Step 1: 发送请求 - 展示请求摘要
            req_summary_lines = [
                f"{result.get('method', 'GET')}  {result.get('url', '')}",
            ]
            if req_data.get('params'):
                req_summary_lines.append(f"Query Params: {json.dumps(_mask_sensitive_data(req_data.get('params')), ensure_ascii=False)}")
            if req_data.get('body'):
                body_preview = _mask_sensitive_data(req_data.get('body'))
                body_preview_str = json.dumps(body_preview, ensure_ascii=False) if isinstance(body_preview, (dict, list)) else str(body_preview)
                if len(body_preview_str) > 300:
                    body_preview_str = body_preview_str[:300] + '...'
                req_summary_lines.append(f"Request Body: {body_preview_str}")

            send_step = {
                "name": "发送请求",
                "status": "passed",
                "stage": "finished",
                "start": test_start,
                "stop": test_start + 800,
                "description": "\n".join(req_summary_lines),
                "steps": []
            }

            # Step 2: 验证响应 - 展示响应状态 + body
            resp_body_raw = resp_data.get('body', '') or ''
            resp_body_preview = resp_body_raw[:800] + ('...(已截断)' if len(resp_body_raw) > 800 else '')
            resp_status = result.get('status_code', history.get('status_code', '-') if history else '-')
            resp_time = result.get('response_time', history.get('response_time', '-') if history else '-')
            resp_rt_text = f"{resp_time:.2f}ms" if isinstance(resp_time, (int, float)) else str(resp_time)
            resp_summary = (
                f"HTTP {resp_status}  |  耗时 {resp_rt_text}\n\n"
                    f"Response Body:\n{resp_body_preview}"
            )

            # 断言子步骤
            assertion_steps = []
            for j, assertion in enumerate(result.get('assertions_results', [])):
                a_ok = assertion.get('passed', False)
                a_type = assertion.get('type', 'unknown')
                a_name = assertion.get('name', f'断言 {j+1}')
                a_msg = assertion.get('message', '')

                # 构造比对详情
                if a_type == 'status_code':
                    detail = f"类型: 状态码断言 | 期望: {assertion.get('expected', '?')} | 实际: {assertion.get('actual', '?')}"
                elif a_type == 'response_time':
                    detail = f"类型: 响应时间断言 | 期望: ≤{assertion.get('expected', '?')}ms | 实际: {assertion.get('actual_time', assertion.get('actual', '?'))}ms"
                elif a_type == 'json_path':
                    detail = (
                        f"类型: JSON路径断言 | 路径: {assertion.get('json_path', '')} | "
                            f"期望: {assertion.get('expected', '?')} | 实际: {assertion.get('actual', '?')}"
                    )
                elif a_type == 'contains':
                    detail = f"类型: 包含断言 | 关键词: {assertion.get('expected', '?')} | 结果: {'找到' if a_ok else '未找到'}"
                elif a_type == 'header':
                    detail = (
                        f"类型: 响应头断言 | 头名称: {assertion.get('header_name', '')} | "
                            f"期望: {assertion.get('expected', '?')} | 实际: {assertion.get('actual', '?')}"
                    )
                elif a_type == 'equals':
                    detail = f"类型: 相等断言 | 期望: {assertion.get('expected', '?')} | 实际: {assertion.get('actual', '?')}"
                elif a_type == 'mongo_match':
                    mongo_r = assertion.get('mongo_result', {})
                    total = mongo_r.get('total', 0)
                    passed_c = mongo_r.get('successful_count', 0)
                    failed_c = mongo_r.get('failed_count', 0)
                    detail = f"类型: MongoDB断言 | 总检查点: {total} | 通过: {passed_c} | 失败: {failed_c}"
                else:
                    detail = f"类型: {a_type} | {a_msg}"

                # MongoDB 断言：为每个失败的匹配项生成子步骤
                mongo_sub_steps = []
                if a_type == 'mongo_match':
                    mongo_r = assertion.get('mongo_result', {})
                    for k, fm in enumerate(mongo_r.get('failed_matches', [])):
                        mongo_sub_steps.append({
                            "name": f"✗ {fm.get('path', '?')} [{fm.get('operator', '?')}] 期望: {fm.get('expected', '?')} | 实际: {fm.get('actual', '?')}",
                            "status": "failed",
                            "stage": "finished",
                            "start": test_start + 900 + j * 10 + k,
                            "stop": test_start + 901 + j * 10 + k,
                            "steps": []
                        })
                    for k, sm in enumerate(mongo_r.get('successful_matches', [])):
                        mongo_sub_steps.append({
                            "name": f"✓ {sm.get('path', '?')} [{sm.get('operator', '?')}] 期望: {sm.get('expected', '?')} | 实际: {sm.get('actual', '?')}",
                            "status": "passed",
                            "stage": "finished",
                            "start": test_start + 900 + j * 10 + len(mongo_r.get('failed_matches', [])) + k,
                            "stop": test_start + 901 + j * 10 + len(mongo_r.get('failed_matches', [])) + k,
                            "steps": []
                        })

                a_step = {
                    "name": f"{'✓' if a_ok else '✗'} {a_name}: {detail}",
                    "status": "passed" if a_ok else "failed",
                    "stage": "finished",
                    "start": test_start + 900 + j * 10,
                    "stop": test_start + 910 + j * 10,
                    "steps": mongo_sub_steps
                }
                if not a_ok and assertion.get('error'):
                    a_step["statusDetails"] = {"message": assertion.get('error'), "trace": ""}
                assertion_steps.append(a_step)

            verify_step = {
                "name": "验证响应",
                "status": "passed" if result.get('passed', False) else "failed",
                "stage": "finished",
                "start": test_start + 800,
                "stop": test_stop,
                "description": resp_summary,
                "steps": assertion_steps
            }

            request_result = {
                "uuid": f"{execution.id}-{i}",
                "name": result.get('name', f'测试请求 {i+1}'),
                "status": "passed" if result.get('passed', False) else "failed",
                "stage": "finished",
                "start": test_start,
                "stop": test_stop,
                "description": f"{result.get('method', 'GET')} {result.get('url', '')}",
                "historyId": f"{execution.test_suite.id}-{i}",
                "fullName": f"{execution.test_suite.name} / {result.get('name', f'请求 {i+1}')}",
                "links": [],
                "labels": [
                    {"name": "suite",      "value": execution.test_suite.name},
                    {"name": "testClass",  "value": execution.test_suite.name},
                    {"name": "package",    "value": "api_testing"},
                    {"name": "project",    "value": execution.test_suite.project.name}
                ],
                "parameters": parameters,
                "steps": [send_step, verify_step]
            }

            if result.get('error'):
                request_result["statusDetails"] = {
                    "message": result.get('error'),
                    "trace": resp_body_preview if resp_body_preview else ""
                }

            request_file_path = os.path.join(report_dir, f'{execution.id}-{i}-result.json')
            with open(request_file_path, 'w', encoding='utf-8') as f:
                json.dump(request_result, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"生成测试结果文件失败: {str(e)}", exc_info=True)
        raise
