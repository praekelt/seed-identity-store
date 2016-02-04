from django.contrib.auth.models import User, Group
from rest_framework import serializers
from .models import Identity


class UserSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = ('url', 'username', 'email', 'groups')


class GroupSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Group
        fields = ('url', 'name')


class IdentitySerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Identity
        read_only_fields = ('created_by', 'updated_by', 'created_at',
                            'updated_at')
        fields = ('id', 'version', 'details',
                  'communicate_through', 'operator',
                  'created_at', 'created_by', 'updated_at', 'updated_by')
