from rest_framework import serializers
from .models import AssistantSession, AssistantMessage


class AssistantMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantMessage
        fields = ['id', 'role', 'content', 'tool_name', 'tool_result', 'created_at']


class AssistantSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssistantSession
        fields = ['id', 'title', 'context_module', 'context_page',
                  'context_project_id', 'created_at', 'updated_at']


class SendMessageSerializer(serializers.Serializer):
    session_id = serializers.IntegerField(required=False, allow_null=True)
    message = serializers.CharField(max_length=4000)
    context = serializers.DictField(required=False, default=dict)
