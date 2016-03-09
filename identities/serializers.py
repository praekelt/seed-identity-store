from django.contrib.auth.models import User, Group
from rest_framework import serializers
from rest_hooks.models import Hook
from .models import Identity, OptOut


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


class OptOutSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = OptOut
        fields = ('id', 'identity', 'address_type', 'address',
                  'request_source', 'requestor_source_id', 'created_at')
        read_only_fields = ('created_by')


class HookSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hook
        read_only_fields = ('user',)
