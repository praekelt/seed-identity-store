from rest_framework import viewsets, generics, mixins
from rest_framework.permissions import IsAuthenticated
from rest_hooks.models import Hook
from django.contrib.auth.models import User, Group
from .models import Identity, OptOut
from .serializers import (UserSerializer, GroupSerializer,
                          IdentitySerializer, OptOutSerializer, HookSerializer)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """ API endpoint that allows users to be viewed or edited.
    """
    permission_classes = (IsAuthenticated,)
    queryset = User.objects.all()
    serializer_class = UserSerializer


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    """ API endpoint that allows groups to be viewed or edited.
    """
    permission_classes = (IsAuthenticated,)
    queryset = Group.objects.all()
    serializer_class = GroupSerializer


class IdentityViewSet(viewsets.ModelViewSet):
    """ API endpoint that allows identities to be viewed or edited.
    """
    permission_classes = (IsAuthenticated,)
    queryset = Identity.objects.all()
    serializer_class = IdentitySerializer
    filter_fields = ('details',)

    # TODO make this work in test harness, works in production
    # def perform_create(self, serializer):
    #     serializer.save(created_by=self.request.user,
    #                     updated_by=self.request.user)
    #
    # def perform_update(self, serializer):
    #     serializer.save(updated_by=self.request.user)


class IdentitySearchList(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = IdentitySerializer

    def get_queryset(self):
        """
        This view should return a list of all the Identities
        for the supplied query parameters. The query parameters
        should be in the form:
        {"address_type": "address"}
        e.g.
        {"msisdn": "+27123"}
        {"email": "foo@bar.com"}
        """
        # query_field = list(self.request.query_params.keys())[0]
        filter_string = str(list(self.request.query_params.keys())[0])
        filter_value = self.request.query_params[filter_string]
        if filter_string.startswith("details__addresses__"):
            filter_string += "__has_key"
        data = Identity.objects.filter(**{filter_string: filter_value})
        return data


class OptOutViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """ API endpoint that allows users to be viewed or edited.
    """
    permission_classes = (IsAuthenticated,)
    queryset = OptOut.objects.all()
    serializer_class = OptOutSerializer


class HookViewSet(viewsets.ModelViewSet):
    """ Retrieve, create, update or destroy webhooks.
    """
    permission_classes = (IsAuthenticated,)
    queryset = Hook.objects.all()
    serializer_class = HookSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
