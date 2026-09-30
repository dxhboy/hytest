"""用户列表视图（项目成员选择）"""
from django.contrib.auth import get_user_model
from rest_framework import viewsets, filters
from rest_framework.permissions import IsAuthenticated

from ..serializers import UserSerializer

User = get_user_model()


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """用户列表接口，用于项目成员选择"""
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']
