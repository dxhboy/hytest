import json
import time
import logging
from django.utils import timezone
from .models import RequestHistory
from .variable_resolver import VariableResolver
from ..core.variable_resolver import parse_and_execute_script, execute_with_response

# 获取logger实例
logger = logging.getLogger(__name__)


def _preprocess_mongo_expected(expected):
    """将 {$regex: '...', $options: 'i'} 合并为 {$regex: '(?i)...'} 以兼容 validator.
    递归处理整个 expected 树。
    """
    if isinstance(expected, dict):
        # 同一层同时出现 $regex 和 $options，合并为内联 flags
        if '$regex' in expected and '$options' in expected:
            pattern = expected['$regex']
            options = expected['$options']
            flag_map = {'i': 'i', 'm': 'm', 's': 's', 'x': 'x'}
            flags_str = ''.join(flag_map[c] for c in options if c in flag_map)
            if flags_str:
                pattern = f'(?{flags_str}){pattern}'
            result = {k: _preprocess_mongo_expected(v)
                      for k, v in expected.items()
                      if k not in ('$regex', '$options')}
            result['$regex'] = pattern
            return result
        return {k: _preprocess_mongo_expected(v) for k, v in expected.items()}
    if isinstance(expected, list):
        return [_preprocess_mongo_expected(item) for item in expected]
    return expected

