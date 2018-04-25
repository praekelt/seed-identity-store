from rest_framework import viewsets, generics, mixins, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.pagination import CursorPagination, LimitOffsetPagination
from rest_framework import filters
from rest_hooks.models import Hook
from rest_hooks.signals import raw_hook_event
from django.conf import settings
from django.contrib.auth.models import User, Group
from django.core.exceptions import FieldError
from django.db.models.expressions import F
from .models import Identity, OptOut, OptIn, DetailKey
from .serializers import (UserSerializer, GroupSerializer, AddressSerializer,
                          IdentitySerializer, OptOutSerializer, HookSerializer,
                          CreateUserSerializer, OptInSerializer)
from seed_identity_store.utils import get_available_metrics
from .tasks import scheduled_metrics
import django_filters


class CreatedAtCursorPagination(CursorPagination):
    ordering = "-created_at"


class IdCursorPagination(CursorPagination):
    ordering = "-id"


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """ API endpoint that allows users to be viewed or edited.
    """
    permission_classes = (IsAuthenticated,)
    queryset = User.objects.all()
    serializer_class = UserSerializer
    pagination_class = IdCursorPagination


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    """ API endpoint that allows groups to be viewed or edited.
    """
    permission_classes = (IsAuthenticated,)
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    pagination_class = IdCursorPagination


class UserView(APIView):
    """ API endpoint that allows users creation and returns their token.
    Only admin users can do this to avoid permissions escalation.
    """
    permission_classes = (IsAdminUser,)

    def post(self, request):
        '''Create a user and token, given an email. If user exists just
        provide the token.'''
        serializer = CreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get('email')
        try:
            user = User.objects.get(username=email)
        except User.DoesNotExist:
            user = User.objects.create_user(email, email=email)
        token, created = Token.objects.get_or_create(user=user)

        return Response(
            status=status.HTTP_201_CREATED, data={'token': token.key})


class IdentityFilter(filters.FilterSet):
    """Filter for identities created, using ISO 8601 formatted dates"""
    created_from = django_filters.IsoDateTimeFilter(name="created_at",
                                                    lookup_type="gte")
    created_to = django_filters.IsoDateTimeFilter(name="created_at",
                                                  lookup_type="lte")
    updated_from = django_filters.IsoDateTimeFilter(name="updated_at",
                                                    lookup_type="gte")
    updated_to = django_filters.IsoDateTimeFilter(name="updated_at",
                                                  lookup_type="lte")

    class Meta:
        model = Identity
        fields = ['details', 'communicate_through', 'operator',
                  'created_at', 'created_by', 'updated_at', 'updated_by']


