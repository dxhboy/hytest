# -*- coding: utf-8 -*-
# -----------------------------
# @Author    : 影子
# @Time      : 2026/1/1 14:47
# @Software  : PyCharm
# @FileName  : fakerx.py
# -----------------------------
from faker import Faker
import re
import json
import csv
import uuid
import sqlite3
import yaml
import asyncio
from io import StringIO
from typing import Any, Dict, List, Union, Generator
from pydantic import BaseModel
from datetime import datetime, date


class FakerX(Faker):
    def __init__(self, locale='en_US', **kwargs):
        super().__init__(locale, **kwargs)

    def uuid4(self) -> str:
        """生成UUID4字符串"""
        return str(uuid.uuid4())

    def custom_url(self, domain: str = None) -> str:
        """生成自定义域名的URL"""
        if domain:
            return f"https://{domain}/{self.slug()}"
        return self.url()

    def validate_email(self, email: str) -> bool:
        """验证邮箱格式"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def set_seed(self, seed_value: int) -> None:
        """设置随机种子以便重现结果"""
        Faker.seed(seed_value)

    def _resolve_template(self, template: str) -> str:
        def replacer(match):
            method = match.group(1)
            if hasattr(self, method):
                return str(getattr(self, method)())
            else:
                return match.group(0)

        return re.sub(r'\{(\w+)\}', replacer, template)

    def _generate_from_schema(self, schema: Union[Dict, List, str, Any]) -> Any:
        if isinstance(schema, str):
            return self._resolve_template(schema)
        elif isinstance(schema, list):
            return [self._generate_from_schema(item) for item in schema]
        elif isinstance(schema, dict):
            if 'elements' in schema and len(schema) == 1:
                # Special case for random_element
                return self.random_element(schema['elements'])
            else:
                result = {}
                for key, value in schema.items():
                    result[key] = self._generate_from_schema(value)
                return result
        else:
            return schema

    def schema(self, schema_dict: Dict, iterations: int = 1, unique_fields: List[str] = None) -> List[Dict]:
        results = []
        unique_values = {field: set() for field in (unique_fields or [])}
        for _ in range(iterations):
            result = {}
            for key, value in schema_dict.items():
                if isinstance(value, str) and value.startswith('{') and value.endswith('}'):
                    # 处理模板字符串
                    method_name = value[1:-1]
                    if hasattr(self, method_name):
                        val = getattr(self, method_name)()
                        if key in unique_values:
                            while val in unique_values[key]:
                                val = getattr(self, method_name)()
                            unique_values[key].add(val)
                        result[key] = val
                    else:
                        result[key] = value
                elif callable(value):
                    # 直接调用可调用对象
                    result[key] = value()
                else:
                    # 递归处理嵌套结构
                    if isinstance(value, (dict, list)):
                        result[key] = self._generate_from_schema(value)
                    else:
                        result[key] = value
            results.append(result)
        return results

    def to_json(self, data: List[Dict]) -> str:
        """将数据列表转换为JSON字符串"""
        return json.dumps(data, ensure_ascii=False, indent=2)

    def to_csv(self, data: List[Dict], filename: str = None) -> str:
        """将数据列表转换为CSV字符串或保存到文件"""
        if not data:
            return ""
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
        csv_string = output.getvalue()
        if filename:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                f.write(csv_string)
            return f"Data saved to {filename}"
        return csv_string

    def stats(self, data: List[Dict]) -> Dict[str, Any]:
        """统计生成数据的统计信息"""
        if not data:
            return {}

        stats = {}
        for key in data[0].keys():
            values = [item[key] for item in data]
            if isinstance(values[0], (int, float)):
                stats[key] = {
                    'count': len(values),
                    'min': min(values),
                    'max': max(values),
                    'avg': sum(values) / len(values)
                }
            elif isinstance(values[0], str):
                stats[key] = {
                    'count': len(values),
                    'unique': len(set(values)),
                    'avg_length': sum(len(v) for v in values) / len(values)
                }
            else:
                stats[key] = {'count': len(values)}
        return stats

    def to_database(self, data: List[Dict], table_name: str, db_path: str = ':memory:',
                    if_exists: str = 'replace') -> None:
        """将数据插入到SQLite数据库"""
        conn = sqlite3.connect(db_path)
        try:
            if data:
                # 创建表
                columns = list(data[0].keys())
                column_defs = ', '.join([f'{col} TEXT' for col in columns])
                create_sql = f'CREATE TABLE {table_name} ({column_defs})'

                if if_exists == 'replace':
                    conn.execute(f'DROP TABLE IF EXISTS {table_name}')

                conn.execute(create_sql)

                # 插入数据
                placeholders = ', '.join(['?' for _ in columns])
                insert_sql = f'INSERT INTO {table_name} VALUES ({placeholders})'

                for row in data:
                    values = [str(row[col]) for col in columns]
                    conn.execute(insert_sql, values)

                conn.commit()
                print(f"成功插入 {len(data)} 条记录到表 {table_name}")
        finally:
            conn.close()

    def load_schema_from_file(self, file_path: str) -> Dict:
        """从JSON或YAML文件加载schema"""
        with open(file_path, 'r', encoding='utf-8') as f:
            if file_path.endswith('.yaml') or file_path.endswith('.yml'):
                return yaml.safe_load(f)
            else:
                return json.load(f)

    def generate_from_config(self, config_path: str) -> List[Dict]:
        """从配置文件生成数据"""
        config = self.load_schema_from_file(config_path)
        schema = config.get('schema', {})
        iterations = config.get('iterations', 1)
        unique_fields = config.get('unique_fields', [])
        return self.schema(schema, iterations, unique_fields)

    async def async_batch(self, method: str, iterations: int = 1, unique: bool = False) -> List[Any]:
        """异步批量生成数据"""
        loop = asyncio.get_event_loop()
        results = []
        seen = set() if unique else None

        for _ in range(iterations):
            # 在线程池中运行同步方法
            value = await loop.run_in_executor(None, getattr(self, method))
            if unique:
                while value in seen:
                    value = await loop.run_in_executor(None, getattr(self, method))
                seen.add(value)
            results.append(value)

        return results

    def nested_schema(self, schema_dict: Dict, iterations: int = 1, unique_fields: List[str] = None) -> List[Dict]:
        """生成嵌套结构的schema数据，支持更复杂的嵌套"""
        return self.schema(schema_dict, iterations, unique_fields)

    def generate_with_validation(self, method: str, validator: callable = None, max_retries: int = 10) -> Any:
        """生成数据并使用自定义验证器验证"""
        for _ in range(max_retries):
            value = getattr(self, method)()
            if validator is None or validator(value):
                return value
        raise ValueError(f"Failed to generate valid value for {method} after {max_retries} attempts")

    def pydantic(self, model: BaseModel, max_retries: int = 100) -> BaseModel:
        # Check Pydantic version
        try:
            # Pydantic v2
            fields = model.model_fields

            def get_type(field_info):
                return field_info.annotation
        except AttributeError:
            # Pydantic v1
            fields = model.__fields__

            def get_type(field_info):
                return field_info.type_

        for attempt in range(max_retries):
            data = {}
            for field_name, field_info in fields.items():
                method_name = field_name
                if hasattr(self, method_name):
                    data[field_name] = getattr(self, method_name)()
                else:
                    # Fallback to random data based on type
                    field_type = get_type(field_info)
                    if hasattr(field_type, '__origin__') and field_type.__origin__ is Union:
                        # Handle Union/Optional types
                        args = field_type.__args__
                        non_none_types = [t for t in args if t is not type(None)]
                        if non_none_types:
                            field_type = non_none_types[0]

                    if field_type == int:
                        data[field_name] = self.pyint()
                    elif field_type == str:
                        # Check for specific string field names like email
                        if 'email' in field_name.lower():
                            data[field_name] = self.email()
                        else:
                            data[field_name] = self.text(max_nb_chars=20)
                    elif field_type == float:
                        data[field_name] = self.pyfloat()
                    elif field_type == bool:
                        data[field_name] = self.pybool()
                    elif field_type == datetime:
                        data[field_name] = self.date_time()
                    elif field_type == date:
                        data[field_name] = self.date_object()
                    else:
                        data[field_name] = self.text(max_nb_chars=20)

            try:
                return model(**data)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Failed to create valid {model.__name__} after {max_retries} attempts") from e
                continue

    def batch(self, method: str, iterations: int = 1, unique: bool = False) -> Generator[Any, None, None]:
        if not hasattr(self, method):
            raise AttributeError(f"No such method: {method}")
        seen = set() if unique else None
        for _ in range(iterations):
            value = getattr(self, method)()
            if unique:
                while value in seen:
                    value = getattr(self, method)()
                seen.add(value)
            yield value

    def clean_address(self) -> str:
        """生成不带邮编的地址"""
        full_address = self.address()
        # 使用正则表达式移除末尾的邮编（通常是6位数字）
        cleaned = re.sub(r'\s*\d{6}\s*$', '', full_address).strip()
        return cleaned

    def random_date_between(self, start_date: str = '2000-01-01', end_date: str = '2023-12-31') -> str:
        """生成指定日期范围内的随机日期"""
        from datetime import datetime
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        random_date = self.date_time_between(start_date=start, end_date=end)
        return random_date.strftime('%Y-%m-%d')
