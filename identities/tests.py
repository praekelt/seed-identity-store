import json

import responses
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.test import TestCase
from prometheus_client import REGISTRY
from requests_testadapter import TestAdapter, TestSession
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from rest_hooks.models import Hook

from .models import DetailKey, Identity, OptIn, OptOut, handle_optin, handle_optout
from .tasks import deliver_hook_wrapper


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
                        "msisdn": {"+27123": {}},
                        "email": {
                            "foo1@bar.com": {"default": True},
                            "foo2@bar.com": {},
                        },
                    },
                }
            }
        return Identity.objects.create(**id_data)

    def _replace_post_save_hooks(self):
        post_save.disconnect(handle_optout, sender=Identity)
        post_save.disconnect(handle_optin, sender=Identity)

    def _restore_post_save_hooks(self):
        post_save.connect(handle_optout, sender=Identity)
        post_save.connect(handle_optin, sender=Identity)

    def setUp(self):
        super(AuthenticatedAPITestCase, self).setUp()

        self._replace_post_save_hooks()

        self.username = "testuser"
        self.password = "testpass"
        self.user = User.objects.create_user(
            self.username, "testuser@example.com", self.password
        )
        token = Token.objects.create(user=self.user)
        self.token = token.key
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token)

        self.superuser = User.objects.create_superuser(
            "testsu", "su@example.com", "dummypwd"
        )
        sutoken = Token.objects.create(user=self.superuser)
        self.adminclient.credentials(HTTP_AUTHORIZATION="Token %s" % sutoken)

    def tearDown(self):
        self._restore_post_save_hooks()


class TestLogin(AuthenticatedAPITestCase):
    def test_login(self):
        # Setup
        post_auth = {"username": "testuser", "password": "testpass"}
        # Execute
        request = self.client.post("/api/token-auth/", post_auth)
        token = request.data.get("token", None)
        # Check
        self.assertIsNotNone(
            token, "Could not receive authentication token on login post."
        )
        self.assertEqual(
            request.status_code,
            200,
            "Status code on /api/token-auth was %s (should be 200)."
            % request.status_code,
        )


class TestUserCreation(AuthenticatedAPITestCase):
    def test_list_user(self):
        response = self.client.get("/api/v1/user/")

        body = response.json()
        self.assertEqual(len(body["results"]), 2)

    def test_list_group(self):
        response = self.client.get("/api/v1/group/")

        body = response.json()
        self.assertEqual(len(body["results"]), 0)

    def test_create_user_and_token(self):
        # Setup
        user_request = {"email": "test@example.org"}
        # Execute
        request = self.adminclient.post("/api/v1/user/token/", user_request)
        token = request.json().get("token", None)
        # Check
        self.assertIsNotNone(token, "Could not receive authentication token on post.")
        self.assertEqual(
            request.status_code,
            201,
            "Status code on /api/v1/user/token/ was %s (should be 201)."
            % request.status_code,
        )

    def test_create_user_and_token_fail_nonadmin(self):
        # Setup
        user_request = {"email": "test@example.org"}
        # Execute
        request = self.client.post("/api/v1/user/token/", user_request)
        error = request.json().get("detail", None)
        # Check
        self.assertIsNotNone(error, "Could not receive error on post.")
        self.assertEqual(
            error,
            "You do not have permission to perform this action.",
            "Error message was unexpected: %s." % error,
        )

    def test_create_user_and_token_not_created(self):
        # Setup
        user_request = {"email": "test@example.org"}
        # Execute
        request = self.adminclient.post("/api/v1/user/token/", user_request)
        token = request.json().get("token", None)
        # And again, to get the same token
        request2 = self.adminclient.post("/api/v1/user/token/", user_request)
        token2 = request2.json().get("token", None)

        # Check
        self.assertEqual(
            token, token2, "Tokens are not equal, should be the same as not recreated."
        )

    def test_create_user_new_token_nonadmin(self):
        # Setup
        user_request = {"email": "test@example.org"}
        request = self.adminclient.post("/api/v1/user/token/", user_request)
        token = request.json().get("token", None)
        cleanclient = APIClient()
        cleanclient.credentials(HTTP_AUTHORIZATION="Token %s" % token)
        # Execute
        request = cleanclient.post("/api/v1/user/token/", user_request)
        error = request.json().get("detail", None)
        # Check
        # new user should not be admin
        self.assertIsNotNone(error, "Could not receive error on post.")
        self.assertEqual(
            error,
            "You do not have permission to perform this action.",
            "Error message was unexpected: %s." % error,
        )


