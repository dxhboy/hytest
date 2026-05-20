import re
from typing import Any, Dict, List, Optional, Union, Callable, Set
import logging

logger = logging.getLogger(__name__)


class MongoDBComparator:
    """MongoDB风格比较器"""

    # 支持的操作符列表，添加$eq
    SUPPORTED_OPERATORS = {
        '$eq', '$lt', '$lte', '$gt', '$gte', '$ne',
        '$in', '$nin', '$exists', '$size', '$regex'
    }

    @staticmethod
    def get_supported_operators() -> List[str]:
        """获取支持的操作符列表"""
        return sorted(list(MongoDBComparator.SUPPORTED_OPERATORS))

    @staticmethod
    def _is_supported_operator(operator: str) -> bool:
        """检查操作符是否被支持"""
        return operator in MongoDBComparator.SUPPORTED_OPERATORS

    @staticmethod
    def _eq(actual: Any, expected: Any) -> bool:
        """等于比较 $eq"""
        return actual == expected

    @staticmethod
    def _lt(actual: Any, expected: Any) -> bool:
        """小于比较 $lt"""
        try:
            return actual < expected
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _lte(actual: Any, expected: Any) -> bool:
        """小于等于比较 $lte"""
        try:
            return actual <= expected
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _gt(actual: Any, expected: Any) -> bool:
        """大于比较 $gt"""
        try:
            return actual > expected
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _gte(actual: Any, expected: Any) -> bool:
        """大于等于比较 $gte"""
        try:
            return actual >= expected
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _ne(actual: Any, expected: Any) -> bool:
        """不等于比较 $ne"""
        return actual != expected

    @staticmethod
    def _in(actual: Any, expected: List) -> bool:
        """包含在列表中比较 $in"""
        return actual in expected

    @staticmethod
    def _nin(actual: Any, expected: List) -> bool:
        """不包含在列表中比较 $nin"""
        return actual not in expected

    @staticmethod
    def _exists(actual: Any, expected: bool) -> bool:
        """字段存在性比较 $exists"""
        # 如果expected为True，表示字段应该存在
        # 如果expected为False，表示字段不应该存在
        field_exists = actual is not None
        return field_exists == expected

    @staticmethod
    def _size(actual: Any, expected: int) -> bool:
        """数组大小比较 $size"""
        if isinstance(actual, (list, tuple, set)):
            return len(actual) == expected
        return False

    @staticmethod
    def _regex(actual: Any, expected: Union[str, dict]) -> bool:
        """正则表达式比较 $regex"""
        if not isinstance(actual, str):
            actual = str(actual)

        if isinstance(expected, dict):
            # 处理带选项的正则表达式
            pattern = expected.get('$regex', '')
            options = expected.get('$options', '')

            # 处理大小写不敏感选项
            flags = 0
            if 'i' in options:
                flags |= re.IGNORECASE
            if 'm' in options:
                flags |= re.MULTILINE

            return bool(re.search(pattern, actual, flags))
        else:
            # 直接的正则表达式字符串
            return bool(re.search(str(expected), actual))

    @staticmethod
    def compare_with_operator(actual: Any, operator_dict: Dict) -> Dict[str, Any]:
        """
        使用MongoDB操作符进行比较

        Args:
            actual: 实际值
            operator_dict: 包含操作符的字典

        Returns:
            包含匹配结果和详细信息的字典
        """
        results = []
        all_success = True
        unsupported_operators = []
        details = []

        for operator, expected_value in operator_dict.items():
            if not operator.startswith('$'):
                # 非操作符键，跳过
                continue

            if not MongoDBComparator._is_supported_operator(operator):
                unsupported_operators.append(operator)
                all_success = False
                details.append({
                    "operator": operator,
                    "supported": False,
                    "match": False,
                    "error": f"不支持的操作符: {operator}",
                    "actual": actual,
                    "expected": expected_value
                })
                continue

            is_match = False
            try:
                if operator == "$eq":
                    is_match = MongoDBComparator._eq(actual, expected_value)
                elif operator == "$lt":
                    is_match = MongoDBComparator._lt(actual, expected_value)
                elif operator == "$lte":
                    is_match = MongoDBComparator._lte(actual, expected_value)
                elif operator == "$gt":
                    is_match = MongoDBComparator._gt(actual, expected_value)
                elif operator == "$gte":
                    is_match = MongoDBComparator._gte(actual, expected_value)
                elif operator == "$ne":
                    is_match = MongoDBComparator._ne(actual, expected_value)
                elif operator == "$in":
                    is_match = MongoDBComparator._in(actual, expected_value)
                elif operator == "$nin":
                    is_match = MongoDBComparator._nin(actual, expected_value)
                elif operator == "$exists":
                    is_match = MongoDBComparator._exists(actual, expected_value)
                elif operator == "$size":
                    is_match = MongoDBComparator._size(actual, expected_value)
                elif operator == "$regex":
                    is_match = MongoDBComparator._regex(actual, expected_value)

                results.append(is_match)
                all_success = all_success and is_match

                details.append({
                    "operator": operator,
                    "expected": expected_value,
                    "actual": actual,
                    "match": is_match,
                    "supported": True
                })

            except Exception as e:
                all_success = False
                details.append({
                    "operator": operator,
                    "expected": expected_value,
                    "actual": actual,
                    "match": False,
                    "supported": True,
                    "error": f"执行操作符 {operator} 时出错: {str(e)}"
                })

        return {
            "success": all_success and len(unsupported_operators) == 0,
            "all_match": all(results) if results else False,
            "unsupported_operators": unsupported_operators,
            "details": details,
            "supported_operators": MongoDBComparator.get_supported_operators()
        }


