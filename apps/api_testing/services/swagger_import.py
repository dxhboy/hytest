"""Swagger/OpenAPI 规范解析与测试用例生成"""
import json


def _resolve_ref(spec, ref):
    """解析 $ref 引用，返回对应的 schema dict"""
    if not ref or not ref.startswith('#/'):
        return {}
    parts = ref.lstrip('#/').split('/')
    node = spec
    for part in parts:
        if not isinstance(node, dict):
            return {}
        node = node.get(part, {})
    return node or {}


def _get_sample_value(schema, spec, depth=0):
    """根据 JSON Schema 生成示例值，depth 防止循环引用"""
    if depth > 4 or not isinstance(schema, dict):
        return None
    if '$ref' in schema:
        schema = _resolve_ref(spec, schema['$ref'])
    if not schema:
        return None

    if 'enum' in schema:
        return schema['enum'][0]

    s_type = schema.get('type', 'string')
    fmt = schema.get('format', '')

    if s_type == 'integer':
        minimum = schema.get('minimum')
        return int(minimum) if minimum is not None else 1
    if s_type == 'number':
        minimum = schema.get('minimum')
        return float(minimum) if minimum is not None else 0.1
    if s_type == 'boolean':
        return True
    if s_type == 'array':
        item_val = _get_sample_value(schema.get('items', {}), spec, depth + 1)
        return [item_val] if item_val is not None else []
    if s_type == 'object':
        props = schema.get('properties', {})
        return {k: _get_sample_value(v, spec, depth + 1) for k, v in list(props.items())[:8]}

    # string
    if fmt == 'date':
        return '2024-01-01'
    if fmt == 'date-time':
        return '2024-01-01T00:00:00Z'
    if fmt == 'email':
        return 'test@example.com'
    if fmt in ('password', 'byte'):
        return 'Test@123456'
    if fmt == 'uuid':
        return '00000000-0000-0000-0000-000000000001'
    min_len = schema.get('minLength', 0)
    base = 'test'
    return base + 'x' * max(0, min_len - len(base))


def _build_body(operation, spec, is_v3, sample=True):
    """提取并构建请求 body，sample=True 时填入示例值"""
    if is_v3:
        rb = operation.get('requestBody', {})
        content = rb.get('content', {})
        if 'application/json' in content:
            body_schema = content['application/json'].get('schema', {})
            if '$ref' in body_schema:
                body_schema = _resolve_ref(spec, body_schema['$ref'])
            data = json.dumps(_get_sample_value(body_schema, spec) or {}, ensure_ascii=False, indent=2) if sample else '{}'
            return {'type': 'raw', 'rawType': 'json', 'data': data}, body_schema
        if 'multipart/form-data' in content:
            return {'type': 'form-data', 'data': []}, {}
        if 'application/x-www-form-urlencoded' in content:
            return {'type': 'x-www-form-urlencoded', 'data': []}, {}
    else:
        for param in operation.get('parameters', []):
            if param.get('in') == 'body':
                body_schema = param.get('schema', {})
                if '$ref' in body_schema:
                    body_schema = _resolve_ref(spec, body_schema['$ref'])
                data = json.dumps(_get_sample_value(body_schema, spec) or {}, ensure_ascii=False, indent=2) if sample else '{}'
                return {'type': 'raw', 'rawType': 'json', 'data': data}, body_schema
    return {}, {}


def _extract_params_meta(operation, path_item, spec, is_v3):
    """提取所有参数元信息（含 schema、是否必填）"""
    meta = []
    seen = set()
    all_params = list(path_item.get('parameters', [])) + list(operation.get('parameters', []))
    for param in all_params:
        if not isinstance(param, dict):
            continue
        if '$ref' in param:
            param = _resolve_ref(spec, param['$ref'])
        p_name = param.get('name', '')
        p_in = param.get('in', '')
        if not p_name or p_in == 'body' or (p_name, p_in) in seen:
            continue
        seen.add((p_name, p_in))
        schema = param.get('schema', {}) if is_v3 else {
            'type': param.get('type', 'string'),
            'format': param.get('format', ''),
            'enum': param.get('enum'),
            'minimum': param.get('minimum'),
            'maximum': param.get('maximum'),
            'minLength': param.get('minLength'),
            'maxLength': param.get('maxLength'),
            'default': param.get('default'),
        }
        if '$ref' in schema:
            schema = _resolve_ref(spec, schema['$ref'])
        meta.append({
            'name': p_name,
            'in': p_in,
            'required': param.get('required', p_in == 'path'),
            'description': param.get('description', ''),
            'schema': schema,
        })
    return meta


