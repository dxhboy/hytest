"""请求执行器 - 封装单个 HTTP 请求的准备与执行"""
import json
import time
import logging

import requests

from ..variable_resolver import VariableResolver

# 获取logger实例
logger = logging.getLogger(__name__)


class RequestExecutor:
    """请求执行器 - 封装请求执行逻辑"""

    def __init__(self, resolver=None):
        self.resolver = resolver or VariableResolver()
        self.session = requests.Session()

    def prepare_headers(self, headers, variables):
        """准备请求头"""
        result = {}
        if isinstance(headers, list):
            for header_item in headers:
                if header_item.get('enabled', True) and header_item.get('key'):
                    key = header_item['key']
                    value = self._replace_variables(str(header_item.get('value', '')), variables)
                    value = self.resolver.resolve(value)
                    result[key] = value
        else:
            headers_copy = headers.copy() if headers else {}
            for key, value in headers_copy.items():
                result[key] = self.resolver.resolve(self._replace_variables(str(value), variables))
        return result

    def prepare_params(self, params, variables):
        """准备请求参数"""
        result = {}
        if params:
            for key, value in params.items():
                result[key] = self.resolver.resolve(self._replace_variables(str(value), variables))
        return result

    def prepare_body(self, body, method, variables):
        """准备请求体"""
        logger.info(f"[DEBUG] prepare_body 原始输入: body={body}, method={method}")
        if not body or method not in ['POST', 'PUT', 'PATCH']:
            return None, 'none'

        if not isinstance(body, dict):
            return self.resolver.resolve(self._replace_variables(str(body), variables)), 'raw'

        body_type = body.get('type', 'raw')
        body_data = body.get('data', '')
        logger.info(f"[DEBUG] prepare_body 解析: body_type={body_type}, body_data={body_data}")

        if body_type == 'json':
            if isinstance(body_data, (dict, list)):
                body_data = self._replace_variables_in_dict(body_data, variables)
                body_data = self._resolve_variables_in_dict(body_data, self.resolver)
            else:
                body_str = self.resolver.resolve(self._replace_variables(str(body_data), variables))
                try:
                    body_data = json.loads(body_str)
                except json.JSONDecodeError:
                    body_data = body_str
            return body_data, body_type

        elif body_type in ['x-www-form-urlencoded', 'form-data']:
            return self._prepare_form_data(body_data, body_type, variables), body_type

        else:  # raw
            return self.resolver.resolve(self._replace_variables(str(body_data), variables)), body_type

    def _prepare_form_data(self, body_data, body_type, variables):
        """准备表单数据"""
        if isinstance(body_data, dict):
            result = {}
            for key, value in body_data.items():
                resolved_key = self.resolver.resolve(self._replace_variables(str(key), variables))
                resolved_value = self.resolver.resolve(self._replace_variables(str(value), variables))
                result[resolved_key] = resolved_value
            return result
        elif isinstance(body_data, list):
            result = {}
            for item in body_data:
                if item.get('enabled', True) and item.get('key'):
                    key = self.resolver.resolve(self._replace_variables(str(item['key']), variables))
                    value = self.resolver.resolve(self._replace_variables(str(item.get('value', '')), variables))
                    result[key] = value
            return result
        else:
            return self.resolver.resolve(self._replace_variables(str(body_data), variables))

    def execute(self, method, url, headers=None, params=None, body=None, body_type='none', timeout=30):
        """执行请求"""
        merged_headers = dict(headers or {})

        if body_type == 'json':
            # 强制 Content-Type 为 application/json，避免用户配置的 header 冲突
            merged_headers['Content-Type'] = 'application/json'
        elif body_type == 'x-www-form-urlencoded':
            # 强制 Content-Type 为 application/x-www-form-urlencoded，
            # 防止用户配置了 application/json 导致服务端解析失败（如 OAuth2 token 接口）
            merged_headers['Content-Type'] = 'application/x-www-form-urlencoded'
        elif body_type == 'form-data':
            # multipart/form-data 的 boundary 由 requests 自动生成，不能手动设置
            merged_headers.pop('Content-Type', None)

        request_kwargs = {
            'method': method,
            'url': url,
            'headers': merged_headers,
            'params': params or {},
            'timeout': timeout
        }

        if body_type == 'json':
            request_kwargs['json'] = body
        else:
            request_kwargs['data'] = body

        logger.info(f"[DEBUG] 执行请求: {method} {url} | body_type={body_type} | body={body} | headers={merged_headers}")
        start_time = time.time()
        response = self.session.request(**request_kwargs)
        end_time = time.time()

        return response, (end_time - start_time) * 1000

    # 代理方法，保持与BaseViewSetMixin的兼容
    def _replace_variables(self, text, variables):
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

    def _replace_variables_in_dict(self, data, variables):
        if isinstance(data, dict):
            return {k: self._replace_variables_in_dict(v, variables) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_variables_in_dict(item, variables) for item in data]
        elif isinstance(data, str):
            return self._replace_variables(data, variables)
        else:
            return data

    def _resolve_variables_in_dict(self, data, resolver):
        if isinstance(data, dict):
            return {k: self._resolve_variables_in_dict(v, resolver) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._resolve_variables_in_dict(item, resolver) for item in data]
        elif isinstance(data, str):
            return resolver.resolve(data)
        else:
            return data
