from django.conf.urls import url, include
from rest_framework import routers
from . import views

router = routers.DefaultRouter()
router.register(r'user', views.UserViewSet)
router.register(r'group', views.GroupViewSet)
router.register(r'identities', views.IdentityViewSet)
router.register(r'optout', views.OptOutViewSet)
router.register(r'webhook', views.HookViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browseable API.
urlpatterns = [
    url(r'^api/v1/identities/search/$',
        views.IdentitySearchList.as_view()),
    url(r'^api/v1/identities/(?P<identity_id>.+)/addresses/(?P<address_type>.+)$',  # noqa
        views.IdentityAddresses.as_view()),
    url(r'^api/v1/', include(router.urls)),
]
