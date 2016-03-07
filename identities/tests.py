import json

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from .models import Identity, OptOut

TEST_IDENTITY1 = {
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
TEST_IDENTITY2 = {
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
}
TEST_IDENTITY3 = {
    "version": 2,
    "details": {
        "name": "Test Name 3",
        "addresses": {
            "msisdn": {
                "+27555": {}
            }
        }
    }
}
TEST_OPTOUT = {
    "identity": "/api/v1/identities/1/",
    "request_source": "test_source",
    "request_source_id": 1
}


class APITestCase(TestCase):

    def setUp(self):
        self.client = APIClient()


class AuthenticatedAPITestCase(APITestCase):

    def make_identity(self, id_data=TEST_IDENTITY1):
        return Identity.objects.create(**id_data)

    def setUp(self):
        super(AuthenticatedAPITestCase, self).setUp()
        self.username = 'testuser'
        self.password = 'testpass'
        self.user = User.objects.create_user(self.username,
                                             'testuser@example.com',
                                             self.password)
        token = Token.objects.create(user=self.user)
        self.token = token.key
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token)


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


class TestIdentityAPI(AuthenticatedAPITestCase):

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

    def test_read_identity_search_single(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data=TEST_IDENTITY2)
        self.make_identity(id_data=TEST_IDENTITY3)
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"details__addresses__msisdn": "+27555"},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["details"]["name"], "Test Name 3")

    def test_read_identity_search_multiple(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data=TEST_IDENTITY2)
        self.make_identity(id_data=TEST_IDENTITY3)
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"details__addresses__msisdn": "+27123"},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_read_identity_search_email(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data=TEST_IDENTITY2)
        self.make_identity(id_data=TEST_IDENTITY3)
        # Execute
        response = self.client.get(
            '/api/v1/identities/search/',
            {"details__addresses__email": "foo1@bar.com"},
            content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["details"]["name"], "Test Name 1")

    def test_read_identity_search_personnel_code(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data=TEST_IDENTITY2)
        self.make_identity(id_data=TEST_IDENTITY3)
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"details__personnel_code": "23456"},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["details"]["name"], "Test Name 2")

    def test_read_identity_search_version(self):
        # Setup
        self.make_identity()
        self.make_identity(id_data=TEST_IDENTITY2)
        self.make_identity(id_data=TEST_IDENTITY3)
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"version": 2},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["details"]["name"], "Test Name 3")

    def test_read_identity_search_communicate_through(self):
        # Setup
        self.make_identity()
        test_id2 = self.make_identity(id_data=TEST_IDENTITY2)
        test_id3 = TEST_IDENTITY3.copy()
        test_id3["communicate_through"] = test_id2
        self.make_identity(id_data=test_id3)
        # Execute
        response = self.client.get('/api/v1/identities/search/',
                                   {"communicate_through": str(test_id2.id)},
                                   content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["details"]["name"], "Test Name 3")

    def test_update_identity(self):
        # Setup
        identity = self.make_identity()
        new_details = {
            "details": {
                "name": "Changed Name",
                "default_addr_type": "email"
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
        identity2 = self.make_identity(id_data=TEST_IDENTITY2)
        post_identity = {
            "communicate_through": '/api/v1/identities/%s/' % identity1.id,
            "operator": '/api/v1/identities/%s/' % identity2.id,
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


class TestOptOutAPI(AuthenticatedAPITestCase):
    def test_create_opt_out(self):
        # Setup
        identity = self.make_identity()
        opt_out = TEST_OPTOUT
        opt_out["identity"] = reverse('identity-detail',
                                      kwargs={'pk': identity.pk})
        # Execute
        response = self.client.post('/api/v1/optout/',
                                    json.dumps(opt_out),
                                    content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        d = OptOut.objects.get(id=response.data["id"])
        self.assertEqual(d.identity, identity)
        self.assertEqual(d.request_source, "test_source")
        self.assertEqual(d.request_source_id, '1')
