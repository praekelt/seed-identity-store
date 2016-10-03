===========
API Details
===========

The Seed Identity Store provides REST like API with JSON payloads.

The root URL for all of the endpoints is:

    :samp:`https://{<identity-store-domain>}/api/`


Authenticating to the API
=========================

Please see the :doc:`Authentication and Authorization <auth>` document.

Pagination
==========

When the results set is larger than a configured amount, the data is broken up
into pages using the limit and offset parameters.

Paginated endpoints will provide information about the total amount of items
available along with links to the previous and next pages (where available) in
the returned JSON data.

.. http:get:: /(any)/
    :noindex:

    :query limit: the amount of record to limit a page of results to.
    :query offset: the starting position of the query in relation to the complete set of unpaginated items
    :>json int count: the total number of results available
    :>json string previous: the URL to the previous page of results (if available)
    :>json string next: the URL to the next page of results (if available)

    **Example request**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Content-Type: application/json

        {
            "count": 50,
            "next": "http://sis.example.org/api/v1/enpoint/?limit=10&offset=30",
            "previous": "http://sis.example.org/api/v1/endpoint/?limit=10&offset=10",
            "results": []
        }


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

    Returns a list of users for the Seed Identity Store service.

    :status 200: no error.
    :status 401: the token is invalid/missing.

    **Example request**:

    .. sourcecode:: http

        GET /user/ HTTP/1.1
        Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Content-Type: application/json

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [
                {
                    "email": "john@example.org",
                    "groups": [],
                    "url": "http://sis.example.org/api/v1/user/1/",
                    "username": "john"
                }
            ]
        }

.. http:get:: /user/(int:user_id)/

    Returns the details of the specified user ID.

    :param user_id: a user's unique ID.
    :type user_id: int
    :status 200: no error.
    :status 401: the token is invalid/missing.

    **Example request**:

    .. sourcecode:: http

        GET /user/1/ HTTP/1.1
        Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Content-Type: application/json

        {
            "email": "john@example.org",
            "groups": [],
            "url": "http://sis.example.org/api/v1/user/1/",
            "username": "john"
        }

.. http:post:: /user/token/

    Creates a user and token for the given email address.

    If a user already exists for the given email address, the existing user
    account is used to generate a new token.

    :<json string email: the email address of the user to create or use.
    :>json string token: the auth token generated for the given user.
    :status 201: token successfully created.
    :status 400: an email address was not provided or was invalid.
    :status 401: the token is invalid/missing.


    **Example request**:

    .. sourcecode:: http

        POST /user/token/ HTTP/1.1
        Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b

        {
            "email": "bob@example.org"
        }


    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 201 Created
        Content-Type: application/json

        {
            "token": "c05fbab6d5f912429052830c77eeb022249324cb"
        }

.. http:get:: /group/

    Returns a list of groups for the Seed Identity Store service.

    :status 200: no error
    :status 401: the token is invalid/missing.

    **Example request**:

    .. sourcecode:: http

        GET /group/ HTTP/1.1
        Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b


    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Content-Type: application/json

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [
                {
                    "name": "Admins",
                    "url": "http://sis.example.org/api/v1/group/1/"
                }
            ]
        }

.. http:get:: /group/(int:group_id)/

    Returns the details of the specified group ID.

    :param group_id: a group's unique ID.
    :type group_id: int
    :status 200: no error.
    :status 401: the token is invalid/missing.

    **Example request**:

    .. sourcecode:: http

        GET /group/1/ HTTP/1.1
        Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b


    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Content-Type: application/json

        {
            "name": "Admins",
            "url": "http://sis.example.org/api/v1/group/1/"
        }

Identities
~~~~~~~~~~~

.. http:get:: /identities/

    Returns a list of identities.

    :status 200: no error.
    :status 401: the token is invalid/missing.

    **Example request**:

    .. sourcecode:: http

        GET /identities/ HTTP/1.1
        Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b

    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 200 OK
        Content-Type: application/json

        {
            "count": 1,
            "next": null,
            "previous": null,
            "results": [
            ]
        }

