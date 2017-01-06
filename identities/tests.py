import json
import responses

try:
    from urllib.parse import urlparse
except ImportError:
    from urlparse import urlparse

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.test import TestCase
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from rest_hooks.models import Hook
from requests_testadapter import TestAdapter, TestSession
from go_http.metrics import MetricsApiClient

from .models import (Identity, OptOut, OptIn, DetailKey, handle_optout,
                     handle_optin, fire_metrics_if_new, fire_optout_metric)
from .tasks import deliver_hook_wrapper, fire_metric, scheduled_metrics
from . import tasks


class RecordingAdapter(TestAdapter):

    """ Record the request that was handled by the adapter.
    """
    request = None

    def send(self, request, *args, **kw):
        self.request = request
        return super(RecordingAdapter, self).send(request, *args, **kw)


class APITestCase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.adminclient = APIClient()
        self.session = TestSession()


class AuthenticatedAPITestCase(APITestCase):

    def make_identity(self, id_data=None):
        if id_data is None:
            id_data = {
                "details": {
                    "name": "Test Name 1",
                    "default_addr_type": "msisdn",
                    "personnel_code": "12345",
                    "addresses": {
                        "msisdn": {
                            "+27123": {}
                        },
                        "email": {
                            "foo1@bar.com": {"default": True},
                            "foo2@bar.com": {}
                        }
                    }
                }
            }
        return Identity.objects.create(**id_data)

    def _replace_get_metric_client(self, session=None):
        return MetricsApiClient(
            auth_token=settings.METRICS_AUTH_TOKEN,
            api_url=settings.METRICS_URL,
            session=self.session)

    def _restore_get_metric_client(self, session=None):
        return MetricsApiClient(
            auth_token=settings.METRICS_AUTH_TOKEN,
            api_url=settings.METRICS_URL,
            session=session)

    def _replace_post_save_hooks(self):
        post_save.disconnect(handle_optout, sender=Identity)
        post_save.disconnect(handle_optin, sender=Identity)
        post_save.disconnect(fire_metrics_if_new, sender=Identity)
        post_save.disconnect(fire_optout_metric, sender=OptOut)

    def _restore_post_save_hooks(self):
        post_save.connect(handle_optout, sender=Identity)
        post_save.connect(handle_optin, sender=Identity)
        post_save.connect(fire_metrics_if_new, sender=Identity)
        post_save.connect(fire_optout_metric, sender=OptOut)

    def setUp(self):
        super(AuthenticatedAPITestCase, self).setUp()

        self._replace_post_save_hooks()
        tasks.get_metric_client = self._replace_get_metric_client

        self.username = 'testuser'
        self.password = 'testpass'
        self.user = User.objects.create_user(self.username,
                                             'testuser@example.com',
                                             self.password)
        token = Token.objects.create(user=self.user)
        self.token = token.key
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token)

        self.superuser = User.objects.create_superuser('testsu',
                                                       'su@example.com',
                                                       'dummypwd')
        sutoken = Token.objects.create(user=self.superuser)
        self.adminclient.credentials(
            HTTP_AUTHORIZATION='Token %s' % sutoken)

    def tearDown(self):
        self._restore_post_save_hooks()
        tasks.get_metric_client = self._restore_get_metric_client


class TestLogin(AuthenticatedAPITestCase):

    def test_login(self):
        # Setup
        post_auth = {"username": "testuser",
                     "password": "testpass"}
        # Execute
        request = self.client.post(
            '/api/token-auth/', post_auth)
        token = request.data.get('token', None)
        # Check
        self.assertIsNotNone(
            token, "Could not receive authentication token on login post.")
        self.assertEqual(
            request.status_code, 200,
            "Status code on /api/token-auth was %s (should be 200)."
            % request.status_code)


