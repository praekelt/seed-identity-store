import json
import responses

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db.models.signals import post_save
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from rest_hooks.models import Hook

from .models import Identity, OptOut, handle_optout
from .tasks import deliver_hook_wrapper


class APITestCase(TestCase):

    def setUp(self):
        self.client = APIClient()


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

    def test_read_identity_search_multiple(self):
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
            {"details__addresses__email": "foo1@bar.com"},
            content_type='application/json')
        # Check
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["details"]["name"], "Test Name 1")

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
    def test_create_optout_with_identity(self):
        # Setup
        identity = self.make_identity()
        optout_data = {
            "request_source": "test_source",
            "requestor_source_id": "1",
            "address_type": "msisdn",
            "address": "+27123",
            "identity": reverse('identity-detail', kwargs={'pk': identity.pk})
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
            "details": {
                "addresses": {
                    "msisdn": {
                        "+27123": {}
                    }
                }
            }
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
            'details': identity.details,
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
            'details': identity.details,
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
            'details': identity.details,
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
