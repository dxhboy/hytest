from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from apps.users.models import User
from apps.projects.models import Project
import json
import logging

logger = logging.getLogger(__name__)


class RequirementDocument(models.Model):
    """需求文档模型"""
    DOCUMENT_TYPE_CHOICES = [
        ('pdf', 'PDF文档'),
        ('docx', 'Word文档'),
        ('txt', '文本文档'),
        ('md', 'Markdown文档'),
    ]

    STATUS_CHOICES = [
        ('uploaded', '已上传'),
        ('analyzing', '分析中'),
        ('analyzed', '分析完成'),
        ('failed', '分析失败'),
    ]

    title = models.CharField(max_length=200, verbose_name='文档标题')
    file = models.FileField(upload_to='requirement_docs/%Y/%m/', verbose_name='文档文件')
    document_type = models.CharField(max_length=10, choices=DOCUMENT_TYPE_CHOICES, verbose_name='文档类型')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded', verbose_name='状态')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_documents',
                                    verbose_name='上传者')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='requirement_documents',
                                verbose_name='关联项目', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    file_size = models.PositiveIntegerField(verbose_name='文件大小(bytes)', null=True, blank=True)
    extracted_text = models.TextField(verbose_name='提取的文本内容', blank=True)

    class Meta:
        db_table = 'requirement_documents'
        verbose_name = '需求文档'
        verbose_name_plural = '需求文档'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"


class RequirementAnalysis(models.Model):
    """需求分析记录"""
    document = models.OneToOneField(RequirementDocument, on_delete=models.CASCADE, related_name='analysis',
                                    verbose_name='关联文档')
    analysis_report = models.TextField(verbose_name='分析报告', blank=True)
    requirements_count = models.PositiveIntegerField(verbose_name='需求数量', default=0)
    analysis_time = models.FloatField(verbose_name='分析耗时(秒)', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'requirement_analyses'
        verbose_name = '需求分析'
        verbose_name_plural = '需求分析'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.document.title} - 分析报告"


class BusinessRequirement(models.Model):
    """业务需求模型"""
    REQUIREMENT_TYPE_CHOICES = [
        ('functional', '功能需求'),
        ('performance', '性能需求'),
        ('security', '安全需求'),
        ('usability', '可用性需求'),
        ('interface', '接口需求'),
        ('other', '其他需求'),
    ]

    REQUIREMENT_LEVEL_CHOICES = [
        ('high', '高'),
        ('medium', '中'),
        ('low', '低'),
    ]

    analysis = models.ForeignKey(RequirementAnalysis, on_delete=models.CASCADE, related_name='requirements',
                                 verbose_name='关联分析')
    requirement_id = models.CharField(max_length=50, verbose_name='需求编号')
    requirement_name = models.CharField(max_length=200, verbose_name='需求名称')
    requirement_type = models.CharField(max_length=20, choices=REQUIREMENT_TYPE_CHOICES, verbose_name='需求类型')
    parent_requirement = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True,
                                           verbose_name='父级需求')
    module = models.CharField(max_length=100, verbose_name='所属模块')
    requirement_level = models.CharField(max_length=10, choices=REQUIREMENT_LEVEL_CHOICES, verbose_name='需求级别')
    reviewer = models.CharField(max_length=50, verbose_name='评审人', default='admin')
    estimated_hours = models.PositiveIntegerField(verbose_name='预计工时', default=8)
    description = models.TextField(verbose_name='需求描述')
    acceptance_criteria = models.TextField(verbose_name='验收标准')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'business_requirements'
        verbose_name = '业务需求'
        verbose_name_plural = '业务需求'
        ordering = ['-created_at']
        unique_together = ['analysis', 'requirement_id']

    def __str__(self):
        return f"{self.requirement_id} - {self.requirement_name}"


