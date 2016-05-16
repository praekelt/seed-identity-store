from rest_framework import viewsets, generics, mixins
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_hooks.models import Hook
from django.contrib.auth.models import User, Group
from .models import Identity, OptOut
from .serializers import (UserSerializer, GroupSerializer, AddressSerializer,
                          IdentitySerializer, OptOutSerializer, HookSerializer)
from seed_identity_store.utils import get_available_metrics
# from .tasks import scheduled_metrics


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
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user,
                        updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


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


class Address(object):
    def __init__(self, address):
        self.address = address


class IdentityAddresses(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = AddressSerializer

    def get_queryset(self):
        """
        This view should return a list of all the addresses the identity has
        for the supplied query parameters.
        Currently only supports address_type and default params
        Always excludes addresses with optedout = True
        """
        identity_id = self.kwargs['identity_id']
        address_type = self.kwargs['address_type']
        identity = Identity.objects.get(id=identity_id)
        response = []
        if "addresses" in identity.details:
            addresses = identity.details["addresses"]
            # remove all non matching addresses types
            for addr_type in addresses.keys():
                if addr_type != address_type:
                    addresses.pop(addr_type)
            # Ignore opted out addresses and make the response and apply
            # default filter if spec'd
            for address_type, entries in addresses.items():
                for address, metadata in entries.items():
                    if "optedout" in metadata and metadata["optedout"]:
                        break
                    if "default" in self.request.query_params:
                        # look for default
                        if len(entries.keys()) > 1:
                            # more than one address, look for default flag
                            if "default" in metadata and metadata["default"]:
                                response.append(Address(address=address))
                        else:
                            # if only one address its assumed default
                            response.append(Address(address=address))
                    else:
                        response.append(Address(address=address))
        return response


class OptOutViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """ API endpoint that allows optouts to be created.
    """
    permission_classes = (IsAuthenticated,)
    queryset = OptOut.objects.all()
    serializer_class = OptOutSerializer

    def perform_create(self, serializer):
        data = serializer.validated_data
        if "identity" not in data or data["identity"] is None:
            identities = Identity.objects.filter_by_addr(
                data["address_type"], data["address"])
            if len(identities) == 0:
                raise ValidationError(
                    'There is no identity with this address.')
            if len(identities) > 1:
                raise ValidationError(
                    'There are multiple identities with this address.')
            return serializer.save(created_by=self.request.user,
                                   identity=identities[0])
        return serializer.save(created_by=self.request.user)


class HookViewSet(viewsets.ModelViewSet):
    """ Retrieve, create, update or destroy webhooks.
    """
    permission_classes = (IsAuthenticated,)
    queryset = Hook.objects.all()
    serializer_class = HookSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class MetricsView(APIView):

    """ Metrics Interaction
        GET - returns list of all available metrics on the service
        POST - starts up the task that fires all the scheduled metrics
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        status = 200
        resp = {
            "metrics_available": get_available_metrics()
        }
        return Response(resp, status=status)

    def post(self, request, *args, **kwargs):
        status = 201
        # scheduled_metrics.apply_async()
        resp = {"scheduled_metrics_initiated": True}
        return Response(resp, status=status)
