"""
录制功能序列化器。
"""
from rest_framework import serializers
from .models import RecordingSession, TestCase, TestCaseStep, Element


class StartRecordingSerializer(serializers.Serializer):
    """开始录制请求参数"""
    project_id = serializers.IntegerField(help_text='项目ID')
    target_url = serializers.URLField(help_text='录制目标URL')
    viewport_width = serializers.IntegerField(default=1280, required=False)
    viewport_height = serializers.IntegerField(default=720, required=False)


class RecordingSessionSerializer(serializers.ModelSerializer):
    """录制会话序列化"""
    class Meta:
        model = RecordingSession
        fields = [
            'id', 'project', 'test_case', 'target_url', 'status',
            'recorded_steps', 'match_results',
            'viewport_width', 'viewport_height',
            'created_by', 'created_at', 'finished_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at']


class ConfirmRecordingSerializer(serializers.Serializer):
    """确认录制请求参数"""
    test_case_name = serializers.CharField(max_length=200, help_text='测试用例名称')
    steps = serializers.ListField(
        child=serializers.DictField(),
        help_text='确认后的步骤列表（用户可能调整了顺序、删除了步骤、修改了元素关联）'
    )
