from .base import ToolDispatcher
from .api_testing_tools import (
    list_interfaces, get_interface, create_interface,
    list_test_suites, run_test_suite, get_execution_result,
)
from .ui_automation_tools import (
    list_ui_suites, get_ui_suite, run_ui_suite,
    list_ui_elements, get_ui_execution_result,
)

# 注册所有工具
_TOOLS = {
    'list_interfaces': list_interfaces,
    'get_interface': get_interface,
    'create_interface': create_interface,
    'list_test_suites': list_test_suites,
    'run_test_suite': run_test_suite,
    'get_execution_result': get_execution_result,
    'list_ui_suites': list_ui_suites,
    'get_ui_suite': get_ui_suite,
    'run_ui_suite': run_ui_suite,
    'list_ui_elements': list_ui_elements,
    'get_ui_execution_result': get_ui_execution_result,
}
for _name, _func in _TOOLS.items():
    ToolDispatcher.register(_name, _func)

# OpenAI function calling 格式的工具定义
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_interfaces",
            "description": "列出 api-testing 模块的接口用例，可按项目ID或名称关键词过滤",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目ID，不填则返回用户可见的所有接口"},
                    "keyword": {"type": "string", "description": "按名称关键词模糊搜索"},
                    "limit": {"type": "integer", "description": "返回条数，默认20，最大50"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_interface",
            "description": "获取单条接口用例的完整详情（含 headers、body、断言等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "interface_id": {"type": "integer", "description": "接口用例ID"},
                },
                "required": ["interface_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_interface",
            "description": "创建新的接口用例",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "接口名称"},
                    "method": {"type": "string", "description": "HTTP 方法：GET/POST/PUT/DELETE/PATCH"},
                    "url": {"type": "string", "description": "请求 URL"},
                    "collection_id": {"type": "integer", "description": "所属集合ID（可选）"},
                    "description": {"type": "string", "description": "接口描述（可选）"},
                    "headers": {"type": "object", "description": "请求头（可选）"},
                    "params": {"type": "object", "description": "查询参数（可选）"},
                    "body": {"type": "object", "description": "请求体（可选）"},
                },
                "required": ["name", "method", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_test_suites",
            "description": "列出 api-testing 自动化测试套件",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目ID（可选）"},
                    "keyword": {"type": "string", "description": "名称关键词（可选）"},
                    "limit": {"type": "integer", "description": "返回条数，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_test_suite",
            "description": "触发 api-testing 测试套件执行，返回执行ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "integer", "description": "套件ID"},
                },
                "required": ["suite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_execution_result",
            "description": "查询 api-testing 或 ui-automation 的执行结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "execution_id": {"type": "integer", "description": "执行记录ID"},
                    "module": {"type": "string", "description": "模块：api-testing 或 ui-automation，默认 api-testing"},
                },
                "required": ["execution_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_suites",
            "description": "列出 UI 自动化测试套件",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目ID（可选）"},
                    "keyword": {"type": "string", "description": "名称关键词（可选）"},
                    "limit": {"type": "integer", "description": "返回条数，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ui_suite",
            "description": "获取 UI 测试套件详情",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "integer", "description": "UI 套件ID"},
                },
                "required": ["suite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_ui_suite",
            "description": "触发 UI 测试套件执行",
            "parameters": {
                "type": "object",
                "properties": {
                    "suite_id": {"type": "integer", "description": "UI 套件ID"},
                },
                "required": ["suite_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_ui_elements",
            "description": "列出 UI 元素库",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目ID（可选）"},
                    "keyword": {"type": "string", "description": "名称关键词（可选）"},
                    "limit": {"type": "integer", "description": "返回条数，默认20"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ui_execution_result",
            "description": "查询 UI 自动化执行结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "execution_id": {"type": "integer", "description": "UI 执行记录ID"},
                },
                "required": ["execution_id"],
            },
        },
    },
]