def execute_assertions(response, assertions, variables=None):
    """执行断言验证 - 优化版本，确保断言结果结构完整"""
    results = []

    # 如果没有断言，返回一个默认的通过结果
    if not assertions:
        return [{
            'name': '无断言配置',
            'type': 'none',
            'passed': True,
            'expected': None,
            'actual': None,
            'error': None,
            'message': '无断言配置'
        }]

    for assertion in assertions:
        # 确保断言是字典类型
        if not isinstance(assertion, dict):
            continue

        result = {
            'name': assertion.get('name', '未命名断言'),
            'type': assertion.get('type', 'unknown'),
            'passed': False,
            'expected': assertion.get('expected'),
            'actual': None,
            'error': None,
            'message': ''
        }

        try:
            assertion_type = assertion.get('type')
            expected = assertion.get('expected')
            actual = None
            passed = False

            # 状态码断言
            if assertion_type == 'status_code':
                actual = response.status_code
                passed = actual == expected
                result['message'] = f"状态码断言: 期望 {expected}, 实际 {actual}"

            # 响应时间断言
            elif assertion_type == 'response_time':
                actual = assertion.get('actual_time')
                if actual is not None:
                    passed = actual <= expected
                    result['message'] = f"响应时间断言: 期望 <= {expected}ms, 实际 {actual:.2f}ms"
                else:
                    result['error'] = "未提供实际响应时间"
                    result['message'] = "响应时间断言失败: 未获取到响应时间"

            # 包含断言
            elif assertion_type == 'contains':
                text = response.text or ''
                pattern = str(expected)
                # 截取实际值用于显示
                actual = pattern in str(text)
                passed = actual
                result['actual'] = pattern in str(text)  # 存储布尔值
                result['message'] = f"包含断言: {'找到' if passed else '未找到'} '{pattern}'"

            # JSON路径断言
            elif assertion_type == 'json_path':
                json_path = assertion.get('json_path', '')
                expected_value = assertion.get('expected')
                actual = None
                passed = False

                try:
                    # 检查响应是否为JSON格式
                    content_type = response.headers.get('content-type', '').lower()
                    if 'application/json' not in content_type:
                        raise ValueError(f"响应不是JSON格式，Content-Type: {content_type}")

                    response_json = json.loads(response.text)

                    # 检查JSONPath表达式是否为空
                    if not json_path:
                        raise ValueError("JSON路径表达式不能为空")

                    from jsonpath_ng import parse
                    matches = parse(json_path).find(response_json)
                    actual = matches[0].value if matches else None
                    passed = str(actual) == str(expected_value)
                    result['message'] = f"JSON路径断言: 路径 '{json_path}' {'匹配' if passed else '不匹配'}"

                except json.JSONDecodeError as e:
                    result['error'] = f"JSON解析失败: {str(e)}"
                    result['message'] = f"JSON解析失败"
                except ImportError as e:
                    result['error'] = f"缺少依赖库: {str(e)}，请安装jsonpath-ng"
                    result['message'] = f"JSONPath库未安装"
                except Exception as e:
                    result['error'] = f"执行错误: {str(e)}"
                    result['message'] = f"JSON路径执行错误"

            # 请求头断言
            elif assertion_type == 'header':
                header_name = assertion.get('header_name', '')
                expected_value = assertion.get('expected')
                actual = response.headers.get(header_name)
                passed = actual == expected_value
                result['message'] = f"请求头断言: 头 '{header_name}' {'匹配' if passed else '不匹配'}"

            # 相等断言
            elif assertion_type == 'equals':
                actual = response.text.strip()
                passed = actual == str(expected).strip()
                result['message'] = f"相等断言: {'相等' if passed else '不相等'}"

            # MongoDB风格响应体匹配断言
            elif assertion_type == 'mongo_match':
                from apps.core.validator import compare_mongo_style
                expected_json = assertion.get('expected')

                # 若 expected 是字符串，尝试解析为 JSON
                if isinstance(expected_json, str):
                    try:
                        expected_json = json.loads(expected_json)
                    except (json.JSONDecodeError, ValueError) as e:
                        raise ValueError(f'expected 不是有效的 JSON: {str(e)}')

                # 解析 expected 中的 {{变量}} 占位符
                if variables and expected_json is not None:
                    try:
                        exp_str = json.dumps(expected_json, ensure_ascii=False)
                        for k, v in variables.items():
                            exp_str = exp_str.replace('{{' + str(k) + '}}', str(v))
                        expected_json = json.loads(exp_str)
                    except Exception:
                        pass  # 替换失败则使用原始值

                # 获取实际响应 JSON
                try:
                    actual = response.json()
                except Exception:
                    actual = response.text

                # 预处理：合并 {$regex, $options} 为内联 flags，避免 $options 被识别为不支持操作符
                expected_json = _preprocess_mongo_expected(expected_json)
                match_result = compare_mongo_style(actual, expected_json)
                # 使用 failed_count 判断，避免 validator 的 all_success 字段 bug
                total = match_result.get('total_matches', 0)
                failed_c = match_result.get('failed_count', 0)
                success_c = match_result.get('successful_count', 0)
                passed = failed_c == 0 and total > 0
                result['expected'] = expected_json
                if passed:
                    result['message'] = f"MongoDB断言通过（{success_c}/{total} 个检查点）"
                else:
                    failed_paths = [m.get('path', '?') for m in match_result.get('failed_matches', [])]
                    result['message'] = f"MongoDB断言失败: {failed_c}/{total} 个检查点不符（路径: {failed_paths}）"
                result['mongo_result'] = {
                    'total': match_result.get('total_matches', 0),
                    'successful_count': match_result.get('successful_count', 0),
                    'failed_count': match_result.get('failed_count', 0),
                    'failed_matches': match_result.get('failed_matches', []),
                    'successful_matches': match_result.get('successful_matches', []),
                }

            # 设置实际值
            if actual is not None:
                result['actual'] = actual
            result['passed'] = passed

        except Exception as e:
            result['error'] = str(e)
            result['message'] = f"断言执行异常: {str(e)}"
            result['passed'] = False

        results.append(result)

    return results