class IdentityViewSet(viewsets.ModelViewSet):
    """ API endpoint that allows identities to be viewed or edited.
    """
    permission_classes = (IsAuthenticated,)
    queryset = Identity.objects.all()
    serializer_class = IdentitySerializer
    filter_class = IdentityFilter
    pagination_class = CreatedAtCursorPagination

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user,
                        updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class IdentitySearchList(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = IdentitySerializer
    pagination_class = CreatedAtCursorPagination

    def get_queryset(self):
        """
        This view should return a list of all the Identities
        for the supplied query parameters. The query parameters
        should be in the form:
        {"address_type": "address"}
        e.g.
        {"msisdn": "+27123"}
        {"email": "foo@bar.com"}

        A special query paramater "include_inactive" can also be passed
        as False to prevent returning identities for which the addresses
        have been set to "inactive"
        e.g.
        {"include_inactive": False}
        """
        query_params = list(self.request.query_params.keys())

        # variable that stores criteria to filter identities by
        filter_criteria = {}
        # variable that stores a list of addresses that should be active
        # if the special filter is passed in
        exclude_if_address_inactive = []

        # Determine from param "include_inactive" whether inactive identities
        # should be included in the search results
        if "include_inactive" in query_params:
            if self.request.query_params["include_inactive"] in [
              "False", 'false', False]:
                include_inactive = False
            else:
                include_inactive = True
        else:
            include_inactive = True  # default to True

        # Compile a list of criteria to filter the identities by, based on the
        # query parameters
        for filter in query_params:
            if filter in ["include_inactive", "cursor"]:
                # Don't add the cursor to the filter_criteria
                pass
            elif filter.startswith("details__addresses__"):
                # Edit the query_param to evaluate the key instead of the value
                # and add it to the filter_criteria
                filter_criteria[filter + "__has_key"] = \
                    self.request.query_params[filter]

                # Add the address to the list of addresses that should not
                # be inactive (tuple e.g ("msisdn", "+27123"))
                if include_inactive is False:
                    exclude_if_address_inactive.append(
                        (filter.replace("details__addresses__", ""),
                         self.request.query_params[filter])
                    )
            else:
                # Add the normal params to the filter criteria
                filter_criteria[filter] = self.request.query_params[filter]

        identities = Identity.objects.filter(**filter_criteria)

        if include_inactive is False:
            # Check through all the identities and exclude ones where the
            # addresses are inactive
            for identity in identities:
                for param in exclude_if_address_inactive:
                    q_key = identity.details["addresses"][param[0]][param[1]]
                    if ('inactive' in q_key and q_key['inactive'] in [True, 'True', 'true']):  # noqa
                        identities = identities.exclude(
                            id=identity.id)

        return identities


def fire_max_send_failures_hook(user, identity):
        raw_hook_event.send(
            sender=None,
            event_name='identity.max_failures',
            payload={
                'identity_id': str(identity.id),
                'failure_count': identity.failed_message_count
            },
            user=user
        )


class UpdateFailedMessageCount(APIView):
    """ Increments failed_message_count for a given Identity and triggers hook
        if max failures reached
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        try:
            # The hooks send the request data as {"hook":{}, "data":{}}
            data = request.data['data']
        except KeyError:
            raise ValidationError('"data" must be supplied')
        if data.get('identity', None) is not None and data['identity'] != "":
            identity = Identity.objects.get(pk=data['identity'])
        elif data.get('to_addr', None) is not None and data['to_addr'] != "":
            identities = Identity.objects\
                .filter(details__addresses__msisdn__has_key=data['to_addr'])\
                .order_by('id')
            if len(identities) > 0:
                identity = identities[0]
            else:
                raise ValidationError('No identity found for given address')
        else:
            raise ValidationError(
                '"data" must contain either "identity" or "to_addr" keys')

        if data['delivered']:
            identity.failed_message_count = 0
        else:
            if identity.failed_message_count is None:
                identity.failed_message_count = 1
            else:
                identity.failed_message_count = F('failed_message_count') + 1
        identity.save(update_fields=['failed_message_count'])
        identity.refresh_from_db()

        if identity.failed_message_count >= \
                settings.MAX_CONSECUTIVE_SEND_FAILURES:
            fire_max_send_failures_hook(request.user, identity)

        return Response(status=status.HTTP_200_OK)


class Address(object):
    def __init__(self, address):
        self.address = address


class IdentityAddresses(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = AddressSerializer
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        """
        This view should return a list of all the addresses the identity has
        for the supplied query parameters.
        Currently only supports address_type and default params
        Always excludes addresses with optedout = True
        """
        identity_id = self.kwargs['identity_id']
        address_type = self.kwargs['address_type']
        use_ct = 'use_communicate_through' in self.request.query_params
        default_only = 'default' in self.request.query_params
        if use_ct:
            identity = Identity.objects.select_related('communicate_through')\
                .get(id=identity_id)
            if identity.communicate_through is not None:
                identity = identity.communicate_through
        else:
            identity = Identity.objects.get(id=identity_id)
        addresses = identity.get_addresses_list(address_type, default_only)
        return [Address(addr) for addr in addresses]


class OptInViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """ API endpoint that allows opt-ins to be created.
    """
    permission_classes = (IsAuthenticated,)
    queryset = OptIn.objects.all()
    serializer_class = OptInSerializer

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


class OptOutSearchList(generics.ListAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = OptOutSerializer
    pagination_class = CreatedAtCursorPagination

    def get_queryset(self):
        try:
            return OptOut.objects.filter(**self.request.query_params.dict())
        except FieldError as e:
            raise ValidationError(str(e))


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
        scheduled_metrics.apply_async()
        resp = {"scheduled_metrics_initiated": True}
        return Response(resp, status=status)


class HealthcheckView(APIView):

    """ Healthcheck Interaction
        GET - returns service up - getting auth'd requires DB
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        import seed_identity_store
        import django
        import rest_framework
        status = 200
        resp = {
            "up": True,
            "result": {
                "database": "Accessible",
                "version": seed_identity_store.__version__,
                "libraries": {
                    "django": django.__version__,
                    "djangorestframework": rest_framework.__version__
                }
            }
        }
        return Response(resp, status=status)


class DetailKeyView(APIView):

    """ DetailKey retrieval for filter views
        GET - returns list of all available key_names in DetailKey model
    """
    permission_classes = (IsAuthenticated,)

    def get(self, request, *args, **kwargs):
        status = 200
        key_names = DetailKey.objects.values_list('key_name', flat=True)
        resp = {
            "key_names": key_names
        }
        return Response(resp, status=status)