class TestUserCreation(AuthenticatedAPITestCase):

    def test_create_user_and_token(self):
        # Setup
        user_request = {"email": "test@example.org"}
        # Execute
        request = self.adminclient.post('/api/v1/user/token/', user_request)
        token = request.json().get('token', None)
        # Check
        self.assertIsNotNone(
            token, "Could not receive authentication token on post.")
        self.assertEqual(
            request.status_code, 201,
            "Status code on /api/v1/user/token/ was %s (should be 201)."
            % request.status_code)

    def test_create_user_and_token_fail_nonadmin(self):
        # Setup
        user_request = {"email": "test@example.org"}
        # Execute
        request = self.client.post('/api/v1/user/token/', user_request)
        error = request.json().get('detail', None)
        # Check
        self.assertIsNotNone(
            error, "Could not receive error on post.")
        self.assertEqual(
            error, "You do not have permission to perform this action.",
            "Error message was unexpected: %s."
            % error)

    def test_create_user_and_token_not_created(self):
        # Setup
        user_request = {"email": "test@example.org"}
        # Execute
        request = self.adminclient.post('/api/v1/user/token/', user_request)
        token = request.json().get('token', None)
        # And again, to get the same token
        request2 = self.adminclient.post('/api/v1/user/token/', user_request)
        token2 = request2.json().get('token', None)

        # Check
        self.assertEqual(
            token, token2,
            "Tokens are not equal, should be the same as not recreated.")

    def test_create_user_new_token_nonadmin(self):
        # Setup
        user_request = {"email": "test@example.org"}
        request = self.adminclient.post('/api/v1/user/token/', user_request)
        token = request.json().get('token', None)
        cleanclient = APIClient()
        cleanclient.credentials(HTTP_AUTHORIZATION='Token %s' % token)
        # Execute
        request = cleanclient.post('/api/v1/user/token/', user_request)
        error = request.json().get('detail', None)
        # Check
        # new user should not be admin
        self.assertIsNotNone(
            error, "Could not receive error on post.")
        self.assertEqual(
            error, "You do not have permission to perform this action.",
            "Error message was unexpected: %s."
            % error)


