from rest_framework import serializers
from .models import JiraIssueLink

ALLOWED_FIELDS = ['summary', 'description', 'acceptance_criteria', 'subtasks', 'labels', 'priority']


class JiraPreviewRequestSerializer(serializers.Serializer):
    urls = serializers.ListField(
        child=serializers.CharField(), min_length=1, max_length=50
    )
    selected_fields = serializers.ListField(
        child=serializers.ChoiceField(choices=ALLOWED_FIELDS),
        default=['summary', 'description']
    )


class JiraImportRequestSerializer(serializers.Serializer):
    urls = serializers.ListField(
        child=serializers.CharField(), min_length=1, max_length=50
    )
    selected_fields = serializers.ListField(
        child=serializers.ChoiceField(choices=ALLOWED_FIELDS),
        default=['summary', 'description']
    )
    version_id = serializers.IntegerField(required=False, allow_null=True)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    writer_model_config_id = serializers.IntegerField(required=False, allow_null=True)
    reviewer_model_config_id = serializers.IntegerField(required=False, allow_null=True)
    expand_epic = serializers.BooleanField(default=False)


class JiraIssueLinkSerializer(serializers.ModelSerializer):
    case_count = serializers.SerializerMethodField()
    version_name = serializers.CharField(source='version.name', read_only=True, default='')

    class Meta:
        model = JiraIssueLink
        fields = ['id', 'issue_key', 'issue_url', 'issue_summary',
                  'jira_fix_version', 'version', 'version_name',
                  'project', 'created_by', 'created_at', 'case_count']
        read_only_fields = ['id', 'created_by', 'created_at']

    def get_case_count(self, obj):
        return obj.case_links.count()


class LinkCaseRequestSerializer(serializers.Serializer):
    case_type = serializers.ChoiceField(choices=['generated', 'manual'])
    case_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)


class JiraRecommendRequestSerializer(serializers.Serializer):
    version_id = serializers.IntegerField()