class GeneratedTestCase(models.Model):
    """生成的测试用例模型"""
    PRIORITY_CHOICES = [
        ('P0', '最高优先级'),
        ('P1', '高优先级'),
        ('P2', '中优先级'),
        ('P3', '低优先级'),
    ]

    STATUS_CHOICES = [
        ('generated', '已生成'),
        ('reviewing', '评审中'),
        ('reviewed', '已评审'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
        ('adopted', '已采纳'),
        ('discarded', '已弃用'),
    ]

    requirement = models.ForeignKey(BusinessRequirement, on_delete=models.CASCADE, related_name='test_cases',
                                    verbose_name='关联需求')
    case_id = models.CharField(max_length=50, verbose_name='用例编号')
    title = models.CharField(max_length=300, verbose_name='用例标题')
    priority = models.CharField(max_length=5, choices=PRIORITY_CHOICES, verbose_name='优先级')
    precondition = models.TextField(verbose_name='前置条件')
    test_steps = models.TextField(verbose_name='测试步骤')
    expected_result = models.TextField(verbose_name='预期结果')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='generated', verbose_name='状态')
    generated_by_ai = models.CharField(max_length=50, verbose_name='生成AI模型', default='AI-A')
    reviewed_by_ai = models.CharField(max_length=50, verbose_name='评审AI模型', null=True, blank=True)
    review_comments = models.TextField(verbose_name='评审意见', blank=True)
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'generated_test_cases'
        verbose_name = '生成的测试用例'
        verbose_name_plural = '生成的测试用例'
        ordering = ['-created_at']
        unique_together = ['requirement', 'case_id']

    def __str__(self):
        return f"{self.case_id} - {self.title[:50]}"


class AnalysisTask(models.Model):
    """分析任务模型"""
    TASK_TYPE_CHOICES = [
        ('requirement_analysis', '需求分析'),
        ('testcase_generation', '测试用例生成'),
        ('testcase_review', '测试用例评审'),
    ]

    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('running', '运行中'),
        ('completed', '已完成'),
        ('failed', '失败'),
    ]

    task_id = models.CharField(max_length=100, unique=True, verbose_name='任务ID')
    task_type = models.CharField(max_length=30, choices=TASK_TYPE_CHOICES, verbose_name='任务类型')
    document = models.ForeignKey(RequirementDocument, on_delete=models.CASCADE, related_name='tasks',
                                 verbose_name='关联文档')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    progress = models.PositiveIntegerField(default=0, verbose_name='进度百分比')
    result = models.JSONField(verbose_name='任务结果', null=True, blank=True)
    error_message = models.TextField(verbose_name='错误信息', blank=True)
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='开始时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')

    class Meta:
        db_table = 'analysis_tasks'
        verbose_name = '分析任务'
        verbose_name_plural = '分析任务'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.task_id} - {self.get_task_type_display()}"


