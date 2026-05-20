# apps/core/pm_context.py
import json as _json


class _EnvironmentProxy:
    def __init__(self, variables: dict):
        self._vars = variables
        self._updated: dict = {}

    def set(self, key: str, value):
        self._vars[str(key)] = value
        self._updated[str(key)] = value

    def get(self, key: str, default=None):
        return self._vars.get(str(key), default)


class _VariablesProxy(_EnvironmentProxy):
    """临时变量，行为与 environment 相同，共享同一 dict"""
    pass


class _RequestProxy:
    class _HeadersHelper:
        def __init__(self, proxy):
            self._proxy = proxy

        def add(self, key: str, value: str):
            self._proxy._extra_headers[str(key)] = str(value)

    def __init__(self):
        self._extra_headers: dict = {}
        self.headers = self._HeadersHelper(self)


class _ResponseProxy:
    def __init__(self, response):
        self._response = response

    def json(self):
        if self._response is None:
            return {}
        try:
            return self._response.json()
        except Exception:  # 包括 JSONDecodeError、AttributeError 等
            return {}

    @property
    def text(self) -> str:
        if self._response is None:
            return ''
        return self._response.text

    @property
    def code(self) -> int:
        if self._response is None:
            return 0
        return self._response.status_code

    @property
    def headers(self) -> dict:
        if self._response is None:
            return {}
        return dict(self._response.headers)


class PmObject:
    def __init__(self, variables: dict, response=None):
        self.environment = _EnvironmentProxy(variables)
        self.variables = _VariablesProxy(variables)
        self.request = _RequestProxy()
        self.response = _ResponseProxy(response)


def execute_pm_script(script: str, variables: dict, response=None) -> dict:
    """执行 Python 脚本，注入 pm 对象。

    注意：脚本以完整 Python 权限执行（含 __builtins__），仅限受信任的测试工程师使用。

    Returns:
        {
          'variables': dict,        # 新增/修改的变量
          'extra_headers': dict,    # 需合并到请求头的额外头
          'console': list[str],     # print() 输出
          'errors': list[str],      # 执行期间的异常信息
        }
    """
    pm = PmObject(variables, response)
    console_output = []
    errors = []

    def _print(*args, **kwargs):
        sep = kwargs.get('sep', ' ')
        console_output.append(sep.join(str(a) for a in args))

    exec_context = {
        'pm': pm,
        'print': _print,
        'json': _json,
        '__builtins__': __builtins__,
    }

    try:
        exec(compile(script, '<pm_script>', 'exec'), exec_context)
    except Exception as e:
        errors.append(str(e))

    return {
        'variables': {**pm.environment._updated, **pm.variables._updated},
        'extra_headers': pm.request._extra_headers,
        'console': console_output,
        'errors': errors,
    }