class MongoDBAssert:
    """MongoDB风格断言类"""

    def __init__(self):
        self.comparator = MongoDBComparator()
        self.expected_items = []  # 存储所有expected匹配项信息
        self.expected_total = 0  # expected项总数

    def assert_mongo_match(self, actual: Any, expected: Any, path: str = "") -> Dict[str, Any]:
        """
        主入口函数：比较实际值和期望值，支持MongoDB查询语法

        Args:
            actual: 实际对象
            expected: 期望对象，可以包含MongoDB操作符
            path: 当前路径（用于错误信息）

        Returns:
            验证结果字典
        """
        try:
            # 重置数据
            self.expected_items = []
            self.expected_total = 0

            # 第一步：扫描expected结构，收集所有匹配项信息
            self._collect_expected_items(expected, path)

            # 第二步：进行实际匹配，同时统计成功/失败
            success_count = 0
            fail_count = 0
            failed_matches = []
            successful_matches = []
            all_success = True

            # 进行匹配并收集结果
            match_result = self._deep_match_with_stats(actual, expected, path,
                                                       successful_matches, failed_matches)

            # 统计成功和失败数量
            success_count = len(successful_matches)
            fail_count = len(failed_matches)
            self.expected_total = len(self.expected_items)  # 更新总数

            # 检查整体成功状态
            for item in self.expected_items:
                if not item.get("match", False):
                    all_success = False
                    break

            # 构建统一的返回结构
            result = {
                "success": match_result["success"] and all_success,
                "all_match": match_result.get("all_match", True) and all_success,
                "actual": actual,
                "expected": expected,
                "unsupported_operators": match_result.get("unsupported_operators", []),
                "supported_operators": self.comparator.get_supported_operators(),
                "failed_matches": failed_matches,
                "successful_matches": successful_matches,
                "total_matches": self.expected_total,
                "failed_count": fail_count,
                "successful_count": success_count,
                "details": match_result.get("details", [])
            }
            print("###################comp result#############################")
            print(result['success'])
            print(result['successful_matches'])
            print(result['failed_matches'])
            # 生成总结信息
            if result["success"]:
                result[
                    "message"] = f"MongoDB模式匹配验证通过（{result['successful_count']}/{result['total_matches']} 个匹配项成功）"
            else:
                failed_paths = [match.get("path", "unknown") for match in failed_matches]
                result[
                    "message"] = f"MongoDB模式匹配失败: {result['failed_count']} 个匹配项失败（失败的路径: {failed_paths}）"

            return result

        except Exception as e:
            return {
                "success": False,
                "message": f"MongoDB模式匹配异常: {str(e)}",
                "actual": actual,
                "expected": expected,
                "error": str(e),
                "supported_operators": self.comparator.get_supported_operators(),
                "failed_matches": [],
                "successful_matches": [],
                "total_matches": self.expected_total,
                "failed_count": 0,
                "successful_count": 0
            }

    def _collect_expected_items(self, expected: Any, path: str = ""):
        """收集expected结构中的所有匹配项信息"""
        if self._is_mongo_operator(expected):
            # 如果是操作符字典，统计每个操作符作为一个匹配项
            for key, value in expected.items():
                if key.startswith('$'):
                    self.expected_items.append({
                        "path": path,
                        "expected": value,
                        "operator": key,
                        "type": "operator"
                    })
        elif isinstance(expected, dict):
            # 递归统计字典中的匹配项
            for key, value in expected.items():
                current_path = f"{path}.{key}" if path else key
                self._collect_expected_items(value, current_path)
        elif isinstance(expected, list):
            # 对于列表，如果只有一个元素且是操作符字典，则按操作符统计
            if len(expected) == 1 and isinstance(expected[0], dict) and self._is_mongo_operator(expected[0]):
                for key, value in expected[0].items():
                    if key.startswith('$'):
                        self.expected_items.append({
                            "path": path,
                            "expected": value,
                            "operator": key,
                            "type": "list_operator"
                        })
            else:
                # 否则每个元素都可能包含匹配项
                for i, item in enumerate(expected):
                    current_path = f"{path}[{i}]"
                    self._collect_expected_items(item, current_path)
        elif expected is not None:
            # 基本类型（非None）作为一个匹配项
            self.expected_items.append({
                "path": path,
                "expected": expected,
                "operator": "$eq",  # 隐式的$eq操作符
                "type": "basic"
            })

    def _deep_match_with_stats(self, actual: Any, expected: Any, path: str,
                               successful_matches: List, failed_matches: List) -> Dict[str, Any]:
        """深度匹配函数，同时收集成功/失败信息"""
        # 检查是否包含MongoDB操作符
        if self._is_mongo_operator(expected):
            return self._match_with_operators_and_stats(actual, expected, path,
                                                        successful_matches, failed_matches)

        # 处理字典类型
        if isinstance(expected, dict) and isinstance(actual, dict):
            return self._match_dict_with_stats(actual, expected, path,
                                               successful_matches, failed_matches)

        # 处理列表类型
        elif isinstance(expected, list) and isinstance(actual, list):
            return self._match_list_with_stats(actual, expected, path,
                                               successful_matches, failed_matches)

        # 处理基本类型比较
        else:
            return self._match_basic_with_stats(actual, expected, path,
                                                successful_matches, failed_matches)

    def _match_with_operators_and_stats(self, actual: Any, operators: Dict, path: str,
                                        successful_matches: List, failed_matches: List) -> Dict[str, Any]:
        """使用MongoDB操作符进行匹配，并统计结果"""
        try:
            # 检查是否有不支持的操作符
            unsupported_ops = []
            for operator in operators.keys():
                if operator.startswith('$') and not self.comparator._is_supported_operator(operator):
                    unsupported_ops.append(operator)

            if unsupported_ops:
                # 对于不支持的操作符，都标记为失败
                for operator, expected_value in operators.items():
                    if operator.startswith('$'):
                        failed_matches.append({
                            "path": path,
                            "actual": actual,
                            "expected": expected_value,
                            "operator": operator,
                            "error": f"不支持的操作符: {operator}",
                            "detail": {
                                "path": path,
                                "error": f"不支持的操作符: {operator}",
                                "match": False,
                                "actual": actual,
                                "expected": expected_value
                            }
                        })

                return {
                    "success": False,
                    "all_match": False,
                    "message": f"发现不支持的操作符",
                    "unsupported_operators": unsupported_ops,
                    "supported_operators": self.comparator.get_supported_operators(),
                    "path": path,
                    "details": [{
                        "path": path,
                        "error": f"不支持的操作符: {unsupported_ops}",
                        "match": False,
                        "actual": actual,
                        "expected": operators,
                        "supported_operators": self.comparator.get_supported_operators()
                    }]
                }

            # 使用比较器进行匹配
            match_result = self.comparator.compare_with_operator(actual, operators)

            # 添加路径信息到详情中，并统计成功/失败
            for detail in match_result.get("details", []):
                detail["path"] = path

                # 统计成功和失败
                if detail.get("match", False):
                    successful_matches.append({
                        "path": path,
                        "actual": detail.get("actual"),
                        "expected": detail.get("expected"),
                        "operator": detail.get("operator"),
                        "detail": detail
                    })
                else:
                    failed_matches.append({
                        "path": path,
                        "actual": detail.get("actual"),
                        "expected": detail.get("expected"),
                        "operator": detail.get("operator"),
                        "error": detail.get("error", "匹配失败"),
                        "detail": detail
                    })

            result_dict = {
                "success": match_result["success"],
                "all_match": match_result.get("all_match", True),
                "details": match_result.get("details", []),
                "path": path,
                "unsupported_operators": match_result.get("unsupported_operators", []),
                "supported_operators": match_result.get("supported_operators", [])
            }

            if match_result["success"]:
                result_dict["message"] = "操作符匹配成功"
            else:
                # 生成详细的错误消息
                failed_ops = []
                for detail in match_result.get("details", []):
                    if not detail.get("match", True):
                        op = detail.get("operator", "unknown")
                        failed_ops.append(op)

                if failed_ops:
                    result_dict["message"] = f"操作符匹配失败: {failed_ops}"
                else:
                    result_dict["message"] = "操作符匹配失败"

            return result_dict

        except Exception as e:
            # 对于异常情况，所有操作符都标记为失败
            for operator, expected_value in operators.items():
                if operator.startswith('$'):
                    failed_matches.append({
                        "path": path,
                        "actual": actual,
                        "expected": expected_value,
                        "operator": operator,
                        "error": f"操作符匹配异常: {str(e)}",
                        "detail": {
                            "path": path,
                            "error": f"操作符匹配异常: {str(e)}",
                            "match": False,
                            "actual": actual,
                            "expected": expected_value
                        }
                    })

            return {
                "success": False,
                "all_match": False,
                "message": f"操作符匹配异常: {str(e)}",
                "path": path,
                "error": str(e),
                "details": [{
                    "path": path,
                    "error": f"操作符匹配异常: {str(e)}",
                    "match": False,
                    "actual": actual,
                    "expected": operators
                }],
                "supported_operators": self.comparator.get_supported_operators()
            }

    def _match_dict_with_stats(self, actual: Dict, expected: Dict, path: str,
                               successful_matches: List, failed_matches: List) -> Dict[str, Any]:
        """字典匹配，并统计结果"""
        details = []
        all_success = True
        unsupported_operators = []
        nested_results = []

        # 检查期望字典中的所有键
        for key, expected_value in expected.items():
            current_path = f"{path}.{key}" if path else key

            # 检查键是否存在
            if key not in actual:
                # 如果是$exists操作符的特殊情况
                if isinstance(expected_value, dict) and "$exists" in expected_value:
                    exists_expected = expected_value["$exists"]
                    match_result = self.comparator._exists(None, exists_expected)

                    detail = {
                        "path": current_path,
                        "operator": "$exists",
                        "expected": exists_expected,
                        "actual": False,
                        "match": match_result
                    }
                    details.append(detail)

                    # 统计成功/失败
                    if match_result:
                        successful_matches.append({
                            "path": current_path,
                            "actual": False,
                            "expected": exists_expected,
                            "operator": "$exists",
                            "detail": detail
                        })
                    else:
                        failed_matches.append({
                            "path": current_path,
                            "actual": False,
                            "expected": exists_expected,
                            "operator": "$exists",
                            "error": "字段存在性不匹配",
                            "detail": detail
                        })

                    all_success = all_success and match_result
                else:
                    detail = {
                        "path": current_path,
                        "error": f"键 '{key}' 不存在于实际对象中",
                        "match": False,
                        "actual": None,
                        "expected": expected_value
                    }
                    details.append(detail)

                    failed_matches.append({
                        "path": current_path,
                        "actual": None,
                        "expected": expected_value,
                        "error": f"键 '{key}' 不存在于实际对象中",
                        "detail": detail
                    })
                    all_success = False
                continue

            # 递归比较值
            match_result = self._deep_match_with_stats(actual[key], expected_value, current_path,
                                                       successful_matches, failed_matches)

            # 收集嵌套结果
            nested_results.append(match_result)

            # 收集详情
            if "details" in match_result:
                details.extend(match_result.get("details", []))

            # 收集不支持的操作符
            if match_result.get("unsupported_operators"):
                unsupported_operators.extend(match_result.get("unsupported_operators"))

            if not match_result.get("success", False):
                all_success = False

        return {
            "success": all_success and len(unsupported_operators) == 0,
            "all_match": all_success,
            "message": f"字典匹配 {'成功' if all_success else '失败'}",
            "details": details,
            "nested_results": nested_results,
            "path": path,
            "unsupported_operators": unsupported_operators,
            "supported_operators": self.comparator.get_supported_operators()
        }

    def _match_list_with_stats(self, actual: List, expected: List, path: str,
                               successful_matches: List, failed_matches: List) -> Dict[str, Any]:
        """列表匹配，并统计结果"""
        # 如果期望列表为空，检查实际列表是否也为空
        if len(expected) == 0:
            is_match = len(actual) == 0
            detail = {
                "path": path,
                "expected": "空列表",
                "actual": f"长度为 {len(actual)} 的列表",
                "match": is_match
            }

            if is_match:
                successful_matches.append({
                    "path": path,
                    "actual": actual,
                    "expected": "空列表",
                    "operator": "$eq",
                    "detail": detail
                })
            else:
                failed_matches.append({
                    "path": path,
                    "actual": f"长度为 {len(actual)} 的列表",
                    "expected": "空列表",
                    "error": "列表长度不匹配",
                    "detail": detail
                })

            return {
                "success": is_match,
                "all_match": is_match,
                "message": f"空列表匹配 {'成功' if is_match else '失败'}",
                "path": path,
                "details": [detail],
                "supported_operators": self.comparator.get_supported_operators()
            }

        # 如果期望列表中有操作符，特殊处理
        if len(expected) == 1 and isinstance(expected[0], dict) and self._is_mongo_operator(expected[0]):
            # 是数组操作符，如{"$size": 2}
            return self._deep_match_with_stats(actual, expected[0], path,
                                               successful_matches, failed_matches)

        # 普通列表比较 - 顺序敏感
        if len(actual) != len(expected):
            detail = {
                "path": path,
                "expected": f"长度为 {len(expected)} 的列表",
                "actual": f"长度为 {len(actual)} 的列表",
                "match": False
            }

            failed_matches.append({
                "path": path,
                "actual": f"长度为 {len(actual)} 的列表",
                "expected": f"长度为 {len(expected)} 的列表",
                "error": "列表长度不匹配",
                "detail": detail
            })

            return {
                "success": False,
                "all_match": False,
                "message": f"列表长度不匹配: 实际长度={len(actual)}, 期望长度={len(expected)}",
                "path": path,
                "details": [detail],
                "supported_operators": self.comparator.get_supported_operators()
            }

        details = []
        all_success = True
        unsupported_operators = []
        nested_results = []

        for i, (actual_item, expected_item) in enumerate(zip(actual, expected)):
            current_path = f"{path}[{i}]"
            match_result = self._deep_match_with_stats(actual_item, expected_item, current_path,
                                                       successful_matches, failed_matches)

            # 收集嵌套结果
            nested_results.append(match_result)

            # 收集详情
            if "details" in match_result:
                details.extend(match_result.get("details", []))

            # 收集不支持的操作符
            if match_result.get("unsupported_operators"):
                unsupported_operators.extend(match_result.get("unsupported_operators"))

            if not match_result.get("success", False):
                all_success = False

        return {
            "success": all_success and len(unsupported_operators) == 0,
            "all_match": all_success,
            "details": details,
            "nested_results": nested_results,
            "path": path,
            "unsupported_operators": unsupported_operators,
            "supported_operators": self.comparator.get_supported_operators()
        }

    def _match_basic_with_stats(self, actual: Any, expected: Any, path: str,
                                successful_matches: List, failed_matches: List) -> Dict[str, Any]:
        """基本类型匹配 - 直接相等比较"""
        is_match = actual == expected
        detail = {
            "path": path,
            "actual": actual,
            "expected": expected,
            "match": is_match,
            "operator": "$eq"  # 隐式的$eq操作符
        }

        if is_match:
            successful_matches.append({
                "path": path,
                "actual": actual,
                "expected": expected,
                "operator": "$eq",
                "detail": detail
            })
        else:
            failed_matches.append({
                "path": path,
                "actual": actual,
                "expected": expected,
                "operator": "$eq",
                "error": "值不相等",
                "detail": detail
            })

        return {
            "success": is_match,
            "all_match": is_match,
            "message": f"值匹配 {'成功' if is_match else '失败'}",
            "path": path,
            "details": [detail],
            "supported_operators": self.comparator.get_supported_operators()
        }

    # 保留原有的辅助方法
    def _is_mongo_operator(self, value: Any) -> bool:
        """检查值是否包含MongoDB操作符"""
        if isinstance(value, dict):
            # 检查是否有以$开头的键
            return any(isinstance(key, str) and key.startswith('$') for key in value.keys())
        return False

    def _find_unsupported_operators(self, data: Any, path: str = "") -> List[Dict[str, Any]]:
        """
        查找数据结构中不支持的操作符

        Args:
            data: 要检查的数据
            path: 当前路径

        Returns:
            不支持操作符的列表，每个元素包含操作符和路径
        """
        unsupported = []

        if isinstance(data, dict):
            # 检查当前字典是否包含操作符
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

                if isinstance(key, str) and key.startswith('$'):
                    # 这是一个操作符键
                    if not self.comparator._is_supported_operator(key):
                        unsupported.append({
                            "operator": key,
                            "path": current_path,
                            "value": value
                        })

                # 递归检查值
                if isinstance(value, (dict, list)):
                    unsupported.extend(self._find_unsupported_operators(value, current_path))

        elif isinstance(data, list):
            # 检查列表中的每个元素
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]"
                if isinstance(item, (dict, list)):
                    unsupported.extend(self._find_unsupported_operators(item, current_path))

        return unsupported


