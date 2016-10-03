===========
Data Models
===========

Identity
========

The Identity is the primary model of the Seed Identity Store. Each record
represents a unique user identity.

Fields
------

**id**
    A UUID 4 unique identifier for the record.

**version**
    An integer number representing the schema version number that this record
    was created with.

**details**
    A JSON fields containing extra details of the identity record. It should
    always contain at least an addresses key with the following structure:

    .. code-block: json

        "addresses": {
            "msisdn": {
                "+27123": {}
            },
            "email": {
                "foo1@bar.com": {"default": True},
                "foo2@bar.com": {"optedout": True}
            }
        }

**communicate_through**
    A self-referencing link to another Identity record that should be used
    instead of this record when trying to communicate directly with an end-user.

**operator**
    A self-referencing link to another Identity record that represents the
    operator that created this record.

**created_at**
    A date and time field of when the record was created.

**updated_at**
    A date and time field of when the record was last updated.

**created_by**
    A reference to the User account that created this record.

**updated_by**
    A reference to the User account that last updated this record.


OptIn
=====

**id**
    A UUID 4 unique identifier for the record.

**identity**
    A reference to an Identity record.

**address_type**
    The address type used to identify the Identity.

**address**
    The address used to identify the Identity

**request_source**
    The Service that the OptIn was requested from.

**requestor_source_id**
    The ID for the user requesting the OptIn on the service that it was
    requested from. Ideally a UUID.

**created_at**
    A date and time field of when the record was created.

**created_by**
    A reference to the User account that created this record.


OptOut
======

**id**
    A UUID 4 unique identifier for the record.

**identity**
    A reference to an Identity record.

**optout_type**
    A field representing a fixed set of reasons for the OptOut:

        * stop -> No communication on address
        * stopall -> No communication on all addresses
        * unsubscribe -> Unsubcribe
        * forget -> Forget

**reason**
    An optional reason (e.g. 'not interested') for the OptOut.

**address_type**
    The address type used to identify the Identity.

**address**
    The address used to identify the Identity

**request_source**
    The Service that the OptOut was requested from.

**requestor_source_id**
    The ID for the user requesting the OptOut on the service that it was
    requested from. Ideally a UUID.

**created_at**
    A date and time field of when the record was created.

**created_by**
    A reference to the User account that created this record.
