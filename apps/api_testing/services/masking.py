"""请求数据敏感字段脱敏"""


_SENSITIVE_KEYS = frozenset([
    'password', 'passwd', 'pwd', 'secret', 'token', 'authorization',
    'auth', 'api_key', 'apikey', 'access_token', 'refresh_token',
    'private_key', 'secret_key', 'client_secret',
])


def _mask_sensitive_data(data):
    """递归地将敏感字段值替换为 '******'"""
    if isinstance(data, dict):
        return {
            k: '******' if k.lower() in _SENSITIVE_KEYS else _mask_sensitive_data(v)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_mask_sensitive_data(item) for item in data]
    return data