# 使用示例
def compare_mongo_style(actual: Any, expected: Any) -> Dict[str, Any]:
    """
    总入口函数：比较两个对象，支持MongoDB查询语法

    返回结构:
    {
        "success": bool,  # 整体是否成功（所有匹配都通过）
        "all_match": bool,  # 是否所有匹配都成功
        "actual": Any,  # 原始actual数据
        "expected": Any,  # 原始expected数据
        "failed_matches": List[Dict],  # 失败的匹配项列表
        "successful_matches": List[Dict],  # 成功的匹配项列表
        "total_matches": int,  # 总匹配项数（以expected为准）
        "failed_count": int,  # 失败匹配项数（以expected为准）
        "successful_count": int,  # 成功匹配项数（以expected为准）
        "message": str,  # 总结信息
        "unsupported_operators": List[str],  # 不支持的操作符列表
        "supported_operators": List[str],  # 支持的操作符列表
        "details": List[Dict]  # 详细信息
    }

    Args:
        actual: 实际对象
        expected: 期望对象，可以包含MongoDB操作符
        当expected没有操作符时，表示actual和expected应该相等

    Returns:
        比较结果字典
    """
    validator = MongoDBAssert()
    return validator.assert_mongo_match(actual, expected)


def get_supported_operators() -> List[str]:
    """
    获取当前支持的所有MongoDB操作符

    Returns:
        支持的操作符列表
    """
    return MongoDBComparator.get_supported_operators()