class AIModelConfig(models.Model):
    """AI模型配置模型"""
    MODEL_CHOICES = [
        ('deepseek', 'DeepSeek'),
        ('qwen', '通义千问'),
        ('siliconflow', '硅基流动'),
        ('zhipu', '智谱'),
        ('anthropic_claude', 'Anthropic Claude'),
        ('bedrock_claude', 'AWS Bedrock Claude'),
        ('other', '其他'),
    ]

    ROLE_CHOICES = [
        ('writer', '测试用例编写专家'),
        ('reviewer', '测试评审专家'),
        ('browser_use_text', 'Browser Use - 文本模式'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称')
    model_type = models.CharField(max_length=20, choices=MODEL_CHOICES, verbose_name='模型类型')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, verbose_name='角色')
    api_key = models.CharField(max_length=200, verbose_name='API Key', blank=True, null=True)
    base_url = models.CharField(max_length=500, verbose_name='API Base URL', blank=True, null=True)
    model_name = models.CharField(max_length=100, verbose_name='模型名称', blank=True, null=True)
    max_tokens = models.IntegerField(default=4096, verbose_name='最大Token数')
    temperature = models.FloatField(default=0.7, verbose_name='温度参数')
    top_p = models.FloatField(default=0.9, verbose_name='Top P参数')
    aws_access_key_id = models.CharField(max_length=255, verbose_name='AWS Access Key ID', blank=True, null=True)
    aws_secret_access_key = models.CharField(max_length=255, verbose_name='AWS Secret Access Key', blank=True, null=True)
    aws_region = models.CharField(max_length=50, verbose_name='AWS Region', default='us-east-1', blank=True, null=True)
    aws_model_id = models.CharField(max_length=100, verbose_name='Bedrock Model ID', blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'ai_model_config'
        verbose_name = 'AI模型配置'
        verbose_name_plural = 'AI模型配置'
        # 移除 unique_together 约束，允许同一个 role 有多个配置
        # 在应用层面通过代码控制：每个 role 只能有一个 is_active=True 的配置

    def __str__(self):
        return f"{self.get_model_type_display()} - {self.get_role_display()}"

    @classmethod
    def get_active_config(cls, model_type: str, role: str):
        """获取活跃的配置"""
        return cls.objects.filter(
            model_type=model_type,
            role=role,
            is_active=True
        ).first()


class PromptConfig(models.Model):
    """提示词配置模型"""
    PROMPT_CHOICES = [
        ('writer', '用例编写提示词'),
        ('reviewer', '用例评审提示词'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称')
    prompt_type = models.CharField(max_length=20, choices=PROMPT_CHOICES, verbose_name='提示词类型')
    content = models.TextField(verbose_name='提示词内容')
    project = models.ForeignKey(
        'projects.Project', on_delete=models.CASCADE,
        null=True, blank=True, verbose_name='所属项目',
        help_text='为空则为全局配置，有项目则优先于全局配置生效'
    )
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'prompt_config'
        verbose_name = '提示词配置'
        verbose_name_plural = '提示词配置'

    def __str__(self):
        return f"{self.get_prompt_type_display()} - {self.name}"

    @classmethod
    def get_active_config(cls, prompt_type: str, project_id: int = None):
        """获取活跃的提示词配置。有 project_id 时优先取项目级，fallback 全局。"""
        if project_id:
            project_config = cls.objects.filter(
                prompt_type=prompt_type,
                is_active=True,
                project_id=project_id,
            ).first()
            if project_config:
                return project_config
        return cls.objects.filter(
            prompt_type=prompt_type,
            is_active=True,
            project__isnull=True,
        ).first()


class GenerationConfig(models.Model):
    """生成行为配置模型"""
    OUTPUT_MODE_CHOICES = [
        ('stream', '实时流式输出'),
        ('complete', '完整输出'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称', default='默认生成配置')
    default_output_mode = models.CharField(
        max_length=10,
        choices=OUTPUT_MODE_CHOICES,
        default='stream',
        verbose_name='默认输出模式',
        help_text='测试用例生成的默认输出方式'
    )

    # 扩展配置字段
    enable_auto_review = models.BooleanField(
        default=True,
        verbose_name='启用AI评审和改进',
        help_text='生成完成后自动进行AI评审，并根据评审意见改进测试用例'
    )
    review_timeout = models.IntegerField(
        default=120,
        verbose_name='评审和改进超时时间（秒）',
        help_text='AI评审和改进的最大等待时间（总时长）'
    )

    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'generation_config'
        verbose_name = '生成行为配置'
        verbose_name_plural = '生成行为配置'

    def __str__(self):
        return self.name

    @classmethod
    def get_active_config(cls):
        """获取活跃的生成配置"""
        return cls.objects.filter(is_active=True).first()


class TestCaseGenerationTask(models.Model):
    """测试用例生成任务模型"""
    STATUS_CHOICES = [
        ('pending', '等待中'),
        ('generating', '生成中'),
        ('reviewing', '评审中'),
        ('revising', '改进中'),
        ('completed', '已完成'),
        ('failed', '失败'),
        ('cancelled', '已取消'),
    ]

    OUTPUT_MODE_CHOICES = [
        ('stream', '实时流式输出'),
        ('complete', '完整输出'),
    ]

    task_id = models.CharField(max_length=50, unique=True, verbose_name='任务ID')
    title = models.CharField(max_length=200, verbose_name='任务标题')
    requirement_text = models.TextField(verbose_name='需求描述')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    progress = models.IntegerField(default=0, verbose_name='进度百分比')

    # 流式输出配置
    output_mode = models.CharField(
        max_length=10,
        choices=OUTPUT_MODE_CHOICES,
        default='stream',
        verbose_name='输出模式'
    )

    # 流式缓冲区和状态跟踪
    stream_buffer = models.TextField(blank=True, verbose_name='流式输出缓冲区')
    stream_position = models.IntegerField(default=0, verbose_name='流式输出位置')
    last_stream_update = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后流式更新时间'
    )

    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generation_tasks',
        verbose_name='关联项目'
    )

    # 配置参数
    writer_model_config = models.ForeignKey(
        AIModelConfig, on_delete=models.SET_NULL, null=True,
        related_name='writer_tasks', verbose_name='编写模型配置'
    )
    reviewer_model_config = models.ForeignKey(
        AIModelConfig, on_delete=models.SET_NULL, null=True,
        related_name='reviewer_tasks', verbose_name='评审模型配置'
    )
    writer_prompt_config = models.ForeignKey(
        PromptConfig, on_delete=models.SET_NULL, null=True,
        related_name='writer_tasks', verbose_name='编写提示词配置'
    )
    reviewer_prompt_config = models.ForeignKey(
        PromptConfig, on_delete=models.SET_NULL, null=True,
        related_name='reviewer_tasks', verbose_name='评审提示词配置'
    )

    # 生成结果
    generated_test_cases = models.TextField(blank=True, verbose_name='生成的测试用例')
    review_feedback = models.TextField(blank=True, verbose_name='评审反馈')
    final_test_cases = models.TextField(blank=True, verbose_name='最终测试用例')

    # 元数据
    generation_log = models.TextField(blank=True, verbose_name='生成日志')
    error_message = models.TextField(blank=True, verbose_name='错误信息')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='完成时间')
    is_saved_to_records = models.BooleanField(default=False, verbose_name='是否已保存到记录')
    saved_at = models.DateTimeField(null=True, blank=True, verbose_name='保存到记录时间')

    class Meta:
        db_table = 'testcase_generation_task'
        verbose_name = '测试用例生成任务'
        verbose_name_plural = '测试用例生成任务'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.get_status_display()}"


class ScheduledGenerationTask(models.Model):
    """定时用例生成任务"""
    STATUS_CHOICES = [
        ('pending', '待执行'),
        ('running', '执行中'),
        ('success', '成功'),
        ('failed', '失败'),
    ]

    name = models.CharField(max_length=100, verbose_name='任务名称')
    requirement_document = models.ForeignKey(
        RequirementDocument, on_delete=models.CASCADE,
        related_name='scheduled_generation_tasks', verbose_name='需求文档'
    )
    ai_model_config = models.ForeignKey(
        AIModelConfig, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scheduled_tasks', verbose_name='AI模型配置'
    )
    scheduled_time = models.TimeField(verbose_name='每日执行时间（HH:MM）')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    last_run_at = models.DateTimeField(null=True, blank=True, verbose_name='最近执行时间')
    last_run_status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='最近执行状态'
    )
    last_run_task = models.ForeignKey(
        TestCaseGenerationTask, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='scheduled_source', verbose_name='最近生成任务'
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name='创建人'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'scheduled_generation_task'
        verbose_name = '定时用例生成任务'
        verbose_name_plural = '定时用例生成任务'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} @ {self.scheduled_time}"


class JiraIssueLink(models.Model):
    """记录已导入的 Jira Issue 及其与 TestHub 版本的关联"""
    issue_key        = models.CharField(max_length=64, verbose_name='Issue Key')
    issue_url        = models.URLField(verbose_name='Issue URL')
    issue_summary    = models.CharField(max_length=500, verbose_name='Issue 标题')
    jira_domain      = models.CharField(max_length=255, verbose_name='Jira 域名')
    jira_fix_version = models.CharField(max_length=255, blank=True, default='',
                                        verbose_name='Jira Fix Version')
    version          = models.ForeignKey('versions.Version', null=True, blank=True,
                                         on_delete=models.SET_NULL,
                                         related_name='jira_issue_links',
                                         verbose_name='关联版本')
    project          = models.ForeignKey('projects.Project', null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name='jira_issue_links',
                                          verbose_name='关联项目')
    created_by       = models.ForeignKey(User, null=True,
                                          on_delete=models.SET_NULL,
                                          related_name='created_jira_links')
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('issue_key', 'jira_domain')
        verbose_name = 'Jira Issue 关联'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.issue_key}: {self.issue_summary[:50]}'


