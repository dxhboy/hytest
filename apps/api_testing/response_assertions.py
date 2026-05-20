# response_assertions.py
import json
import re
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta


class PMResponse:
    """模拟Postman的pm.response对象"""

    def __init__(self, response):
        """
        初始化响应对象

        Args:
            response: requests.Response对象
        """
        self._response = response
        self._json_data = None
        self._status = PMStatus(self)
        self._to = PMTo(self)

    @property
    def code(self) -> int:
        """获取响应状态码"""
        return self._response.status_code

    @property
    def status(self) -> str:
        """获取响应状态文本"""
        return self._response.reason

    @property
    def headers(self) -> Dict:
        """获取响应头"""
        return dict(self._response.headers)

    @property
    def response_time(self) -> int:
        """获取响应时间（毫秒）"""
        return getattr(self._response, 'elapsed', timedelta(seconds=0)).total_seconds() * 1000

    def json(self) -> Dict:
        """获取响应JSON数据"""
        if self._json_data is None:
            try:
                self._json_data = self._response.json()
            except:
                self._json_data = {}
        return self._json_data

    def text(self) -> str:
        """获取响应文本"""
        return self._response.text

    @property
    def to(self):
        """获取to对象，用于断言链"""
        return self._to


class PMStatus:
    """模拟Postman的pm.response.to.have.status"""

    def __init__(self, response):
        self._response = response

    @property
    def have(self):
        return PMHave(self._response)


class PMHave:
    """模拟Postman的pm.response.to.have"""

    def __init__(self, response):
        self._response = response

    def status(self, code: int) -> bool:
        """断言状态码"""
        return self._response.code == code

    def header(self, key: str) -> bool:
        """断言存在指定响应头"""
        return key in self._response.headers

    def cookie(self, name: str) -> bool:
        """断言存在指定cookie"""
        cookies = self._response._response.cookies.get_dict()
        return name in cookies

    def json_body(self) -> bool:
        """断言响应体是JSON格式"""
        try:
            self._response.json()
            return True
        except:
            return False


class PMExpect:
    """模拟Postman的pm.expect"""

    def __init__(self, actual: Any):
        self.actual = actual

    def to(self):
        return PMExpectTo(self.actual)


class PMExpectTo:
    """模拟Postman的pm.expect().to"""

    def __init__(self, actual: Any):
        self.actual = actual

    def eql(self, expected: Any) -> bool:
        """断言相等"""
        return self.actual == expected

    def equal(self, expected: Any) -> bool:
        """断言相等（别名）"""
        return self.actual == expected

    def include(self, item: Any) -> bool:
        """断言包含"""
        if isinstance(self.actual, (str, list, tuple, dict)):
            return item in self.actual
        return False

    def be_a(self, type_name: str) -> bool:
        """断言类型"""
        if type_name == 'string':
            return isinstance(self.actual, str)
        elif type_name == 'number':
            return isinstance(self.actual, (int, float))
        elif type_name == 'boolean':
            return isinstance(self.actual, bool)
        elif type_name == 'array':
            return isinstance(self.actual, list)
        elif type_name == 'object':
            return isinstance(self.actual, dict)
        return False

    def match(self, pattern: Union[str, re.Pattern]) -> bool:
        """断言匹配正则表达式"""
        if isinstance(self.actual, str):
            if isinstance(pattern, str):
                pattern = re.compile(pattern)
            return bool(pattern.search(self.actual))
        return False

    def be_null(self) -> bool:
        """断言为null"""
        return self.actual is None

    def be_true(self) -> bool:
        """断言为true"""
        return self.actual is True

    def be_false(self) -> bool:
        """断言为false"""
        return self.actual is False

    def be_above(self, value: Union[int, float]) -> bool:
        """断言大于"""
        if isinstance(self.actual, (int, float)):
            return self.actual > value
        return False

    def be_below(self, value: Union[int, float]) -> bool:
        """断言小于"""
        if isinstance(self.actual, (int, float)):
            return self.actual < value
        return False

    def be_empty(self) -> bool:
        """断言为空"""
        if hasattr(self.actual, '__len__'):
            return len(self.actual) == 0
        return not bool(self.actual)