def execute_test_suite(test_suite, environment, executed_by):
    """执行测试套件并返回结果 - 优化版本，支持Session和脚本"""
    from .models import TestExecution, RequestHistory
    import requests
    import time

    try:
        # 创建变量解析器
        resolver = VariableResolver()

        # 创建Session，支持自动管理cookies和连接
        session = requests.Session()

        # 创建执行记录
        execution = TestExecution.objects.create(
            test_suite=test_suite,
            status='RUNNING',
            start_time=timezone.now(),
            executed_by=executed_by
        )

        # 获取套件中的请求
        suite_requests = test_suite.testsuiterequest_set.filter(enabled=True).order_by('order')

        execution.total_requests = suite_requests.count()
        execution.save()

        results = []
        passed_count = 0
        failed_count = 0

        # 认证变量，支持自动token更新
        auth_variables = {}
        token_type = 'Bearer'

        # 执行每个请求
        for suite_request in suite_requests:
            api_request = suite_request.request

            try:
                # 准备变量（环境变量 + 认证变量）
                variables = {}
                if environment:
                    variables.update(environment.variables)
                variables.update(auth_variables)

                # 执行预处理脚本
                if api_request.pre_request_script:
                    try:
                        script_context = {
                            'variables': variables,
                            'resolver': resolver,
                            'runtime_vars': resolver.runtime_variables
                        }
                        parse_and_execute_script(api_request.pre_request_script, script_context)
                    except Exception as e:
                        logger.warning(f"预处理脚本执行失败: {str(e)}")

                # 替换URL中的变量
                url = _replace_variables(api_request.url, variables)
                url = resolver.resolve(url)

                # 准备请求头
                headers = {}
                if isinstance(api_request.headers, list):
                    for header_item in api_request.headers:
                        if header_item.get('enabled', True) and header_item.get('key'):
                            key = header_item['key']
                            value = _replace_variables(str(header_item.get('value', '')), variables)
                            value = resolver.resolve(value)
                            headers[key] = value
                else:
                    headers = api_request.headers.copy() if api_request.headers else {}
                    for key, value in headers.items():
                        headers[key] = _replace_variables(str(value), variables)
                        headers[key] = resolver.resolve(headers[key])

                # 自动添加认证头
                if 'token' in auth_variables and 'Authorization' not in headers:
                    headers['Authorization'] = f'{token_type} {auth_variables["token"]}'

                # 准备请求参数
                params = api_request.params.copy() if api_request.params else {}
                for key, value in params.items():
                    params[key] = _replace_variables(str(value), variables)
                    params[key] = resolver.resolve(params[key])

                # 准备请求体
                body_data = None
                body_type = 'none'
                if api_request.body and api_request.method in ['POST', 'PUT', 'PATCH']:
                    raw_body_type = api_request.body.get('type', 'raw')
                    if raw_body_type == 'json':
                        body_data = api_request.body.get('data', {})
                        body_data = _replace_variables_in_dict(body_data, variables)
                        body_data = _resolve_variables_in_dict(body_data, resolver)
                        body_type = 'json'
                    elif raw_body_type in ['x-www-form-urlencoded', 'form-data']:
                        body_data = _prepare_form_data(api_request.body.get('data', {}), variables, resolver)
                        body_type = raw_body_type

                # 根据 body 类型修正 Content-Type，防止用户配置的头与实际发送格式冲突
                if body_type == 'json':
                    headers['Content-Type'] = 'application/json'
                elif body_type == 'x-www-form-urlencoded':
                    headers['Content-Type'] = 'application/x-www-form-urlencoded'
                elif body_type == 'form-data':
                    headers.pop('Content-Type', None)

                # 执行请求（使用Session）
                start_time = time.time()
                request_kwargs = {
                    'method': api_request.method,
                    'url': url,
                    'headers': headers,
                    'params': params,
                    'timeout': 30
                }
                if body_type == 'json':
                    request_kwargs['json'] = body_data
                else:
                    request_kwargs['data'] = body_data

                response = session.request(**request_kwargs)
                end_time = time.time()
                response_time = (end_time - start_time) * 1000

                # 执行后处理脚本，提取 Tests 中的 MongoDB 断言
                script_assertions = []
                if api_request.post_request_script:
                    try:
                        script_result = execute_with_response(api_request.post_request_script, response)
                        for _i, _sa in enumerate(script_result.get('assertions', [])):
                            _expected = _sa.get('expected')
                            if _expected is not None and isinstance(_expected, (dict, list)):
                                script_assertions.append({
                                    'type': 'mongo_match',
                                    'name': f'Tests断言 {_i + 1}',
                                    'expected': _expected,
                                })
                    except Exception as e:
                        logger.warning(f"后处理脚本执行失败: {str(e)}")

                # 提取认证信息（自动更新token）
                _extract_auth_info_from_response(response, auth_variables, token_type, session)

                # 准备断言列表（合并套件请求断言和请求自身断言）
                assertions_to_execute = []

                # 添加套件请求的断言
                if suite_request.assertions:
                    for assertion in suite_request.assertions:
                        assertion_copy = assertion.copy() if isinstance(assertion, dict) else {}
                        if assertion_copy.get('type') == 'response_time':
                            assertion_copy['actual_time'] = response_time
                        assertions_to_execute.append(assertion_copy)

                # 添加请求自身的断言（如果没有套件请求断言）
                if not suite_request.assertions and api_request.assertions:
                    for assertion in api_request.assertions:
                        assertion_copy = assertion.copy() if isinstance(assertion, dict) else {}
                        if assertion_copy.get('type') == 'response_time':
                            assertion_copy['actual_time'] = response_time
                        assertions_to_execute.append(assertion_copy)

                # 合并运行时变量（pre/post script 中赋值的、前序请求提取的变量）
                variables.update(resolver.runtime_variables)

                # 执行断言验证（含 Tests 中的 MongoDB 断言）
                assertions_results = execute_assertions(response, assertions_to_execute + script_assertions, variables=variables)

                # 检查是否通过（所有断言通过）
                passed = True
                error_message = ''

                for assertion_result in assertions_results:
                    if not assertion_result.get('passed', True):
                        passed = False
                        error_message = assertion_result.get('message', '断言失败')
                        break

                if passed:
                    passed_count += 1
                else:
                    failed_count += 1

                # 构建结果对象 - 确保包含完整的断言结果信息
                result_item = {
                    'request_id': api_request.id,
                    'name': api_request.name,
                    'method': api_request.method,
                    'url': url,
                    'status_code': response.status_code,
                    'response_time': response_time,
                    'passed': passed,
                    'error': error_message,
                    'assertions_results': assertions_results
                }
                results.append(result_item)

                # 准备响应JSON用于历史记录
                response_json = None
                try:
                    if response.headers.get('content-type', '').startswith('application/json'):
                        response_json = response.json()
                except:
                    pass

                # 保存请求历史
                RequestHistory.objects.create(
                    request=api_request,
                    environment=environment,
                    request_data={
                        'url': url,
                        'method': api_request.method,
                        'headers': _mask_sensitive_data(headers),
                        'params': _mask_sensitive_data(params),
                        'body': _mask_sensitive_data(body_data)
                    },
                    response_data={
                        'headers': dict(response.headers),
                        'body': response.text,
                        'json': response_json
                    },
                    status_code=response.status_code,
                    response_time=response_time,
                    assertions_results=assertions_results,
                    executed_by=executed_by
                )

            except Exception as e:
                failed_count += 1
                error_result = {
                    'request_id': api_request.id,
                    'name': api_request.name,
                    'method': api_request.method,
                    'url': api_request.url,
                    'passed': False,
                    'error': str(e),
                    'assertions_results': [{
                        'name': '执行错误',
                        'type': 'error',
                        'passed': False,
                        'message': f'请求执行失败: {str(e)}',
                        'expected': None,
                        'actual': None
                    }]
                }
                results.append(error_result)

        # 更新执行结果
        execution.end_time = timezone.now()
        execution.passed_requests = passed_count
        execution.failed_requests = failed_count
        execution.status = 'COMPLETED' if failed_count == 0 else 'FAILED'
        execution.results = results
        execution.save()

        return {
            'success': True,
            'execution_id': execution.id,
            'passed_count': passed_count,
            'failed_count': failed_count,
            'total_count': execution.total_requests,
            'results': results
        }

    except Exception as e:
        logger.error(f"执行测试套件失败: {str(e)}", exc_info=True)
        return {
            'success': False,
            'error': str(e)
        }