def validate_expected_structure(expected: Any) -> Dict[str, Any]:
    """
    验证期望结构中的操作符是否都被支持

    Args:
        expected: 期望对象

    Returns:
        验证结果
    """
    validator = MongoDBAssert()
    unsupported_list = validator._find_unsupported_operators(expected)

    # 提取操作符名称
    unsupported_operators = list(set([item["operator"] for item in unsupported_list]))

    return {
        "has_unsupported": len(unsupported_list) > 0,
        "unsupported_operators": unsupported_operators,
        "unsupported_details": unsupported_list,
        "supported_operators": get_supported_operators(),
        "message": f"发现 {len(unsupported_list)} 个不支持的操作符实例" if unsupported_list else "所有操作符都受支持"
    }


# 测试代码
if __name__ == "__main__":
    # 显示支持的操作符
    print("当前支持的操作符:")
    for op in get_supported_operators():
        print(f"  - {op}")

    print("\n" + "=" * 80 + "\n")

    actual = {'data': {'serverName': 'MT4_TEST_4', 'existsPendingApproval': False, 'name': 'TESTSZUSD16', 'source': 'GBPJPY', 'digits': 4, 'description': '', 'type': 0, 'exemode': 0, 'currency': 'TES', 'trade': 2, 'backgroundColor': 64636, 'hexColor': '#7CFC00', 'marginCurrency': 'TES', 'instantMaxVolume': 0, 'gtcPendings': 1, 'spread': 5, 'spreadBalance': 0, 'longOnly': 0, 'stopsLevel': 10, 'freezeLevel': 0, 'realTime': 1, 'logging': 0, 'filter': 20, 'filterLimit': 10, 'filterCounter': 3, 'quotesDelay': 0, 'filterSmoothing': 0, 'contractSize': 100000, 'marginInitial': 0, 'marginMaintenance': 0, 'marginHedged': 0, 'tickSize': 0, 'tickValue': 0, 'marginDivider': 100, 'marginMode': 0, 'profitMode': 0, 'marginHedgedStrong': 0, 'swapEnable': 1, 'swapType': 0, 'swapLong': 0, 'swapShort': 0, 'swapRollover3Days': 3, 'swapOpenPrice': 0, 'swapVariationMargin': 0, 'sessions': [{'quote': [{'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}], 'trade': [{'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}]}, {'quote': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}], 'trade': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}]}, {'quote': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}], 'trade': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}]}, {'quote': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}], 'trade': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}]}, {'quote': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}], 'trade': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}]}, {'quote': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}], 'trade': [{'openHour': 0, 'openMin': 0, 'closeHour': 24, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}]}, {'quote': [{'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}], 'trade': [{'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}, {'openHour': 0, 'openMin': 0, 'closeHour': 0, 'closeMin': 0}]}], 'starting': 1770651623, 'expiration': 1770738023}, 'code': '0', 'message': 'success'}

    # 测试用例1：完全匹配的情况
    expected1 = {'data': {'serverName': '{{serverName}}', 'name': {'$regex': 'TESTSZ.*16', '$options': 'i'}, 'source': 'GBPJPY', 'digits': 4, 'trade': {'$gt': 1, '$lt': 4}}, 'code': '0', 'message': 'success'}

    print("测试用例1：完全匹配的情况")
    result1 = compare_mongo_style(actual, expected1)
    print(f"整体结果: {'成功' if result1['success'] else '失败'}")
    print(f"消息: {result1['message']}")
    print(f"总匹配项数（以expected为准）: {result1['total_matches']}")
    print(f"成功数（以expected为准）: {result1['successful_count']}")
    print(f"失败数（以expected为准）: {result1['failed_count']}")