def _make_param_dict(params_meta, p_in, override=None, use_invalid_type=False):
    """把 params_meta 中指定 in 类型的参数转成 dict，override 可替换特定 key 的值"""
    result = {}
    override = override or {}
    for p in params_meta:
        if p['in'] != p_in:
            continue
        name = p['name']
        if name in override:
            result[name] = override[name]
        elif use_invalid_type and p['schema'].get('type') in ('integer', 'number'):
            result[name] = 'invalid_string'
        else:
            val = _get_sample_value(p['schema'], {})
            result[name] = str(val) if val is not None else ''
    return result


# 用例标签多语言映射（lang: 'zh' | 'en'）
CASE_LABELS = {
    'zh': {
        'normal': '正常',
        'missing_required': '异常-缺少必填',
        'boundary_exceed_max': '边界-超出最大值',
        'boundary_below_min': '边界-低于最小值',
        'boundary_exceed_maxlen': '边界-超出最大长度',
        'boundary_below_minlen': '边界-低于最小长度',
        'type_error': '异常-类型错误',
        'empty_body': '异常-空Body',
        'assert_ok': '状态码校验',
        'missing_desc': '必填参数置空: {params}',
        'exceed_max_desc': '{param} 超出最大值 {val}',
        'below_min_desc': '{param} 低于最小值 {val}',
        'exceed_maxlen_desc': '{param} 超出最大长度 {val}',
        'below_minlen_desc': '{param} 低于最小长度 {val}',
        'type_error_desc': '数值参数传入非法字符串: {params}',
        'empty_body_desc': '请求体为空',
    },
    'en': {
        'normal': 'Normal',
        'missing_required': 'Error-Missing Required',
        'boundary_exceed_max': 'Boundary-Exceed Max',
        'boundary_below_min': 'Boundary-Below Min',
        'boundary_exceed_maxlen': 'Boundary-Exceed MaxLength',
        'boundary_below_minlen': 'Boundary-Below MinLength',
        'type_error': 'Error-Type Mismatch',
        'empty_body': 'Error-Empty Body',
        'assert_ok': 'Status Code Check',
        'missing_desc': 'Required params set to empty: {params}',
        'exceed_max_desc': '{param} exceeds max {val}',
        'below_min_desc': '{param} below min {val}',
        'exceed_maxlen_desc': '{param} exceeds maxLength {val}',
        'below_minlen_desc': '{param} below minLength {val}',
        'type_error_desc': 'Numeric params passed invalid string: {params}',
        'empty_body_desc': 'Empty request body',
    },
}

# 用例分类与标签前缀的映射（用于 dry_run 中解析 case_category）
_LABEL_TO_CATEGORY = {
    'normal': 'normal',
    'missing_required': 'error',
    'boundary_exceed_max': 'boundary',
    'boundary_below_min': 'boundary',
    'boundary_exceed_maxlen': 'boundary',
    'boundary_below_minlen': 'boundary',
    'type_error': 'error',
    'empty_body': 'error',
}