def _extract_auth_info_from_response(response, auth_variables, token_type, session):
    """从响应中提取认证信息（与TestSuiteViewSet中的方法一致）"""
    try:
        response_json = response.json()

        # 常见的token字段
        token_fields = [
            'access_token', 'token', 'accessToken',
            'jwt', 'auth_token', 'id_token', 'refresh_token'
        ]

        for field in token_fields:
            if field in response_json:
                auth_variables[field] = response_json[field]

                # 如果是access_token，也设置为token变量
                if field == 'access_token' and 'token' not in auth_variables:
                    auth_variables['token'] = response_json[field]

        # 提取token_type
        if 'token_type' in response_json:
            token_type = response_json['token_type']
            auth_variables['token_type'] = token_type

    except (ValueError, AttributeError):
        pass

    # 从响应头提取认证信息
    auth_header = response.headers.get('Authorization')
    if auth_header:
        if auth_header.startswith('Bearer '):
            auth_variables['token'] = auth_header.replace('Bearer ', '')
            auth_variables['token_type'] = 'Bearer'
        elif auth_header.startswith('Token '):
            auth_variables['token'] = auth_header.replace('Token ', '')
            auth_variables['token_type'] = 'Token'

    # 提取cookies
    if session.cookies:
        cookies_dict = session.cookies.get_dict()
        auth_variables.update(cookies_dict)
        if 'sessionid' in cookies_dict:
            auth_variables['session_id'] = cookies_dict['sessionid']