class TestIdentityAPI(AuthenticatedAPITestCase):

    def test_read_optouts(self):
        # Setup
        identity = self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "identity": identity,
            "reason": "not good messages",
        }
        OptOut.objects.create(**optout_data)
        # Execute
        response = self.client.get('/api/v1/optouts/search/',
                                   {"reason": "not good messages"},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)

    def test_read_optouts_invalid(self):
        # Setup
        identity = self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "identity": identity,
            "reason": "not good messages",
        }
        OptOut.objects.create(**optout_data)
        # Execute
        response = self.client.get('/api/v1/optouts/search/',
                                   {"foo": "bar"},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()[0].replace("u'", "'"),
                         "Cannot resolve keyword 'foo' into field. Choices "
                         "are: address, address_type, created_at, created_by, "
                         "created_by_id, id, identity, identity_id, "
                         "optout_type, reason, request_source, "
                         "requestor_source_id")

    def test_read_optouts_filter(self):
        # Setup
        identity = self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "identity": identity,
            "reason": "not good messages",
        }
        OptOut.objects.create(**optout_data)
        # Execute
        response = self.client.get('/api/v1/optouts/search/',
                                   {"reason": "very good messages"},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 0)

    def test_read_identity(self):
        # Setup
        identity = self.make_identity()
        # Execute
        response = self.client.get('/api/v1/identities/%s/' % identity.id,
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        d = Identity.objects.last()
        self.assertEqual(d.details["name"], "Test Name 1")
        self.assertEqual(d.version, 1)

    def test_read_identity_search_msisdn_single(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data={
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
        })
        self.make_identity(id_data={
            "version": 2,
            "details": {
                "name": "Test Name 3",
                "addresses": {
                    "msisdn": {
                        "+27555": {}
                    }
                }
            }
        })
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"details__addresses__msisdn": "+27555"},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 3")

    def test_read_identity_search_msisdn_multiple(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data={
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
        })
        self.make_identity(id_data={
            "version": 2,
            "details": {
                "name": "Test Name 3",
                "addresses": {
                    "msisdn": {
                        "+27555": {}
                    }
                }
            }
        })
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"details__addresses__msisdn": "+27123"},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)

    def test_read_identity_search_msisdn_inactive_filter(self):
        # Setup
        self.make_identity(id_data={
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27123": {"default": True, "inactive": True}
                    }
                }
            }
        })
        self.make_identity(id_data={
            "version": 2,
            "details": {
                "name": "Test Name 4",
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
        })
        # Execute
        response_default = self.client.get(
            '/api/v1/identities/search/',
            {
                "details__addresses__msisdn": "+27123"
            },
            content_type='application/json')
        response_include_inactive = self.client.get(
            '/api/v1/identities/search/',
            {
                "details__addresses__msisdn": "+27123",
                "include_inactive": True
            },
            content_type='application/json')
        response_exclude_inactive = self.client.get(
            '/api/v1/identities/search/',
            {
                "details__addresses__msisdn": "+27123",
                "include_inactive": False
            },
            content_type='application/json')
        # Check
        self.assertEqual(response_default.status_code,
                         status.HTTP_200_OK)
        data_default = response_default.json()
        self.assertEqual(len(data_default["results"]), 2)

        self.assertEqual(response_include_inactive.status_code,
                         status.HTTP_200_OK)
        data_include = response_include_inactive.json()
        self.assertEqual(len(data_include["results"]), 2)

        self.assertEqual(response_exclude_inactive.status_code,
                         status.HTTP_200_OK)
        data_exclude = response_exclude_inactive.json()
        self.assertEqual(len(data_exclude["results"]), 1)
        self.assertEqual(data_exclude["results"][0]["details"]["name"],
                         "Test Name 4")

    def test_read_identity_search_email(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data={
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
        })
        self.make_identity(id_data={
            "version": 2,
            "details": {
                "name": "Test Name 3",
                "addresses": {
                    "msisdn": {
                        "+27555": {}
                    }
                }
            }
        })
        # Execute
        response = self.client.get(
            '/api/v1/identities/search/',
            {
                "details__addresses__email": "foo1@bar.com",
                "version": 1,
                "include_inactive": True
            },
            content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 1")

    def test_read_identity_search_msisdn_email_inactive_filter(self):
        # Setup
        self.make_identity(id_data={
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "email": {
                        "foo@bar.com": {"default": True, "inactive": True}
                    }
                }
            }
        })
        self.make_identity(id_data={
            "version": 2,
            "details": {
                "name": "Test Name 4",
                "addresses": {
                    "email": {
                        "foo@bar.com": {}
                    }
                }
            }
        })
        # Execute
        response_include_inactive = self.client.get(
            '/api/v1/identities/search/',
            {
                "details__addresses__email": "foo@bar.com",
                "include_inactive": True
            },
            content_type='application/json')
        response_exclude_inactive = self.client.get(
            '/api/v1/identities/search/',
            {
                "details__addresses__email": "foo@bar.com",
                "include_inactive": False
            },
            content_type='application/json')
        # Check
        self.assertEqual(response_include_inactive.status_code,
                         status.HTTP_200_OK)
        data_include = response_include_inactive.json()
        self.assertEqual(len(data_include["results"]), 2)

        self.assertEqual(response_exclude_inactive.status_code,
                         status.HTTP_200_OK)
        data_exclude = response_exclude_inactive.json()
        self.assertEqual(len(data_exclude["results"]), 1)
        self.assertEqual(data_exclude["results"][0]["details"]["name"],
                         "Test Name 4")

    def test_read_identity_search_msisdn_email_and_msisdn(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data={
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "email": {
                        "foo@bar.com": {"default": True, "inactive": True}
                    },
                    "msisdn": {
                        "+27123": {"default": True}
                    }
                }
            }
        })
        self.make_identity(id_data={
            "version": 2,
            "details": {
                "name": "Test Name 4",
                "addresses": {
                    "email": {
                        "foo@bar.com": {}
                    },
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
        })
        self.make_identity(id_data={
            "version": 2,
            "details": {
                "name": "Test Name 5",
                "addresses": {
                    "email": {
                        "foo@bar.com": {}
                    },
                    "msisdn": {
                        "+27123": {"inactive": True}
                    }
                }
            }
        })
        # Execute
        response_include_inactive = self.client.get(
            '/api/v1/identities/search/',
            {
                "details__addresses__email": "foo@bar.com",
                "details__addresses__msisdn": "+27123",
                "include_inactive": True
            },
            content_type='application/json')
        response_exclude_inactive = self.client.get(
            '/api/v1/identities/search/',
            {
                "details__addresses__email": "foo@bar.com",
                "details__addresses__msisdn": "+27123",
                "include_inactive": False
            },
            content_type='application/json')
        # Check
        self.assertEqual(response_include_inactive.status_code,
                         status.HTTP_200_OK)
        data_include = response_include_inactive.json()
        self.assertEqual(len(data_include["results"]), 3)

        self.assertEqual(response_exclude_inactive.status_code,
                         status.HTTP_200_OK)
        data_exclude = response_exclude_inactive.json()
        self.assertEqual(len(data_exclude["results"]), 1)
        self.assertEqual(data_exclude["results"][0]["details"]["name"],
                         "Test Name 4")

    def test_read_identity_search_personnel_code(self):
        # Setup
        self.make_identity()
        self.make_identity({
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
        })
        self.make_identity(id_data={
            "version": 2,
            "details": {
                "name": "Test Name 3",
                "addresses": {
                    "msisdn": {
                        "+27555": {}
                    }
                }
            }
        })
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"details__personnel_code": "23456"},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 2")

    def test_read_identity_search_version(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data={
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
        })
        self.make_identity(id_data={
            "version": 2,
            "details": {
                "name": "Test Name 3",
                "addresses": {
                    "msisdn": {
                        "+27555": {}
                    }
                }
            }
        })
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"version": 2},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 3")

    def test_read_identity_search_communicate_through(self):
        # Setup
        self.make_identity()
        test_id2 = self.make_identity(id_data={
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
        })
        test_id3 = {
            "version": 2,
            "details": {
                "name": "Test Name 3",
                "addresses": {
                    "msisdn": {
                        "+27555": {}
                    }
                }
            }
        }.copy()
        test_id3["communicate_through"] = test_id2
        self.make_identity(id_data=test_id3)
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"communicate_through": str(test_id2.id)},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 3")

    def test_read_identity_addresses_one_no_default(self):
        # Setup
        identity = self.make_identity(id_data={
            "details": {
                "name": "Test One No Default",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27124": {}
                    }
                }
            }
        })
        # Execute
        response = self.client.get(
            '/api/v1/identities/%s/addresses/msisdn' % identity,
            {"default": "True"},
            content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["address"], "+27124")

    def test_read_identity_addresses_two_with_default(self):
        # Setup
        identity = self.make_identity(id_data={
            "details": {
                "name": "Test One No Default",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27124": {},
                        "+27125": {"default": True}
                    }
                }
            }
        })
        # Execute
        response = self.client.get(
            '/api/v1/identities/%s/addresses/msisdn' % identity,
            {"default": "True"},
            content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["address"], "+27125")

    def test_read_identity_addresses_two_with_optout(self):
        # Setup
        identity = self.make_identity(id_data={
            "details": {
                "name": "Test One No Default",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27124": {},
                        "+27125": {"default": True, "optedout": True}
                    }
                }
            }
        })
        # Execute
        response = self.client.get(
            '/api/v1/identities/%s/addresses/msisdn' % identity,
            {"default": "True"},
            content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        # default address is marked as optedout
        self.assertEqual(len(data["results"]), 0)

    def test_update_identity(self):
        # Setup
        identity = self.make_identity()
        new_details = {
            "details": {
                "name": "Changed Name",
                "default_addr_type": "email",
                "addresses": {
                    "msisdn": {"+27123": {}},
                    "email": {"foo1@bar.com": {}, "foo2@bar.com": {}}
                }
            }
        }
        # Execute
        response = self.client.patch('/api/v1/identities/%s/' % identity.id,
                                     json.dumps(new_details),
                                     content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        d = Identity.objects.last()
        self.assertEqual(d.details["name"], "Changed Name")
        self.assertEqual(d.version, 1)

    def test_delete_identity(self):
        # Setup
        identity = self.make_identity()
        # Execute
        response = self.client.delete('/api/v1/identities/%s/' % identity.id,
                                      content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        d = Identity.objects.filter().count()
        self.assertEqual(d, 0)

    def test_create_identity(self):
        # Setup
        identity1 = self.make_identity()
        identity2 = self.make_identity(id_data={
            "details": {
                "name": "Test Name 2",
                "default_addr_type": "msisdn",
                "personnel_code": "23456",
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
        })
        post_identity = {
            "communicate_through": str(identity1.id),
            "operator": str(identity2.id),
            "details": {
                "name": "Test Name",
                "default_addr_type": "msisdn",
                "addresses": "msisdn:+27123 email:foo@bar.com"
            }
        }
        # Execute
        response = self.client.post('/api/v1/identities/',
                                    json.dumps(post_identity),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = Identity.objects.get(id=response.data["id"])
        self.assertEqual(d.details["name"], "Test Name")
        self.assertEqual(d.version, 1)

    def test_create_identity_no_details(self):
        # Setup
        post_identity = {
            "details": {}
        }
        # Execute
        response = self.client.post('/api/v1/identities/',
                                    json.dumps(post_identity),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = Identity.objects.last()
        self.assertEqual(d.version, 1)

    def test_create_identity_detailkeys(self):
        # Setup
        self.make_identity()

        # Check
        c = DetailKey.objects.all().count()
        self.assertEqual(c, 4)

    def test_create_identity_detailkeys_two_new(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data={
            "details": {
                "fresh": "as",
                "default_addr_type": "msisdn",
                "a": "daisy"
            }
        })

        # Check
        c = DetailKey.objects.all().count()
        self.assertEqual(c, 6)

    def test_identity_detailkeys_view(self):
        # Setup
        self.make_identity()

        # Execute
        response = self.client.get('/api/v1/detailkeys/',
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["key_names"]), 4)
        self.assertEqual("default_addr_type" in data["key_names"], True)


class TestOptInAPI(AuthenticatedAPITestCase):
    def test_create_optin_with_identity(self):
        # Setup
        identity = self.make_identity()
        optin_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "identity": str(identity.id)
        }
        # Execute
        response = self.client.post('/api/v1/optin/',
                                    json.dumps(optin_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = OptIn.objects.get(id=response.data["id"])
        self.assertEqual(d.identity, identity)
        self.assertEqual(d.request_source, "test_source")
        self.assertEqual(d.requestor_source_id, '1')

    def test_create_optin_with_address(self):
        # Setup
        identity = self.make_identity()
        optin_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
        }
        # Execute
        response = self.client.post('/api/v1/optin/',
                                    json.dumps(optin_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = OptIn.objects.get(id=response.data["id"])
        self.assertEqual(d.identity, identity)
        self.assertEqual(d.request_source, "test_source")
        self.assertEqual(d.requestor_source_id, '1')

    def test_create_optin_no_matching_address(self):
        # Setup
        optin_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123"
        }
        # Execute
        response = self.client.post('/api/v1/optin/',
                                    json.dumps(optin_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()[0],
                         "There is no identity with this address.")

    def test_create_optin_multiple_matching_addresses(self):
        # Setup
        self.make_identity()
        self.make_identity()
        optin_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
        }
        # Execute
        response = self.client.post('/api/v1/optin/',
                                    json.dumps(optin_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()[0],
            "There are multiple identities with this address.")

    def test_create_webhook(self):
        # Setup
        user = User.objects.get(username='testuser')
        post_data = {
            "target": "http://example.com/test_source/",
            "event": "optin.requested"
        }
        # Execute
        response = self.client.post('/api/v1/webhook/',
                                    json.dumps(post_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = Hook.objects.last()
        self.assertEqual(d.target, 'http://example.com/test_source/')
        self.assertEqual(d.user, user)

    @responses.activate
    def test_deliver_hook_task(self):
        # Setup
        user = User.objects.get(username='testuser')
        hook = Hook.objects.create(
            user=user,
            event='optin.requested',
            target='http://example.com/api/v1/')
        payload = {
            "identity": "test-219f0f88-7d2b-414d-933c-1f8e652869c4",
            "identity_details": {
                "addresses": {
                    "msisdn": {
                        "+27123": {"optedout": True}
                    }
                }
            },
            "optin_address_type": "msisdn",
            "optin_address": "+27123"
        }
        responses.add(
            responses.POST,
            'http://example.com/api/v1/',
            json.dumps(payload),
            status=200, content_type='application/json')

        deliver_hook_wrapper('http://example.com/api/v1/', payload, None, hook)

        # Execute
        self.assertEqual(responses.calls[0].request.url,
                         "http://example.com/api/v1/")

    @responses.activate
    def test_optin(self):
        # Setup
        post_save.connect(receiver=handle_optin, sender=OptIn)
        user = User.objects.get(username='testuser')
        Hook.objects.create(user=user,
                            event='optin.requested',
                            target='http://example.com/api/v1/')
        identity = self.make_identity()
        identity.details["addresses"]["msisdn"]["+27123"]["optedout"] = True
        identity.save()

        payload = {
            "identity": str(identity.id),
            "identity_details": identity.details,
            "optin_address_type": "msisdn",
            "optin_address": "+27123"
        }
        responses.add(
            responses.POST,
            'http://example.com/api/v1/',
            json.dumps(payload),
            status=200, content_type='application/json')

        OptIn.objects.create(
            identity=identity, created_by=user, request_source="test_source",
            requestor_source_id=1, address_type="msisdn", address="+27123")

        self.assertEqual(responses.calls[0].request.url,
                         'http://example.com/api/v1/')
        identity = Identity.objects.get(pk=identity.pk)
        self.assertEqual(identity.details, {
            "name": "Test Name 1",
            "default_addr_type": "msisdn",
            "personnel_code": "12345",
            "addresses": {
                "msisdn": {
                    "+27123": {"optedout": False}
                },
                "email": {
                    "foo1@bar.com": {"default": True},
                    "foo2@bar.com": {}
                }
            }
        })


class TestOptOutAPI(AuthenticatedAPITestCase):
    def test_create_optout_with_identity(self):
        # Setup
        identity = self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "identity": str(identity.id)
        }
        # Execute
        response = self.client.post('/api/v1/optout/',
                                    json.dumps(optout_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = OptOut.objects.get(id=response.data["id"])
        self.assertEqual(d.identity, identity)
        self.assertEqual(d.request_source, "test_source")
        self.assertEqual(d.requestor_source_id, '1')

    def test_create_optout_with_address(self):
        # Setup
        identity = self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "reason": "not good messages"
        }
        # Execute
        response = self.client.post('/api/v1/optout/',
                                    json.dumps(optout_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = OptOut.objects.get(id=response.data["id"])
        self.assertEqual(d.identity, identity)
        self.assertEqual(d.request_source, "test_source")
        self.assertEqual(d.requestor_source_id, '1')
        self.assertEqual(d.reason, 'not good messages')

    def test_create_optout_no_matching_address(self):
        # Setup
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123"
        }
        # Execute
        response = self.client.post('/api/v1/optout/',
                                    json.dumps(optout_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()[0],
                         "There is no identity with this address.")

    def test_create_opt_out_multiple_matching_addresses(self):
        # Setup
        self.make_identity()
        self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "optout_type": "forget"
        }
        # Execute
        response = self.client.post('/api/v1/optout/',
                                    json.dumps(optout_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()[0],
            "There are multiple identities with this address.")

    def test_create_webhook(self):
        # Setup
        user = User.objects.get(username='testuser')
        post_data = {
            "target": "http://example.com/test_source/",
            "event": "optout.requested"
        }
        # Execute
        response = self.client.post('/api/v1/webhook/',
                                    json.dumps(post_data),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = Hook.objects.last()
        self.assertEqual(d.target, 'http://example.com/test_source/')
        self.assertEqual(d.user, user)

    @responses.activate
    def test_deliver_hook_task(self):
        # Setup
        user = User.objects.get(username='testuser')
        hook = Hook.objects.create(
            user=user,
            event='optout.requested',
            target='http://example.com/api/v1/')
        payload = {
            "identity": "test-219f0f88-7d2b-414d-933c-1f8e652869c4",
            "identity_details": {
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            },
            "optout_type": "forget"
        }
        responses.add(
            responses.POST,
            'http://example.com/api/v1/',
            json.dumps(payload),
            status=200, content_type='application/json')

        deliver_hook_wrapper('http://example.com/api/v1/', payload, None, hook)

        # Execute
        self.assertEqual(responses.calls[0].request.url,
                         "http://example.com/api/v1/")

    @responses.activate
    def test_optout_webhook_combination(self):
        # Setup
        post_save.connect(receiver=handle_optout, sender=OptOut)
        user = User.objects.get(username='testuser')
        Hook.objects.create(user=user,
                            event='optout.requested',
                            target='http://example.com/api/v1/')
        identity = self.make_identity()
        payload = {
            "identity": str(identity.id),
            "identity_details": identity.details,
            'optout_type': "forget",
        }
        responses.add(
            responses.POST,
            'http://example.com/api/v1/',
            json.dumps(payload),
            status=200, content_type='application/json')

        OptOut.objects.create(
            identity=identity, created_by=user, request_source="test_source",
            requestor_source_id=1, address_type="msisdn", address="+27123",
            optout_type="forget")

        self.assertEqual(responses.calls[0].request.url,
                         'http://example.com/api/v1/')
        identity = Identity.objects.get(pk=identity.pk)
        self.assertEqual(identity.details, {
            "name": "redacted",
            "default_addr_type": "redacted",
            "personnel_code": "redacted",
            "addresses": {}
        })

    @responses.activate
    def test_optout_webhook_stop(self):
        # Setup
        post_save.connect(receiver=handle_optout, sender=OptOut)
        user = User.objects.get(username='testuser')
        Hook.objects.create(user=user,
                            event='optout.requested',
                            target='http://example.com/api/v1/')
        identity = self.make_identity()
        payload = {
            "identity": str(identity.id),
            "identity_details": identity.details,
            'optout_type': "stop",
        }
        responses.add(
            responses.POST,
            'http://example.com/api/v1/',
            json.dumps(payload),
            status=200, content_type='application/json')

        OptOut.objects.create(
            identity=identity, created_by=user, request_source="test_source",
            requestor_source_id=1, address_type="msisdn", address="+27123",
            optout_type="stop")

        self.assertEqual(responses.calls[0].request.url,
                         'http://example.com/api/v1/')
        identity = Identity.objects.get(pk=identity.pk)
        self.assertEqual(identity.details, {
            "name": "Test Name 1",
            "default_addr_type": "msisdn",
            "personnel_code": "12345",
            "addresses": {
                "msisdn": {
                    "+27123": {"optedout": True}
                },
                "email": {
                    "foo1@bar.com": {"default": True},
                    "foo2@bar.com": {}
                }
            }
        })

    @responses.activate
    def test_optout_webhook_stop_all(self):
        # Setup
        post_save.connect(receiver=handle_optout, sender=OptOut)
        user = User.objects.get(username='testuser')
        Hook.objects.create(user=user,
                            event='optout.requested',
                            target='http://example.com/api/v1/')
        identity = self.make_identity()
        payload = {
            "identity": str(identity.id),
            "identity_details": identity.details,
            'optout_type': "stopall",
        }
        responses.add(
            responses.POST,
            'http://example.com/api/v1/',
            json.dumps(payload),
            status=200, content_type='application/json')

        OptOut.objects.create(
            identity=identity, created_by=user, request_source="test_source",
            requestor_source_id=1, address_type="msisdn", address="+27123",
            optout_type="stopall")

        self.assertEqual(responses.calls[0].request.url,
                         'http://example.com/api/v1/')
        identity = Identity.objects.get(pk=identity.pk)
        self.assertEqual(identity.details, {
            "name": "Test Name 1",
            "default_addr_type": "msisdn",
            "personnel_code": "12345",
            "addresses": {
                "msisdn": {
                    "+27123": {"optedout": True}
                },
                "email": {
                    "foo1@bar.com": {"default": True, "optedout": True},
                    "foo2@bar.com": {"optedout": True}
                }
            }
        })


class TestHealthcheckAPI(AuthenticatedAPITestCase):

    def test_healthcheck_read(self):
        # Setup
        # Execute
        response = self.client.get('/api/health/',
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["up"], True)
        self.assertEqual(response.data["result"]["database"], "Accessible")


class TestMetricsAPI(AuthenticatedAPITestCase):

    def test_metrics_read(self):
        # Setup
        # Execute
        response = self.client.get('/api/metrics/',
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            sorted(response.data["metrics_available"]), sorted([
                'identities.created.sum',
                'identities.created.last',
                'identities.change.msisdn.sum',
                'identities.change.email.sum',
                'optout.sum',
                'optout.total.last',
            ])
        )

    @responses.activate
    def test_post_metrics(self):
        # Setup
        # deactivate Testsession for this test
        self.session = None
        responses.add(responses.POST,
                      "http://metrics-url/metrics/",
                      json={"foo": "bar"},
                      status=200, content_type='application/json')
        # Execute
        response = self.client.post('/api/metrics/',
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["scheduled_metrics_initiated"], True)


class TestMetrics(AuthenticatedAPITestCase):

    def check_request(
            self, request, method, params=None, data=None, headers=None):
        self.assertEqual(request.method, method)
        if params is not None:
            url = urlparse.urlparse(request.url)
            qs = urlparse.parse_qsl(url.query)
            self.assertEqual(dict(qs), params)
        if headers is not None:
            for key, value in headers.items():
                self.assertEqual(request.headers[key], value)
        if data is None:
            self.assertEqual(request.body, None)
        else:
            self.assertEqual(json.loads(request.body), data)

    def _mount_session(self):
        response = [{
            'name': 'foo',
            'value': 9000,
            'aggregator': 'bar',
        }]
        adapter = RecordingAdapter(json.dumps(response).encode('utf-8'))
        self.session.mount(
            "http://metrics-url/metrics/", adapter)
        return adapter

    def test_direct_fire(self):
        # Setup
        adapter = self._mount_session()
        # Execute
        result = fire_metric.apply_async(kwargs={
            "metric_name": 'foo.last',
            "metric_value": 1,
            "session": self.session
        })
        # Check
        self.check_request(
            adapter.request, 'POST',
            data={"foo.last": 1.0}
        )
        self.assertEqual(result.get(),
                         "Fired metric <foo.last> with value <1.0>")

    def test_created_metrics(self):
        # Setup
        adapter = self._mount_session()
        # reconnect metric post_save hook
        post_save.connect(fire_metrics_if_new, sender=Identity)

        # Execute
        self.make_identity()

        # Check
        self.check_request(
            adapter.request, 'POST',
            data={"identities.created.sum": 1.0}
        )
        # remove post_save hooks to prevent teardown errors
        post_save.disconnect(fire_metrics_if_new, sender=Identity)

    @responses.activate
    def test_optout_created_metrics(self):
        # Setup
        identity = self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "identity": identity,
            "reason": "not good messages",
        }
        OptOut.objects.create(**optout_data)

        self.session = None
        # reconnect metric post_save hook
        post_save.connect(fire_optout_metric, sender=OptOut)

        responses.add(responses.POST,
                      "http://metrics-url/metrics/",
                      json={"foo": "bar"},
                      status=200, content_type='application/json')

        # Execute
        OptOut.objects.create(**optout_data)

        # Check
        self.assertEqual(len(responses.calls), 2)
        [call1, call2] = responses.calls
        self.assertEqual(json.loads(call1.request.body), {"optout.sum": 1.0})
        self.assertEqual(json.loads(call2.request.body),
                         {"optout.total.last": 2.0})
        # remove post_save hooks to prevent teardown errors
        post_save.disconnect(fire_optout_metric, sender=OptOut)

    @responses.activate
    def test_multiple_created_metrics(self):
        # Setup
        # deactivate Testsession for this test
        self.session = None
        # reconnect metric post_save hook
        post_save.connect(fire_metrics_if_new, sender=Identity)
        # add metric post response
        responses.add(responses.POST,
                      "http://metrics-url/metrics/",
                      json={"foo": "bar"},
                      status=200, content_type='application/json')

        # Execute
        self.make_identity()
        self.make_identity()

        # Check
        self.assertEqual(len(responses.calls), 2)
        # remove post_save hooks to prevent teardown errors
        post_save.disconnect(fire_metrics_if_new, sender=Identity)

    @responses.activate
    def test_scheduled_metrics(self):
        # Setup
        # deactivate Testsession for this test
        self.session = None
        # add metric post response
        responses.add(responses.POST,
                      "http://metrics-url/metrics/",
                      json={"foo": "bar"},
                      status=200, content_type='application/json')

        # Execute
        result = scheduled_metrics.apply_async()
        # Check
        self.assertEqual(result.get(), "1 Scheduled metrics launched")
        # fire_messagesets_tasks fires two metrics, therefore extra call
        self.assertEqual(len(responses.calls), 1)

    def test_fire_created_last(self):
        # Setup
        adapter = self._mount_session()
        # make two identities
        self.make_identity()
        self.make_identity()

        # Execute
        result = tasks.fire_created_last.apply_async()

        # Check
        self.assertEqual(
            result.get().get(),
            "Fired metric <identities.created.last> with value <2.0>"
        )
        self.check_request(
            adapter.request, 'POST',
            data={"identities.created.last": 2.0}
        )

    def test_update_msisdn_metric(self):
        """
        When a MSISDN is changed on a identity, a sum metric should be fired
        """
        # Setup
        adapter = self._mount_session()

        identity = self.make_identity()
        new_details = {
            "addresses": {
                "msisdn": {"+27123999": {}},
                "email": {"foo1@bar.com": {}, "foo2@bar.com": {}}
            }
        }

        # Execute
        identity.details = new_details
        identity.save()

        # Check
        self.check_request(
            adapter.request, 'POST',
            data={"identities.change.msisdn.sum": 1.0}
        )

    def test_update_msisdn_metric_negative(self):
        """
        When the details of the identity is updated and the MSISDN remains the
        same, no metric request should be made
        """
        # Setup
        adapter = self._mount_session()

        identity = self.make_identity()
        new_details = {
            "addresses": {
                "msisdn": {"+27123": {}},
                "email": {"foo1@bar.com": {}, "foo2@bar.com": {}}
            }
        }

        # Execute
        identity.details = new_details
        identity.save()

        # Check
        self.assertEqual(adapter.request, None)

    def test_update_email_metric(self):
        """
        When a email is changed on a identity, a sum metric should be fired
        """
        # Setup
        adapter = self._mount_session()

        identity = self.make_identity()
        new_details = {
            "addresses": {
                "msisdn": {"+27123": {}},
                "email": {"foo1_new@bar.com": {}, "foo2@bar.com": {}}
            }
        }

        # Execute
        identity.details = new_details
        identity.save()

        # Check
        self.check_request(
            adapter.request, 'POST',
            data={"identities.change.email.sum": 1.0}
        )