.. http:post:: /identities/

    Create a new identity.

    :<json int version: optional version number of the Identity schema being used.
    :<json json details: a JSON object representing the Identity details
    :<json string communicate_through: optional URL to another identity that represents an Identity to communicate through.
    :<json string operator: optional optional URL to another identity that presents an operator that is responsible for this Identity

    :>json uuid id: the UUID of this Identity
    :>json int version: the version number of the Identity schema being used.
    :>json json details: the JSON object representing the Identity details
    :>json url communicate_through: URL to another identity that represents an Identity to communicate through.
    :>json url operator: URL to another identity that presents an operator that is responsible for this Identity
    :>json datetime created_at: the date and time this Identity was created
    :>json datetime created_by: the ID of the user that created this Identity
    :>json datetime updated_at: the date and time this Identity was last updated
    :>json datetime updated_by: the ID of the user that created this Identity

    :status 201: identity successfully created.
    :status 400: the details field was not provided or was invalid.
    :status 401: the token is invalid/missing.

    **Example request**:

    .. sourcecode:: http

        POST /user/ HTTP/1.1
        Authorization: Token 9944b09199c62bcf9418ad846dd0e4bbdfc6ee4b

        {
            "details": {
                "addresses": {
                "msisdn": {
                    "+27115551234": {}
                },
            },
            "version": 1
        }


    **Example response**:

    .. sourcecode:: http

        HTTP/1.1 201 Created
        Content-Type: application/json

        {
            "communicate_through": null,
            "created_at": "2016-09-30T11:10:21.693326Z",
            "created_by": 1,
            "details": {
                "addresses": {
                   "msisdn": {
                        "+27115551234": {}
                    }
                }
            }
        }
            },
            "id": "4be7c1f9-f3a1-4bb3-ade7-a193ca2e79d0",
            "operator": null,
            "updated_at": "2016-09-30T11:10:21.693364Z",
            "updated_by": 1,
            "version": 1
        }

.. http:get:: /identities/(uuid:identity_id)/

    Returns the Identity record for a given UUID.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:put:: /identities/(uuid:identity_id)/

    Update the Identity record for the given UUID.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:delete:: /identities/(uuid:identity_id)/

    Delete the Identity record for the given UUID.

    :status 204: delete successfully completed.
    :status 401: the token is invalid/missing.

.. http:get:: /identities/(uuid:identity_id)/addresses/(str:address_type)/

    Searches address by a given type for a given Identity.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:get:: /identities/search/

    Search Identity records by specifying Django filter keys as query
    parameters.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:post:: /optout/

    Create an OptOut record.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:post:: /optin/

    Create an OptIn record.

    :status 200: no error
    :status 401: the token is invalid/missing.

Other
~~~~~

.. http:get:: /detailkeys/

    Returns a list of all the unique keys stored in any `detail` field of an
    Identity record.

    This list is populated by a post-save signal on the Identity record.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:get:: /webhook/

    Returns a list of setup webhooks.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:post:: /webhook/

    Creates a webhook.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:get:: /webhook/(int:webhook_id)/

    Get the details of a webhook specified by webhook_id.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:put:: /webhook/(int:webhook_id)/

    Updates the details of a webhook specified by webhook_id.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:delete:: /webhook/(int:webhook_id)/

    Deletes the webhook specified by webhook_id.

    :status 200: no error
    :status 401: the token is invalid/missing.


Helpers
-------

The root URL for the helper endpoints does not include a version prefix
(:samp:`https://{<identity-store-domain>}/api/`)

.. http:get:: /metrics/
    :noindex:

    Returns a list of all the available metric keys provided by this service.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:post:: /metrics/
    :noindex:

    Starts a task that fires all scheduled metrics.

    :status 200: no error
    :status 401: the token is invalid/missing.

.. http:get:: /health/
    :noindex:

    Returns a basic health check status.

    :status 200: no error
    :status 401: the token is invalid/missing.
