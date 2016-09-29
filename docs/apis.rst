===========
API Details
===========

The Seed Identity Store provides REST like API with JSON payloads.

The root URL for all of the endpoints is:

    :samp:`https://{<identity-store-domain>}/api/`


Authenticating to the API
=========================

Authentication to the Seed Identity Store API is provided the
`Token Authentication`_ feature of the `Django REST Framework`_.

.. _Django REST Framework: http://www.django-rest-framework.org/api-guide/authentication/#tokenauthentication
.. _Token Authentication: http://www.django-rest-framework.org/api-guide/authentication/#tokenauthentication

In short, each user of this API needs have been supplied a unique secret token
that must be provided in the ``Authorization`` HTTP header of every request made
to this API.

An example request with the ``Authorization`` header might look like this:

.. sourcecode:: http

   POST /endpoint/ HTTP/1.1
   Host: <identity-store-domain>
   Content-Type: application/json
   Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b


Endpoints
=========

The endpoints provided by the Seed Identity Store are split into two
categories, core endpoints and helper endpoints


Core
----

The root URL for all of the core endpoints includes the version prefix
(:samp:`https://{<identity-store-domain>}/api/v1/`)

Users and Groups
~~~~~~~~~~~~~~~~

.. http:get:: /user/

.. http:get:: /user/(int:user_id)/

.. http:post:: /user/token/

.. http:get:: /group/

.. http:get:: /group/(int:group_id)/

Identities
~~~~~~~~~~~

.. http:get:: /identities/

.. http:post:: /identities/

.. http:get:: /identities/(uuid:identity_id)/

.. http:put:: /identities/(uuid:identity_id)/

.. http:delete:: /identities/(uuid:identity_id)/

.. http:get:: /identities/(uuid:identity_id)/addresses/(str:address_type)/

.. http:get:: /identities/search/

.. http:post:: /optout/

.. http:post:: /optin/

Other
~~~~~

.. http:get:: /detailkeys/

.. http:get:: /webhook/

.. http:post:: /webhook/

.. http:get:: /webhook/(int:webhook_id)/

.. http:put:: /webhook/(int:webhook_id)/

.. http:delete:: /webhook/(int:webhook_id)/


Helpers
-------

The root URL for the helper endpoints does not include a version prefix
(:samp:`https://{<identity-store-domain>}/api/`)

.. http:get:: /metrics/

.. http:post:: /metrics/

.. http:get:: /health/