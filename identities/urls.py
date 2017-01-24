from django.conf.urls import url, include
from rest_framework import routers
from . import views

from seed_papertrail.decorators import papertrail

router = routers.DefaultRouter()
router.register(r'user', views.UserViewSet)
router.register(r'group', views.GroupViewSet)
router.register(r'identities', views.IdentityViewSet)
router.register(r'optout', views.OptOutViewSet)
router.register(r'optin', views.OptInViewSet)
router.register(r'webhook', views.HookViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browseable API.
urlpatterns = [
    url(r'^api/v1/identities/search/$',
        papertrail.debug(sample=0.1)(views.IdentitySearchList.as_view())),
    url(r'^api/v1/identities/(?P<identity_id>.+)/addresses/(?P<address_type>.+)$',  # noqa
        papertrail.debug(sample=0.1)(views.IdentityAddresses.as_view())),
    url(r'^api/v1/user/token/$',
        papertrail.debug(sample=0.1)(views.UserView.as_view()),
        name='create-user-token'),
    url(r'^api/v1/detailkeys/',
        papertrail.debug(sample=0.1)(views.DetailKeyView.as_view())),
    # NOTE: Not sure how to wrap these router.urls in papertrail yet,
    #       seems like DRF makes this unnecessarily difficult.
    url(r'^api/v1/', include(router.urls)),
    url(r'^api/v1/optouts/search/$',
        papertrail.debug(sample=0.1)(views.OptOutSearchList.as_view())),
]
