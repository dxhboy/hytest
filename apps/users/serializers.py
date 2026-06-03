from rest_framework import serializers
from django.contrib.auth import authenticate
from django.conf import settings
from cryptography.fernet import Fernet
from .models import User, UserProfile


def _get_fernet():
    return Fernet(settings.JIRA_TOKEN_ENCRYPT_KEY)

class UserSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'avatar')

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 
                 'avatar', 'phone', 'department', 'position', 'is_active',
                 'date_joined', 'created_at', 'updated_at']
        read_only_fields = ['id', 'date_joined', 'created_at', 'updated_at']

class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password_confirm',
                 'first_name', 'last_name', 'phone', 'department', 'position']
    
    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError("密码不一致")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        user = User.objects.create_user(**validated_data)
        return user

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
    
    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')
        
        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError('用户名或密码错误')
            if not user.is_active:
                raise serializers.ValidationError('用户已被禁用')
        else:
            raise serializers.ValidationError('用户名和密码不能为空')
        
        attrs['user'] = user
        return attrs

class UserProfileSerializer(serializers.ModelSerializer):
    # 只读，返回脱敏值
    jira_api_token = serializers.SerializerMethodField()
    # 只写，接收明文 token
    jira_api_token_input = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = UserProfile
        fields = ['theme', 'language', 'timezone', 'notifications',
                  'jira_domain', 'jira_email', 'jira_api_token', 'jira_api_token_input']

    def get_jira_api_token(self, obj):
        return '***' if obj.jira_api_token else ''

    def update(self, instance, validated_data):
        token_input = validated_data.pop('jira_api_token_input', None)
        if token_input:  # 非空才加密覆盖
            f = _get_fernet()
            instance.jira_api_token = f.encrypt(token_input.encode()).decode()
        return super().update(instance, validated_data)