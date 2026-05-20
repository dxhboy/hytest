"""
接口测试变量解析器（已废弃，请使用 apps.core.variable_resolver）
此文件保留用于向后兼容
"""
from apps.core.variable_resolver import VariableResolver, resolve_variables,parse_and_execute_script,execute_with_response

__all__ = ['VariableResolver', 'resolve_variables']
