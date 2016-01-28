from rest_framework import viewsets, generics
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User, Group
from .models import Identity
from .serializers import (UserSerializer, GroupSerializer,
                          IdentitySerializer)


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
        for the supplied msisdn
        """
        contains = {
            "addresses": "msisdn:%s" % self.request.query_params["msisdn"]
        }
        data = Identity.objects.filter(details__contains=contains)
        return data