class PM:
    """模拟Postman的pm对象"""

    def __init__(self, response=None, variables=None):
        """
        初始化pm对象

        Args:
            response: requests.Response对象
            variables: VariableResolver对象或变量字典
        """
        self._response = None
        self._variables = variables
        self._test_results = []
        self._environment = PMEnvironment(variables)
        self._vars = PMVariables(variables)

        if response:
            self.response = PMResponse(response)

    @property
    def response(self) -> PMResponse:
        """获取响应对象"""
        return self._response

    @response.setter
    def response(self, value):
        """设置响应对象"""
        self._response = value

    @property
    def environment(self):
        """获取环境变量对象"""
        return self._environment

    @property
    def vars(self):
        """获取变量对象"""
        return self._vars

    def test(self, name: str, test_func) -> Dict:
        """
        执行测试断言

        Args:
            name: 测试名称
            test_func: 测试函数，返回布尔值

        Returns:
            测试结果字典
        """
        result = {
            'name': name,
            'passed': False,
            'error': None
        }

        try:
            # 执行测试函数
            passed = test_func()
            result['passed'] = passed
        except AssertionError as e:
            result['error'] = str(e)
        except Exception as e:
            result['error'] = f"测试执行异常: {str(e)}"

        self._test_results.append(result)
        return result

    def expect(self, actual: Any) -> PMExpect:
        """创建期望对象"""
        return PMExpect(actual)

    def get_test_results(self) -> List[Dict]:
        """获取所有测试结果"""
        return self._test_results

    def clear_test_results(self):
        """清除测试结果"""
        self._test_results = []


class PMEnvironment:
    """模拟Postman的pm.environment"""

    def __init__(self, variables=None):
        self._variables = variables or {}

    def get(self, key: str, default=None):
        """获取环境变量"""
        if hasattr(self._variables, 'get_variable'):
            return self._variables.get_variable(key) or default
        elif isinstance(self._variables, dict):
            value = self._variables.get(key)
            if isinstance(value, dict):
                return value.get('currentValue', value.get('initialValue', default))
            return value or default
        return default

    def set(self, key: str, value: Any):
        """设置环境变量"""
        if hasattr(self._variables, 'set_variable'):
            self._variables.set_variable(key, value)
        elif isinstance(self._variables, dict):
            self._variables[key] = value


class PMVariables:
    """模拟Postman的pm.variables"""

    def __init__(self, variables=None):
        self._variables = variables or {}

    def get(self, key: str, default=None):
        """获取变量"""
        if hasattr(self._variables, 'get_variable'):
            return self._variables.get_variable(key) or default
        elif isinstance(self._variables, dict):
            value = self._variables.get(key)
            if isinstance(value, dict):
                return value.get('currentValue', value.get('initialValue', default))
            return value or default
        return default

    def set(self, key: str, value: Any):
        """设置变量"""
        if hasattr(self._variables, 'set_variable'):
            self._variables.set_variable(key, value)
        elif isinstance(self._variables, dict):
            self._variables[key] = value


def create_pm(response=None, variables=None):
    """
    创建pm对象

    Args:
        response: requests.Response对象
        variables: VariableResolver对象或变量字典

    Returns:
        PM对象
    """
    return PM(response, variables)


def execute_post_response_scripts(scripts: List[str], response, variables=None) -> List[Dict]:
    """
    执行Post-Response脚本

    Args:
        scripts: 脚本列表
        response: requests.Response对象
        variables: VariableResolver对象或变量字典

    Returns:
        测试结果列表
    """
    pm_obj = create_pm(response, variables)

    for script in scripts:
        try:
            # 创建执行环境
            exec_globals = {
                'pm': pm_obj,
                'response': pm_obj.response,
                'console': type('Console', (), {
                    'log': lambda *args: print(f"[console.log]", *args)
                })(),
                '__builtins__': __builtins__
            }

            # 执行脚本
            exec(script, exec_globals)
        except Exception as e:
            # 记录脚本执行错误
            pm_obj.test(f"脚本执行错误", lambda: False)
            print(f"执行Post-Response脚本时出错: {str(e)}")

    return pm_obj.get_test_results()