def generate_test_cases(ep, spec, lang='zh'):
    """为单个 endpoint 生成正常、异常、边界值测试用例列表"""
    lb = CASE_LABELS.get(lang, CASE_LABELS['zh'])
    cases = []
    params_meta = ep['params_meta']
    method = ep['method']
    url = ep['url']
    tag = ep['tag']
    base_name = ep['name']
    desc = ep.get('description', '')
    normal_body = ep['body']
    empty_body = {'type': 'raw', 'rawType': 'json', 'data': '{}'} if normal_body.get('type') == 'raw' else {}

    required_query = [p for p in params_meta if p['in'] == 'query' and p['required']]
    required_header = [p for p in params_meta if p['in'] == 'header' and p['required']]
    numeric_params = [p for p in params_meta if p['schema'].get('type') in ('integer', 'number')]
    boundary_params = [p for p in params_meta if
                       p['schema'].get('maximum') is not None or p['schema'].get('minimum') is not None
                       or p['schema'].get('maxLength') is not None or p['schema'].get('minLength') is not None]

    normal_q = _make_param_dict(params_meta, 'query')
    normal_h = _make_param_dict(params_meta, 'header')

    def _case(label_key, name, description, query, headers, body, assertions):
        return {
            'tag': tag,
            'name': name,
            'description': description,
            'method': method,
            'url': url,
            'headers': headers,
            'params': query,
            'body': body,
            'assertions': assertions,
            'case_category': _LABEL_TO_CATEGORY.get(label_key, 'error'),
        }

    ok_assert = [{'name': lb['assert_ok'], 'type': 'status_code', 'operator': 'eq', 'expected': 200, 'enabled': True}]
    err_assert = [{'name': lb['assert_ok'], 'type': 'status_code', 'operator': 'gte', 'expected': 400, 'enabled': True}]

    # 1. 正常用例
    cases.append(_case('normal', f'[{lb["normal"]}] {base_name}', desc, normal_q, normal_h, normal_body, ok_assert))

    # 2. 缺少必填参数
    if required_query or required_header:
        miss_q = {k: '' for k in normal_q}
        miss_h = {k: '' for k in normal_h}
        req_names = [p['name'] for p in required_query + required_header]
        cases.append(_case(
            'missing_required',
            f'[{lb["missing_required"]}] {base_name}',
            lb['missing_desc'].format(params=', '.join(req_names[:4])),
            miss_q, miss_h, empty_body, err_assert
        ))

    # 3. 边界值（数值超出最大值 / 字符串超出最大长度）
    for p in boundary_params[:2]:
        schema = p['schema']
        p_in = p['in']
        p_name = p['name']
        if schema.get('maximum') is not None:
            over = schema['maximum'] + 1
            ov = {p_name: str(over)} if p_in == 'query' else {}
            oh = {p_name: str(over)} if p_in == 'header' else {}
            cases.append(_case(
                'boundary_exceed_max',
                f'[{lb["boundary_exceed_max"]}] {base_name} ({p_name}={over})',
                lb['exceed_max_desc'].format(param=p_name, val=schema['maximum']),
                {**normal_q, **ov}, {**normal_h, **oh}, normal_body, err_assert
            ))
        elif schema.get('minimum') is not None:
            under = schema['minimum'] - 1
            ov = {p_name: str(under)} if p_in == 'query' else {}
            oh = {p_name: str(under)} if p_in == 'header' else {}
            cases.append(_case(
                'boundary_below_min',
                f'[{lb["boundary_below_min"]}] {base_name} ({p_name}={under})',
                lb['below_min_desc'].format(param=p_name, val=schema['minimum']),
                {**normal_q, **ov}, {**normal_h, **oh}, normal_body, err_assert
            ))
        elif schema.get('maxLength') is not None:
            over_val = 'a' * (schema['maxLength'] + 1)
            ov = {p_name: over_val} if p_in == 'query' else {}
            cases.append(_case(
                'boundary_exceed_maxlen',
                f'[{lb["boundary_exceed_maxlen"]}] {base_name} ({p_name})',
                lb['exceed_maxlen_desc'].format(param=p_name, val=schema['maxLength']),
                {**normal_q, **ov}, normal_h, normal_body, err_assert
            ))
        elif schema.get('minLength') is not None and schema['minLength'] > 0:
            short_val = 'a' * max(0, schema['minLength'] - 1)
            ov = {p_name: short_val} if p_in == 'query' else {}
            cases.append(_case(
                'boundary_below_minlen',
                f'[{lb["boundary_below_minlen"]}] {base_name} ({p_name})',
                lb['below_minlen_desc'].format(param=p_name, val=schema['minLength']),
                {**normal_q, **ov}, normal_h, normal_body, err_assert
            ))

    # 4. 参数类型错误
    if numeric_params:
        type_err_q = _make_param_dict(params_meta, 'query', use_invalid_type=True)
        type_err_h = _make_param_dict(params_meta, 'header', use_invalid_type=True)
        err_names = [p['name'] for p in numeric_params[:3]]
        cases.append(_case(
            'type_error',
            f'[{lb["type_error"]}] {base_name}',
            lb['type_error_desc'].format(params=', '.join(err_names)),
            type_err_q, type_err_h, normal_body, err_assert
        ))

    # 5. 异常 body（有 body 的接口）
    if normal_body.get('type') == 'raw' and method in ('POST', 'PUT', 'PATCH'):
        cases.append(_case(
            'empty_body',
            f'[{lb["empty_body"]}] {base_name}',
            lb['empty_body_desc'],
            normal_q, normal_h, {'type': 'raw', 'rawType': 'json', 'data': '{}'}, err_assert
        ))

    return cases


def parse_swagger_spec(spec):
    """解析 Swagger 2.0 / OpenAPI 3.0 规范，返回 endpoint 元数据列表"""
    version = str(spec.get('openapi', spec.get('swagger', '2.0')))
    is_v3 = version.startswith('3')

    if is_v3:
        servers = spec.get('servers', [])
        base_url = (servers[0].get('url', '') if servers else '').rstrip('/')
    else:
        host = spec.get('host', '')
        base_path = spec.get('basePath', '/').rstrip('/')
        scheme = (spec.get('schemes') or ['http'])[0]
        base_url = f"{scheme}://{host}{base_path}" if host else base_path

    endpoints = []
    paths = spec.get('paths', {})
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue

            tags = operation.get('tags') or ['默认']
            tag = tags[0]
            name = (operation.get('summary') or operation.get('operationId') or
                    f'{method.upper()} {path}')
            description = operation.get('description', '')
            params_meta = _extract_params_meta(operation, path_item, spec, is_v3)
            body, _ = _build_body(operation, spec, is_v3, sample=True)

            endpoints.append({
                'tag': tag,
                'name': name,
                'description': description,
                'method': method.upper(),
                'url': base_url + path,
                'params_meta': params_meta,
                'body': body,
            })

    return endpoints, is_v3