def _mask_sensitive_data(data):
    """脱敏敏感数据（与TestSuiteViewSet中的方法一致）"""
    if isinstance(data, dict):
        masked_data = {}
        sensitive_keys = ['password', 'token', 'secret', 'authorization', 'api_key']
        for key, value in data.items():
            if any(sensitive_key in key.lower() for sensitive_key in sensitive_keys):
                masked_data[key] = '***MASKED***'
            else:
                masked_data[key] = value
        return masked_data
    return data


def execute_api_request(api_request, environment, executed_by):
    """执行单个API请求并返回结果"""
    import requests
    import time

    try:
        # 创建变量解析器
        resolver = VariableResolver()

        # 解析环境变量
        variables = {}
        if environment:
            variables.update(environment.variables)

        # 替换URL中的变量
        url = _replace_variables(api_request.url, variables)
        url = resolver.resolve(url)

        # 准备请求头
        headers = {}
        if isinstance(api_request.headers, list):
            for header_item in api_request.headers:
                if header_item.get('enabled', True) and header_item.get('key'):
                    key = header_item['key']
                    value = _replace_variables(str(header_item.get('value', '')), variables)
                    value = resolver.resolve(value)
                    headers[key] = value
        else:
            headers = api_request.headers.copy()
            for key, value in headers.items():
                headers[key] = _replace_variables(str(value), variables)
                headers[key] = resolver.resolve(headers[key])

        # 准备请求参数
        params = api_request.params.copy() if api_request.params else {}
        for key, value in params.items():
            params[key] = _replace_variables(str(value), variables)
            params[key] = resolver.resolve(params[key])

        # 准备请求体
        body_data = None
        body_type = 'none'
        if api_request.body and api_request.method in ['POST', 'PUT', 'PATCH']:
            raw_body_type = api_request.body.get('type', 'raw')
            if raw_body_type == 'json':
                body_data = api_request.body.get('data', {})
                body_data = _replace_variables_in_dict(body_data, variables)
                body_data = _resolve_variables_in_dict(body_data, resolver)
                body_type = 'json'
            elif raw_body_type in ['x-www-form-urlencoded', 'form-data']:
                body_data = _prepare_form_data(api_request.body.get('data', {}), variables, resolver)
                body_type = raw_body_type

        # 根据 body 类型修正 Content-Type，防止用户配置的头与实际发送格式冲突
        if body_type == 'json':
            headers['Content-Type'] = 'application/json'
        elif body_type == 'x-www-form-urlencoded':
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        elif body_type == 'form-data':
            headers.pop('Content-Type', None)

        # 执行请求
        start_time = time.time()
        request_kwargs = {
            'method': api_request.method,
            'url': url,
            'headers': headers,
            'params': params,
            'timeout': 30
        }
        if body_type == 'json':
            request_kwargs['json'] = body_data
        else:
            request_kwargs['data'] = body_data
        response = requests.request(**request_kwargs)
        end_time = time.time()
        response_time = (end_time - start_time) * 1000

        # 准备断言
        assertions_to_execute = []
        if api_request.assertions:
            for assertion in api_request.assertions:
                assertion_copy = assertion.copy() if isinstance(assertion, dict) else {}
                if assertion_copy.get('type') == 'response_time':
                    assertion_copy['actual_time'] = response_time
                assertions_to_execute.append(assertion_copy)

        # 执行断言验证
        assertions_results = execute_assertions(response, assertions_to_execute, variables=variables)

        # 保存请求历史
        history = RequestHistory.objects.create(
            request=api_request,
            environment=environment,
            request_data={
                'url': url,
                'method': api_request.method,
                'headers': headers,
                'params': params,
                'body': body_data
            },
            response_data={
                'headers': dict(response.headers),
                'body': response.text,
                'json': response.json() if response.headers.get('content-type', '').startswith(
                    'application/json') else None
            },
            status_code=response.status_code,
            response_time=response_time,
            assertions_results=assertions_results,
            executed_by=executed_by
        )

        return {
            'success': True,
            'history_id': history.id,
            'status_code': response.status_code,
            'response_time': response_time,
            'assertions_results': assertions_results,
            'response_data': {
                'headers': dict(response.headers),
                'body': response.text,
                'json': response.json() if response.headers.get('content-type', '').startswith(
                    'application/json') else None
            }
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def _replace_variables(text, variables):
    """替换文本中的变量"""
    if not isinstance(text, str):
        return text

    result = text
    for key, value in (variables or {}).items():
        if isinstance(value, dict):
            replacement = str(value.get('currentValue', '') or value.get('initialValue', ''))
        else:
            replacement = str(value) if value is not None else ''
        result = result.replace(f'{{{{{key}}}}}', replacement)
    return result


def _replace_variables_in_dict(data, variables):
    """递归替换字典中的变量"""
    if isinstance(data, dict):
        return {k: _replace_variables_in_dict(v, variables) for k, v in data.items()}
    elif isinstance(data, list):
        return [_replace_variables_in_dict(item, variables) for item in data]
    elif isinstance(data, str):
        return _replace_variables(data, variables)
    else:
        return data


def _resolve_variables_in_dict(data, resolver):
    """递归解析字典中的动态函数占位符"""
    if isinstance(data, dict):
        return {k: _resolve_variables_in_dict(v, resolver) for k, v in data.items()}
    elif isinstance(data, list):
        return [_resolve_variables_in_dict(item, resolver) for item in data]
    elif isinstance(data, str):
        return resolver.resolve(data)
    else:
        return data


def _prepare_form_data(body_data, variables, resolver):
    """将表单数据（dict 或 key-value 列表）解析为 requests 可用的 dict"""
    if isinstance(body_data, dict):
        result = {}
        for key, value in body_data.items():
            resolved_key = resolver.resolve(_replace_variables(str(key), variables))
            resolved_value = resolver.resolve(_replace_variables(str(value), variables))
            result[resolved_key] = resolved_value
        return result
    elif isinstance(body_data, list):
        result = {}
        for item in body_data:
            if not isinstance(item, dict):
                continue
            if item.get('enabled', True) and item.get('key'):
                key = resolver.resolve(_replace_variables(str(item['key']), variables))
                value = resolver.resolve(_replace_variables(str(item.get('value', '')), variables))
                result[key] = value
        return result
    else:
        return resolver.resolve(_replace_variables(str(body_data), variables))