class JiraIssueCaseLink(models.Model):
    """用例与 Jira Issue 的关联（支持 AI 生成用例和手工用例）"""
    LINK_AUTO   = 'auto'
    LINK_MANUAL = 'manual'
    LINK_CHOICES = [(LINK_AUTO, '自动关联'), (LINK_MANUAL, '手动关联')]

    jira_issue   = models.ForeignKey(JiraIssueLink, on_delete=models.CASCADE,
                                      related_name='case_links')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id    = models.PositiveIntegerField()
    case         = GenericForeignKey('content_type', 'object_id')
    link_type    = models.CharField(max_length=16, choices=LINK_CHOICES,
                                     default=LINK_MANUAL)
    created_by   = models.ForeignKey(User, null=True,
                                      on_delete=models.SET_NULL,
                                      related_name='created_case_links')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('jira_issue', 'content_type', 'object_id')
        verbose_name = 'Jira Issue 用例关联'
        ordering = ['-created_at']


class KnowledgeDocument(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_INDEXED = 'indexed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, '待处理'),
        (STATUS_PROCESSING, '处理中'),
        (STATUS_INDEXED, '已索引'),
        (STATUS_FAILED, '失败'),
    ]

    project = models.ForeignKey(
        'projects.Project', on_delete=models.CASCADE,
        related_name='knowledge_docs', verbose_name='所属项目'
    )
    name = models.CharField(max_length=255, verbose_name='文件名')
    file = models.FileField(upload_to='knowledge/%Y/%m/', verbose_name='文件')
    file_size = models.PositiveIntegerField(default=0, verbose_name='文件大小(字节)')
    content_text = models.TextField(blank=True, verbose_name='全文内容')
    chunks = models.JSONField(default=list, verbose_name='段落列表')
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES,
        default=STATUS_PENDING, verbose_name='状态'
    )
    error_msg = models.TextField(blank=True, verbose_name='错误信息')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='knowledge_docs', verbose_name='上传者'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='上传时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='最后修改时间')

    class Meta:
        ordering = ['-created_at']
        verbose_name = '知识库文档'
        verbose_name_plural = '知识库文档'

    def __str__(self):
        return self.name

    @classmethod
    def search(cls, query: str, project_id: int, top_k: int = 3) -> list:
        """BM25 全文检索，返回最相关的 top_k 个文档片段。"""
        if not query or not query.strip():
            return []
        try:
            docs = list(
                cls.objects.filter(
                    project_id=project_id,
                    status=cls.STATUS_INDEXED
                ).extra(
                    where=["MATCH(content_text) AGAINST (%s IN BOOLEAN MODE)"],
                    params=[query[:200]],
                    select={'relevance': "MATCH(content_text) AGAINST (%s IN BOOLEAN MODE)"},
                    select_params=[query[:200]],
                ).order_by('-relevance')[:top_k]
            )
            results = []
            for doc in docs:
                if doc.chunks:
                    results.append("\n".join(str(c) for c in doc.chunks[:3]))
                elif doc.content_text:
                    results.append(doc.content_text[:500])
            return results
        except Exception as e:
            logger.warning("KnowledgeDocument.search failed: %s", e)
            return []


class ProjectSkill(models.Model):
    project = models.OneToOneField(
        'projects.Project', on_delete=models.CASCADE,
        related_name='skill', verbose_name='所属项目'
    )
    content = models.TextField(blank=True, verbose_name='Skills 内容(Markdown)')
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='project_skills', verbose_name='最后修改者'
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='最后修改时间')

    class Meta:
        verbose_name = '项目 Skills'
        verbose_name_plural = '项目 Skills'

    def __str__(self):
        return f"{self.project} Skills"


def __getattr__(name):
    """惰性转发：AIModelService 已迁至 ai_service.py，避免循环导入"""
    if name == 'AIModelService':
        from .ai_service import AIModelService
        return AIModelService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
