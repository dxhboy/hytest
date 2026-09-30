# apps/core/pm_context.py
import ast
import builtins as _builtins
import json as _json

# 脚本可 import 的模块：满足签名、时间戳、编码等常见前后置需求，不含文件/进程/网络能力
ALLOWED_MODULES = frozenset({
    'base64', 'binascii', 'datetime', 'decimal', 'hashlib', 'hmac', 'json', 'math',
    'random', 're', 'string', 'time', 'urllib.parse', 'uuid', 'collections', 'itertools',
    'functools', 'copy',
})

_SAFE_BUILTIN_NAMES = (
    'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray', 'bytes', 'callable', 'chr',
    'complex', 'dict', 'divmod', 'enumerate', 'filter', 'float', 'format', 'frozenset',
    'hasattr', 'hash', 'hex', 'int', 'isinstance', 'issubclass', 'iter', 'len', 'list', 'map',
    'max', 'min', 'next', 'object', 'oct', 'ord', 'pow', 'range', 'repr', 'reversed', 'round',
    'set', 'slice', 'sorted', 'str', 'sum', 'tuple', 'zip',
    'Exception', 'ValueError', 'TypeError', 'KeyError', 'IndexError', 'AttributeError',
    'ZeroDivisionError', 'RuntimeError', 'StopIteration',
)


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level != 0 or name not in ALLOWED_MODULES:
        raise ImportError(f"脚本中不允许导入模块 '{name}'，可用模块: {', '.join(sorted(ALLOWED_MODULES))}")
    return __import__(name, globals, locals, fromlist, level)


def _safe_getattr(obj, name, *default):
    if isinstance(name, str) and name.startswith('_'):
        raise AttributeError(f"脚本中不允许访问私有属性 '{name}'")
    return getattr(obj, name, *default)


def _build_safe_builtins():
    safe = {name: getattr(_builtins, name) for name in _SAFE_BUILTIN_NAMES}
    safe['__import__'] = _safe_import
    safe['__build_class__'] = _builtins.__build_class__  # 允许脚本内定义 class
    safe['getattr'] = _safe_getattr
    return safe


def _validate_script(tree):
    """禁止访问下划线开头的属性/名称，堵住 ().__class__.__subclasses__() 之类的逃逸路径"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
            raise ValueError(f"第 {node.lineno} 行：不允许访问私有属性 '{node.attr}'")
        if isinstance(node, ast.Name) and node.id.startswith('__'):
            raise ValueError(f"第 {node.lineno} 行：不允许使用名称 '{node.id}'")
        if isinstance(node, (ast.Import, ast.ImportFrom)) and getattr(node, 'level', 0):
            raise ValueError(f"第 {node.lineno} 行：不允许相对导入")


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

    脚本在受限环境中执行：只提供安全的内置函数、只能导入 ALLOWED_MODULES 中的模块、
    禁止访问下划线开头的属性。这是纵深防御而非完整沙箱，脚本编辑权限仍应只给可信用户。

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
        '__name__': '__pm_script__',
        '__builtins__': _build_safe_builtins(),
    }

    try:
        tree = ast.parse(script, '<pm_script>', 'exec')
        _validate_script(tree)
        exec(compile(tree, '<pm_script>', 'exec'), exec_context)
    except Exception as e:
        errors.append(str(e))

    return {
        'variables': {**pm.environment._updated, **pm.variables._updated},
        'extra_headers': pm.request._extra_headers,
        'console': console_output,
        'errors': errors,
    }