class TestIdentityAPI(AuthenticatedAPITestCase):
    def test_list_pagination_one_page(self):
        identity = self.make_identity()

        response = self.client.get("/api/v1/identities/")

        body = response.json()
        self.assertEqual(len(body["results"]), 1)
        self.assertEqual(body["results"][0]["id"], str(identity.id))
        self.assertIsNone(body["previous"])
        self.assertIsNone(body["next"])

    def test_list_pagination_two_pages(self):
        identities = []
        for i in range(3):
            identities.append(self.make_identity())

        # Test first page
        response = self.client.get("/api/v1/identities/")

        body = response.json()
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(body["results"][0]["id"], str(identities[2].id))
        self.assertEqual(body["results"][1]["id"], str(identities[1].id))
        self.assertIsNone(body["previous"])
        self.assertIsNotNone(body["next"])

        # Test next page
        response = self.client.get(body["next"])

        body = response.json()
        self.assertEqual(len(body["results"]), 1)
        self.assertEqual(body["results"][0]["id"], str(identities[0].id))
        self.assertIsNotNone(body["previous"])
        self.assertIsNone(body["next"])

        # Test going back to previous page works
        response = self.client.get(body["previous"])

        body = response.json()
        self.assertEqual(len(body["results"]), 2)
        self.assertEqual(body["results"][0]["id"], str(identities[2].id))
        self.assertEqual(body["results"][1]["id"], str(identities[1].id))
        self.assertIsNone(body["previous"])
        self.assertIsNotNone(body["next"])

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
        response = self.client.get(
            "/api/v1/optouts/search/",
            {"reason": "not good messages"},
            content_type="application/json",
        )
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
        response = self.client.get(
            "/api/v1/optouts/search/", {"foo": "bar"}, content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()[0].replace("u'", "'"),
            "Cannot resolve keyword 'foo' into field. Choices "
            "are: address, address_type, created_at, created_by, "
            "created_by_id, id, identity, identity_id, "
            "optout_type, reason, request_source, "
            "requestor_source_id",
        )

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
        response = self.client.get(
            "/api/v1/optouts/search/",
            {"reason": "very good messages"},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 0)

    def test_read_identity(self):
        # Setup
        identity = self.make_identity()
        # Execute
        response = self.client.get(
            "/api/v1/identities/%s/" % identity.id, content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        d = Identity.objects.last()
        self.assertEqual(d.details["name"], "Test Name 1")
        self.assertEqual(d.version, 1)

    def test_read_identity_search_msisdn_single(self):
        # Setup
        self.make_identity()
        self.make_identity(
            id_data={
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {"msisdn": {"+27123": {}}},
                }
            }
        )
        self.make_identity(
            id_data={
                "version": 2,
                "details": {
                    "name": "Test Name 3",
                    "addresses": {"msisdn": {"+27555": {}}},
                },
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/search/",
            {"details__addresses__msisdn": "+27555"},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 3")

    def test_read_identity_search_msisdn_multiple(self):
        # Setup
        self.make_identity()
        self.make_identity(
            id_data={
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {"msisdn": {"+27123": {}}},
                }
            }
        )
        self.make_identity(
            id_data={
                "version": 2,
                "details": {
                    "name": "Test Name 3",
                    "addresses": {"msisdn": {"+27555": {}}},
                },
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/search/",
            {"details__addresses__msisdn": "+27123"},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)

    def test_read_identity_search_msisdn_inactive_filter(self):
        # Setup
        self.make_identity(
            id_data={
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {
                        "msisdn": {"+27123": {"default": True, "inactive": True}}
                    },
                }
            }
        )
        self.make_identity(
            id_data={
                "version": 2,
                "details": {
                    "name": "Test Name 4",
                    "addresses": {"msisdn": {"+27123": {}}},
                },
            }
        )
        # Execute
        response_default = self.client.get(
            "/api/v1/identities/search/",
            {"details__addresses__msisdn": "+27123"},
            content_type="application/json",
        )
        response_include_inactive = self.client.get(
            "/api/v1/identities/search/",
            {"details__addresses__msisdn": "+27123", "include_inactive": True},
            content_type="application/json",
        )
        response_exclude_inactive = self.client.get(
            "/api/v1/identities/search/",
            {"details__addresses__msisdn": "+27123", "include_inactive": False},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response_default.status_code, status.HTTP_200_OK)
        data_default = response_default.json()
        self.assertEqual(len(data_default["results"]), 2)

        self.assertEqual(response_include_inactive.status_code, status.HTTP_200_OK)
        data_include = response_include_inactive.json()
        self.assertEqual(len(data_include["results"]), 2)

        self.assertEqual(response_exclude_inactive.status_code, status.HTTP_200_OK)
        data_exclude = response_exclude_inactive.json()
        self.assertEqual(len(data_exclude["results"]), 1)
        self.assertEqual(data_exclude["results"][0]["details"]["name"], "Test Name 4")

    def test_read_identity_search_email(self):
        # Setup
        self.make_identity()
        self.make_identity(
            id_data={
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {"msisdn": {"+27123": {}}},
                }
            }
        )
        self.make_identity(
            id_data={
                "version": 2,
                "details": {
                    "name": "Test Name 3",
                    "addresses": {"msisdn": {"+27555": {}}},
                },
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/search/",
            {
                "details__addresses__email": "foo1@bar.com",
                "version": 1,
                "include_inactive": True,
            },
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 1")

    def test_read_identity_search_msisdn_email_inactive_filter(self):
        # Setup
        self.make_identity(
            id_data={
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {
                        "email": {"foo@bar.com": {"default": True, "inactive": True}}
                    },
                }
            }
        )
        self.make_identity(
            id_data={
                "version": 2,
                "details": {
                    "name": "Test Name 4",
                    "addresses": {"email": {"foo@bar.com": {}}},
                },
            }
        )
        # Execute
        response_include_inactive = self.client.get(
            "/api/v1/identities/search/",
            {"details__addresses__email": "foo@bar.com", "include_inactive": True},
            content_type="application/json",
        )
        response_exclude_inactive = self.client.get(
            "/api/v1/identities/search/",
            {"details__addresses__email": "foo@bar.com", "include_inactive": False},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response_include_inactive.status_code, status.HTTP_200_OK)
        data_include = response_include_inactive.json()
        self.assertEqual(len(data_include["results"]), 2)

        self.assertEqual(response_exclude_inactive.status_code, status.HTTP_200_OK)
        data_exclude = response_exclude_inactive.json()
        self.assertEqual(len(data_exclude["results"]), 1)
        self.assertEqual(data_exclude["results"][0]["details"]["name"], "Test Name 4")

    def test_read_identity_search_msisdn_email_and_msisdn(self):
        # Setup
        self.make_identity()
        self.make_identity(
            id_data={
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {
                        "email": {"foo@bar.com": {"default": True, "inactive": True}},
                        "msisdn": {"+27123": {"default": True}},
                    },
                }
            }
        )
        self.make_identity(
            id_data={
                "version": 2,
                "details": {
                    "name": "Test Name 4",
                    "addresses": {
                        "email": {"foo@bar.com": {}},
                        "msisdn": {"+27123": {}},
                    },
                },
            }
        )
        self.make_identity(
            id_data={
                "version": 2,
                "details": {
                    "name": "Test Name 5",
                    "addresses": {
                        "email": {"foo@bar.com": {}},
                        "msisdn": {"+27123": {"inactive": True}},
                    },
                },
            }
        )
        # Execute
        response_include_inactive = self.client.get(
            "/api/v1/identities/search/",
            {
                "details__addresses__email": "foo@bar.com",
                "details__addresses__msisdn": "+27123",
                "include_inactive": True,
            },
            content_type="application/json",
        )
        response_exclude_inactive = self.client.get(
            "/api/v1/identities/search/",
            {
                "details__addresses__email": "foo@bar.com",
                "details__addresses__msisdn": "+27123",
                "include_inactive": False,
            },
            content_type="application/json",
        )
        # Check
        self.assertEqual(response_include_inactive.status_code, status.HTTP_200_OK)
        data_include = response_include_inactive.json()

        # First page
        self.assertEqual(len(data_include["results"]), 2)

        # Second page
        response_exclude_inactive_page2 = self.client.get(data_include["next"])

        data_include_page2 = response_exclude_inactive_page2.json()
        self.assertEqual(len(data_include_page2["results"]), 1)

        self.assertEqual(response_exclude_inactive.status_code, status.HTTP_200_OK)
        data_exclude = response_exclude_inactive.json()
        self.assertEqual(len(data_exclude["results"]), 1)
        self.assertEqual(data_exclude["results"][0]["details"]["name"], "Test Name 4")

    def test_read_identity_search_personnel_code(self):
        # Setup
        self.make_identity()
        self.make_identity(
            {
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {"msisdn": {"+27123": {}}},
                }
            }
        )
        self.make_identity(
            id_data={
                "version": 2,
                "details": {
                    "name": "Test Name 3",
                    "addresses": {"msisdn": {"+27555": {}}},
                },
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/search/",
            {"details__personnel_code": "23456"},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 2")

    def test_read_identity_search_version(self):
        # Setup
        self.make_identity()
        self.make_identity(
            id_data={
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {"msisdn": {"+27123": {}}},
                }
            }
        )
        self.make_identity(
            id_data={
                "version": 2,
                "details": {
                    "name": "Test Name 3",
                    "addresses": {"msisdn": {"+27555": {}}},
                },
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/search/",
            {"version": 2},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 3")

    def test_read_identity_search_communicate_through(self):
        # Setup
        self.make_identity()
        test_id2 = self.make_identity(
            id_data={
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {"msisdn": {"+27123": {}}},
                }
            }
        )
        test_id3 = {
            "version": 2,
            "details": {"name": "Test Name 3", "addresses": {"msisdn": {"+27555": {}}}},
        }.copy()
        test_id3["communicate_through"] = test_id2
        self.make_identity(id_data=test_id3)
        # Execute
        response = self.client.get(
            "/api/v1/identities/search/",
            {"communicate_through": str(test_id2.id)},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 3")

    def test_read_identity_addresses_one_no_default(self):
        # Setup
        identity = self.make_identity(
            id_data={
                "details": {
                    "name": "Test One No Default",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {"msisdn": {"+27124": {}}},
                }
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/%s/addresses/msisdn" % identity,
            {"default": "True"},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["address"], "+27124")

    def test_read_identity_addresses_two_with_default(self):
        # Setup
        identity = self.make_identity(
            id_data={
                "details": {
                    "name": "Test One No Default",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {
                        "msisdn": {"+27124": {}, "+27125": {"default": True}}
                    },
                }
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/%s/addresses/msisdn" % identity,
            {"default": "True"},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["address"], "+27125")

    def test_read_identity_addresses_two_with_optout(self):
        # Setup
        identity = self.make_identity(
            id_data={
                "details": {
                    "name": "Test One No Default",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {
                        "msisdn": {
                            "+27124": {},
                            "+27125": {"default": True, "optedout": True},
                        }
                    },
                }
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/%s/addresses/msisdn" % identity,
            {"default": "True"},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        # default address is marked as optedout
        self.assertEqual(len(data["results"]), 0)

    def test_read_identity_addresses_with_communicate_through(self):
        # Setup
        identity = self.make_identity(
            id_data={
                "details": {
                    "name": "Test One No Default",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {
                        "msisdn": {"+27124": {}, "+27125": {"default": True}}
                    },
                }
            }
        )
        sub_identity = self.make_identity(
            id_data={
                "communicate_through": identity,
                "details": {
                    "name": "Test One CT",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23457",
                    "addresses": {
                        "msisdn": {"+27321": {}, "+27543": {"default": True}}
                    },
                },
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/%s/addresses/msisdn" % sub_identity,
            {"default": "True", "use_communicate_through": "True"},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["address"], "+27125")

    def test_read_identity_addresses_without_communicate_through(self):
        # Setup
        identity = self.make_identity(
            id_data={
                "details": {
                    "name": "Test One No Default",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {
                        "msisdn": {"+27124": {}, "+27125": {"default": True}}
                    },
                }
            }
        )
        sub_identity = self.make_identity(
            id_data={
                "communicate_through": identity,
                "details": {
                    "name": "Test One CT",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23457",
                    "addresses": {
                        "msisdn": {"+27321": {}, "+27543": {"default": True}}
                    },
                },
            }
        )
        # Execute
        response = self.client.get(
            "/api/v1/identities/%s/addresses/msisdn" % sub_identity,
            {"default": "True"},
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["address"], "+27543")

    def test_update_identity(self):
        # Setup
        identity = self.make_identity()
        new_details = {
            "details": {
                "name": "Changed Name",
                "default_addr_type": "email",
                "addresses": {
                    "msisdn": {"+27123": {}},
                    "email": {"foo1@bar.com": {}, "foo2@bar.com": {}},
                },
            }
        }
        # Execute
        response = self.client.patch(
            "/api/v1/identities/%s/" % identity.id,
            json.dumps(new_details),
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        d = Identity.objects.last()
        self.assertEqual(d.details["name"], "Changed Name")
        self.assertEqual(d.version, 1)

    def test_delete_identity(self):
        # Setup
        identity = self.make_identity()
        # Execute
        response = self.client.delete(
            "/api/v1/identities/%s/" % identity.id, content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        d = Identity.objects.filter().count()
        self.assertEqual(d, 0)

    def test_create_identity(self):
        # Setup
        identity1 = self.make_identity()
        identity2 = self.make_identity(
            id_data={
                "details": {
                    "name": "Test Name 2",
                    "default_addr_type": "msisdn",
                    "personnel_code": "23456",
                    "addresses": {"msisdn": {"+27123": {}}},
                }
            }
        )
        post_identity = {
            "communicate_through": str(identity1.id),
            "operator": str(identity2.id),
            "details": {
                "name": "Test Name",
                "default_addr_type": "msisdn",
                "addresses": "msisdn:+27123 email:foo@bar.com",
            },
        }
        # Execute
        response = self.client.post(
            "/api/v1/identities/",
            json.dumps(post_identity),
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = Identity.objects.get(id=response.data["id"])
        self.assertEqual(d.details["name"], "Test Name")
        self.assertEqual(d.version, 1)

    def test_create_identity_no_details(self):
        # Setup
        post_identity = {"details": {}}
        # Execute
        response = self.client.post(
            "/api/v1/identities/",
            json.dumps(post_identity),
            content_type="application/json",
        )
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
        self.make_identity(
            id_data={
                "details": {"fresh": "as", "default_addr_type": "msisdn", "a": "daisy"}
            }
        )

        # Check
        c = DetailKey.objects.all().count()
        self.assertEqual(c, 6)

    def test_identity_detailkeys_view(self):
        # Setup
        self.make_identity()

        # Execute
        response = self.client.get(
            "/api/v1/detailkeys/", content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["key_names"]), 4)
        self.assertEqual("default_addr_type" in data["key_names"], True)

    def test_update_failed_message_count_identity_given(self):
        # Setup
        identity = self.make_identity()
        data = {"data": {"identity": str(identity.id), "delivered": False}}
        # Execute
        response = self.client.post(
            "/api/v1/identities/message_count/",
            json.dumps(data),
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        d = Identity.objects.last()
        self.assertEqual(d.failed_message_count, 1)

    def test_update_failed_message_count_address_given(self):
        # Setup
        self.make_identity()
        data = {"data": {"to_addr": "+27123", "delivered": False}}
        # Execute
        response = self.client.post(
            "/api/v1/identities/message_count/",
            json.dumps(data),
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        d = Identity.objects.last()
        self.assertEqual(d.failed_message_count, 1)

    @responses.activate
    def test_reached_max_failed_message_count(self):
        # Setup
        hook = Hook.objects.create(
            user=self.user, event="identity.max_failures", target="http://example.com"
        )
        responses.add(
            responses.POST,
            "http://example.com",
            status=200,
            content_type="application/json",
        )

        identity = self.make_identity()
        identity.failed_message_count = 4
        identity.save()
        data = {"data": {"identity": str(identity.id), "delivered": False}}
        # Execute
        response = self.client.post(
            "/api/v1/identities/message_count/",
            json.dumps(data),
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        d = Identity.objects.last()
        self.assertEqual(d.failed_message_count, 5)

        [r] = responses.calls
        r = json.loads(r.request.body)
        self.assertEqual(
            r["hook"], {"id": hook.id, "event": hook.event, "target": hook.target}
        )
        self.assertEqual(
            r["data"],
            {"identity_id": str(d.id), "failure_count": d.failed_message_count},
        )

    def test_update_failed_message_count_reset_on_success(self):
        # Setup
        identity = self.make_identity()
        identity.failed_message_count = 2
        identity.save()
        data = {"data": {"identity": str(identity.id), "delivered": True}}
        # Execute
        response = self.client.post(
            "/api/v1/identities/message_count/",
            json.dumps(data),
            content_type="application/json",
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        d = Identity.objects.last()
        self.assertEqual(d.failed_message_count, 0)

    def test_update_failed_message_count_no_identity_supplied(self):
        """
        If neither the identity or to_addr fields are populated, we should get
        an error returned to us.
        """
        data = {"data": {"delivered": True}}

        response = self.client.post(
            "/api/v1/identities/message_count/",
            json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data, ['"data" must contain either "identity" or "to_addr" keys']
        )

    def test_update_failed_message_count_nonexisting_address(self):
        """
        If an address is supplied, that doesn't belong to any identity, then
        an error should be returned.
        """
        data = {"data": {"to_addr": "invalid-address", "delivered": True}}

        response = self.client.post(
            "/api/v1/identities/message_count/",
            json.dumps(data),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, ["No identity found for given address"])


class TestOptInAPI(AuthenticatedAPITestCase):
    def test_create_optin_with_identity(self):
        # Setup
        identity = self.make_identity()
        optin_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "identity": str(identity.id),
        }
        # Execute
        response = self.client.post(
            "/api/v1/optin/", json.dumps(optin_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = OptIn.objects.get(id=response.data["id"])
        self.assertEqual(d.identity, identity)
        self.assertEqual(d.request_source, "test_source")
        self.assertEqual(d.requestor_source_id, "1")

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
        response = self.client.post(
            "/api/v1/optin/", json.dumps(optin_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = OptIn.objects.get(id=response.data["id"])
        self.assertEqual(d.identity, identity)
        self.assertEqual(d.request_source, "test_source")
        self.assertEqual(d.requestor_source_id, "1")

    def test_create_optin_no_matching_address(self):
        # Setup
        optin_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
        }
        # Execute
        response = self.client.post(
            "/api/v1/optin/", json.dumps(optin_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()[0], "There is no identity with this address.")

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
        response = self.client.post(
            "/api/v1/optin/", json.dumps(optin_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()[0], "There are multiple identities with this address."
        )

    def test_create_webhook(self):
        # Setup
        user = User.objects.get(username="testuser")
        post_data = {
            "target": "http://example.com/test_source/",
            "event": "optin.requested",
        }
        # Execute
        response = self.client.post(
            "/api/v1/webhook/", json.dumps(post_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = Hook.objects.last()
        self.assertEqual(d.target, "http://example.com/test_source/")
        self.assertEqual(d.user, user)

    @responses.activate
    def test_deliver_hook_task(self):
        # Setup
        user = User.objects.get(username="testuser")
        hook = Hook.objects.create(
            user=user, event="optin.requested", target="http://example.com/api/v1/"
        )
        payload = {
            "identity": "test-219f0f88-7d2b-414d-933c-1f8e652869c4",
            "identity_details": {
                "addresses": {"msisdn": {"+27123": {"optedout": True}}}
            },
            "optin_address_type": "msisdn",
            "optin_address": "+27123",
        }
        responses.add(
            responses.POST,
            "http://example.com/api/v1/",
            json.dumps(payload),
            status=200,
            content_type="application/json",
        )

        deliver_hook_wrapper("http://example.com/api/v1/", payload, None, hook)

        # Execute
        self.assertEqual(responses.calls[0].request.url, "http://example.com/api/v1/")

    @responses.activate
    def test_optin(self):
        # Setup
        post_save.connect(receiver=handle_optin, sender=OptIn)
        user = User.objects.get(username="testuser")
        Hook.objects.create(
            user=user, event="optin.requested", target="http://example.com/api/v1/"
        )
        identity = self.make_identity()
        identity.details["addresses"]["msisdn"]["+27123"]["optedout"] = True
        identity.save()

        payload = {
            "identity": str(identity.id),
            "identity_details": identity.details,
            "optin_address_type": "msisdn",
            "optin_address": "+27123",
        }
        responses.add(
            responses.POST,
            "http://example.com/api/v1/",
            json.dumps(payload),
            status=200,
            content_type="application/json",
        )

        OptIn.objects.create(
            identity=identity,
            created_by=user,
            request_source="test_source",
            requestor_source_id=1,
            address_type="msisdn",
            address="+27123",
        )

        self.assertEqual(responses.calls[0].request.url, "http://example.com/api/v1/")
        identity = Identity.objects.get(pk=identity.pk)
        self.assertEqual(
            identity.details,
            {
                "name": "Test Name 1",
                "default_addr_type": "msisdn",
                "personnel_code": "12345",
                "addresses": {
                    "msisdn": {"+27123": {"optedout": False}},
                    "email": {"foo1@bar.com": {"default": True}, "foo2@bar.com": {}},
                },
            },
        )


class TestOptOutAPI(AuthenticatedAPITestCase):
    def test_create_optout_with_identity(self):
        # Setup
        identity = self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "identity": str(identity.id),
        }
        # Execute
        response = self.client.post(
            "/api/v1/optout/", json.dumps(optout_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = OptOut.objects.get(id=response.data["id"])
        self.assertEqual(d.identity, identity)
        self.assertEqual(d.request_source, "test_source")
        self.assertEqual(d.requestor_source_id, "1")

    def test_create_optout_with_address(self):
        # Setup
        identity = self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "reason": "not good messages",
        }
        # Execute
        response = self.client.post(
            "/api/v1/optout/", json.dumps(optout_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = OptOut.objects.get(id=response.data["id"])
        self.assertEqual(d.identity, identity)
        self.assertEqual(d.request_source, "test_source")
        self.assertEqual(d.requestor_source_id, "1")
        self.assertEqual(d.reason, "not good messages")

    def test_create_optout_no_matching_address(self):
        # Setup
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
        }
        # Execute
        response = self.client.post(
            "/api/v1/optout/", json.dumps(optout_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()[0], "There is no identity with this address.")

    def test_create_opt_out_multiple_matching_addresses(self):
        # Setup
        self.make_identity()
        self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "optout_type": "forget",
        }
        # Execute
        response = self.client.post(
            "/api/v1/optout/", json.dumps(optout_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json()[0], "There are multiple identities with this address."
        )

    def test_list_webhook(self):
        response = self.client.get("/api/v1/webhook/")

        body = response.json()
        self.assertEqual(len(body["results"]), 0)

    def test_create_webhook(self):
        # Setup
        user = User.objects.get(username="testuser")
        post_data = {
            "target": "http://example.com/test_source/",
            "event": "optout.requested",
        }
        # Execute
        response = self.client.post(
            "/api/v1/webhook/", json.dumps(post_data), content_type="application/json"
        )
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = Hook.objects.last()
        self.assertEqual(d.target, "http://example.com/test_source/")
        self.assertEqual(d.user, user)

    @responses.activate
    def test_deliver_hook_task(self):
        # Setup
        user = User.objects.get(username="testuser")
        hook = Hook.objects.create(
            user=user, event="optout.requested", target="http://example.com/api/v1/"
        )
        payload = {
            "identity": "test-219f0f88-7d2b-414d-933c-1f8e652869c4",
            "identity_details": {"addresses": {"msisdn": {"+27123": {}}}},
            "optout_type": "forget",
        }
        responses.add(
            responses.POST,
            "http://example.com/api/v1/",
            json.dumps(payload),
            status=200,
            content_type="application/json",
        )

        deliver_hook_wrapper("http://example.com/api/v1/", payload, None, hook)

        # Execute
        self.assertEqual(responses.calls[0].request.url, "http://example.com/api/v1/")

    @responses.activate
    def test_optout_webhook_combination(self):
        # Setup
        post_save.connect(receiver=handle_optout, sender=OptOut)
        user = User.objects.get(username="testuser")
        Hook.objects.create(
            user=user, event="optout.requested", target="http://example.com/api/v1/"
        )
        identity = self.make_identity()
        payload = {
            "identity": str(identity.id),
            "identity_details": identity.details,
            "optout_type": "forget",
        }
        responses.add(
            responses.POST,
            "http://example.com/api/v1/",
            json.dumps(payload),
            status=200,
            content_type="application/json",
        )

        OptOut.objects.create(
            identity=identity,
            created_by=user,
            request_source="test_source",
            requestor_source_id=1,
            address_type="msisdn",
            address="+27123",
            optout_type="forget",
        )

        self.assertEqual(responses.calls[0].request.url, "http://example.com/api/v1/")
        identity = Identity.objects.get(pk=identity.pk)
        self.assertEqual(
            identity.details,
            {
                "name": "redacted",
                "default_addr_type": "redacted",
                "personnel_code": "redacted",
                "addresses": {},
            },
        )

    @responses.activate
    def test_optout_webhook_stop(self):
        # Setup
        post_save.connect(receiver=handle_optout, sender=OptOut)
        user = User.objects.get(username="testuser")
        Hook.objects.create(
            user=user, event="optout.requested", target="http://example.com/api/v1/"
        )
        identity = self.make_identity()
        payload = {
            "identity": str(identity.id),
            "identity_details": identity.details,
            "optout_type": "stop",
        }
        responses.add(
            responses.POST,
            "http://example.com/api/v1/",
            json.dumps(payload),
            status=200,
            content_type="application/json",
        )

        OptOut.objects.create(
            identity=identity,
            created_by=user,
            request_source="test_source",
            requestor_source_id=1,
            address_type="msisdn",
            address="+27123",
            optout_type="stop",
        )

        self.assertEqual(responses.calls[0].request.url, "http://example.com/api/v1/")
        identity = Identity.objects.get(pk=identity.pk)
        self.assertEqual(
            identity.details,
            {
                "name": "Test Name 1",
                "default_addr_type": "msisdn",
                "personnel_code": "12345",
                "addresses": {
                    "msisdn": {"+27123": {"optedout": True}},
                    "email": {"foo1@bar.com": {"default": True}, "foo2@bar.com": {}},
                },
            },
        )

    @responses.activate
    def test_optout_webhook_stop_all(self):
        # Setup
        post_save.connect(receiver=handle_optout, sender=OptOut)
        user = User.objects.get(username="testuser")
        Hook.objects.create(
            user=user, event="optout.requested", target="http://example.com/api/v1/"
        )
        identity = self.make_identity()
        payload = {
            "identity": str(identity.id),
            "identity_details": identity.details,
            "optout_type": "stopall",
        }
        responses.add(
            responses.POST,
            "http://example.com/api/v1/",
            json.dumps(payload),
            status=200,
            content_type="application/json",
        )

        OptOut.objects.create(
            identity=identity,
            created_by=user,
            request_source="test_source",
            requestor_source_id=1,
            address_type="msisdn",
            address="+27123",
            optout_type="stopall",
        )

        self.assertEqual(responses.calls[0].request.url, "http://example.com/api/v1/")
        identity = Identity.objects.get(pk=identity.pk)
        self.assertEqual(
            identity.details,
            {
                "name": "Test Name 1",
                "default_addr_type": "msisdn",
                "personnel_code": "12345",
                "addresses": {
                    "msisdn": {"+27123": {"optedout": True}},
                    "email": {
                        "foo1@bar.com": {"default": True, "optedout": True},
                        "foo2@bar.com": {"optedout": True},
                    },
                },
            },
        )

    @responses.activate
    def test_optout_forget_remove_address(self):
        """
        When a forget optout is created the msisdn should be removed.
        """
        # Setup
        post_save.connect(receiver=handle_optout, sender=OptOut)
        user = User.objects.get(username="testuser")
        identity = self.make_identity()

        optout = OptOut.objects.create(
            identity=identity,
            created_by=user,
            request_source="test_source",
            requestor_source_id=1,
            address_type="msisdn",
            address="+27123",
            optout_type="forget",
        )

        optout.refresh_from_db()

        self.assertEqual(optout.address, "redacted")

    @responses.activate
    def test_optout_forget_remove_address_from_optin(self):
        """
        When a forget optout is created the msisdn should be removed from all
        optins for the identity.
        """
        # Setup
        post_save.connect(receiver=handle_optout, sender=OptOut)
        user = User.objects.get(username="testuser")
        identity = self.make_identity()

        optin = OptIn.objects.create(
            identity=identity,
            created_by=user,
            request_source="test_source",
            requestor_source_id=1,
            address_type="msisdn",
            address="+27123",
        )

        OptOut.objects.create(
            identity=identity,
            created_by=user,
            request_source="test_source",
            requestor_source_id=1,
            address_type="msisdn",
            address="+27123",
            optout_type="forget",
        )

        optin.refresh_from_db()

        self.assertEqual(optin.address, "redacted")


class TestHealthcheckAPI(AuthenticatedAPITestCase):
    def test_healthcheck_read(self):
        # Setup
        # Execute
        response = self.client.get("/api/health/", content_type="application/json")
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["up"], True)
        self.assertEqual(response.data["result"]["database"], "Accessible")


class TestMetricsAPI(AuthenticatedAPITestCase):
    def test_metrics_read(self):
        # Setup
        # Execute
        response = self.client.get("/api/metrics/", content_type="application/json")
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(sorted(response.data["metrics_available"]), sorted([]))

    @responses.activate
    def test_post_metrics(self):
        # Setup
        # deactivate Testsession for this test
        self.session = None
        responses.add(
            responses.POST,
            "http://metrics-url/metrics/",
            json={"foo": "bar"},
            status=200,
            content_type="application/json",
        )
        # Execute
        response = self.client.post("/api/metrics/", content_type="application/json")
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["scheduled_metrics_initiated"], True)


class TestMetrics(AuthenticatedAPITestCase):
    @responses.activate
    def test_update_msisdn_metric(self):
        """
        When a MSISDN is changed on a identity, a sum metric should be fired
        """
        before = (
            REGISTRY.get_sample_value(
                "identities_address_change_total", {"type": "msisdn"}
            )
            or 0
        )
        identity = self.make_identity()
        new_details = {
            "addresses": {
                "msisdn": {"+27123999": {}},
                "email": {"foo1@bar.com": {}, "foo2@bar.com": {}},
            }
        }

        # Execute
        identity.details = new_details
        identity.save()

        # Check
        after = REGISTRY.get_sample_value(
            "identities_address_change_total", {"type": "msisdn"}
        )
        self.assertEqual(1, after - before)

    @responses.activate
    def test_update_msisdn_metric_negative(self):
        """
        When the details of the identity is updated and the MSISDN remains the
        same, no metric request should be made
        """
        before = (
            REGISTRY.get_sample_value(
                "identities_address_change_total", {"type": "msisdn"}
            )
            or 0
        )
        identity = self.make_identity()
        new_details = {
            "addresses": {
                "msisdn": {"+27123": {}},
                "email": {"foo1@bar.com": {}, "foo2@bar.com": {}},
            }
        }

        # Execute
        identity.details = new_details
        identity.save()

        # Check
        after = REGISTRY.get_sample_value(
            "identities_address_change_total", {"type": "msisdn"}
        )
        self.assertEqual(0, after - before)

    @responses.activate
    def test_update_email_metric(self):
        """
        When a email is changed on a identity, a sum metric should be fired
        """
        before = (
            REGISTRY.get_sample_value(
                "identities_address_change_total", {"type": "email"}
            )
            or 0
        )
        identity = self.make_identity()
        new_details = {
            "addresses": {
                "msisdn": {"+27123": {}},
                "email": {"foo1_new@bar.com": {}, "foo2@bar.com": {}},
            }
        }

        # Execute
        identity.details = new_details
        identity.save()

        # Check
        after = REGISTRY.get_sample_value(
            "identities_address_change_total", {"type": "email"}
        )
        self.assertEqual(1, after - before)
