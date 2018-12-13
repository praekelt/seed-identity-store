import os
from django.conf.urls import include, url
from django.contrib import admin
from identities import views
import rest_framework.authtoken.views as rf_views

admin.site.site_header = os.environ.get('IDENTITIES_TITLE',
                                        'Seed Identity Store Admin')


urlpatterns = [
    url(r'^admin/',  include(admin.site.urls)),
    url(r'^api/auth/',
        include('rest_framework.urls', namespace='rest_framework')),
    url(r'^api/token-auth/', rf_views.obtain_auth_token),
    url(r'^api/metrics/', views.MetricsView.as_view()),
    url(r'^api/health/', views.HealthcheckView.as_view()),
    url(r'^', include('identities.urls')),
    url(r'^docs/', include('rest_framework_docs.urls')),
]
