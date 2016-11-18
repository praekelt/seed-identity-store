# seed-identity-store
Seed Identity Store

## Apps & Models:
  * identities
    * Identity
    * Optout
    * Optin

## Metrics
##### identities.created.sum
`sum` Total number of identities created


## Understanding the `details` field

When a new unrecognised number dials into a USSD app, it will create an Identity for them. This Identity's `details` will typically look like this:
```
    details: {
        "addresses": {
            "msisdn": {
                "+27123": {"default": True}
            }
        },
        "default_addr_type": "msisdn"
    }
```

If they complete a registration, we would typically store additional information in the `details` field. This additional information is up to the user to define, e.g.:
```
    details: {
        "addresses": {
            "msisdn": {
                "+27123": {"default": True}
            }
        },
        "default_addr_type": "msisdn",
        "name": "Bob the Builder",
        "favourite_drink": "water",
        "important_dates": {
            "date_of_birth": "2000-01-01",
            "wedding_date": 2020-01-01"
        }
    }
```


## Understanding `addresses` handling

### Multiple addresses for one Identity
The `addresses` object is meant to hold all communication channel information we have for an Identity (similar to contacts on a phone). For instance, for one Identity it might look as follows:
```
    "addresses": {
        "msisdn": {
            "+27123": {"default": True},
            "+27124": {"description": "work cellphone"},
            "+27125": {}
        },
        "email": {
            "bob@example.com": {"default: True"},
            "bob@anotherexample.com": {}
        },
        "facebook": {
            "bobsfacebookid": {}
        }
    },
    "default_addr_type": "email"
```
In the example above, since Bob's `default_addr_type` is "email", any message that could be sent via any of the channels messages should be sent via email. But if we need to issue an emergency announcement, we could also contact him via his msisdn.

The {"default": True} parameter on an msisdn is used to determine which address within an address type determines the default address to contact someone on. For instance, if we wanted to send Bob an SMS, this informs which msisdn to send to (in Bob's case +27123).

### Opting out
Optout is a seperate model that keeps track of all optout requests, and updates the Identity. An optout can be created by making a Post request to the `/optout` endpoint. There are four options for an optout: stop (default), stopall, unsubscribe and forget.

"stop" will add `"optedout": True` to one address's details
e.g. Bob "stop" +27123:
```
    "addresses": {
        "msisdn": {
            "+27123": {"default": True, "optedout": True},
            "+27124": {"description": "work cellphone"},
            "+27125": {}
        },
        "email": {
            "bob@example.com": {"default: True"},
            "bob@anotherexample.com": {}
        },
        "facebook": {
            "bobsfacebookid": {}
        }
    },
    "default_addr_type": "email"
```

"stopall" will add `"opted_out": True` to all the addresses' details.
e.g. Bob "stopall":
```
    "addresses": {
        "msisdn": {
            "+27123": {"default": True, "optedout": True},
            "+27124": {"description": "work cellphone", "optedout": True},
            "+27125": {"optedout": True}
        },
        "email": {
            "bob@example.com": {"default: True", "optedout": True},
            "bob@anotherexample.com": {"optedout": True}
        },
        "facebook": {
            "bobsfacebookid": {"optedout": True}
        }
    },
    "default_addr_type": "email"
```

"unsubscribe" is not implemented.

"forget" redacts all the Identity's details.
e.g. Bob "forget":
```
    details: {
        "addresses": {}
        "default_addr_type": "redacted",
        "name": "redacted",
        "favourite_drink": "redacted",
        "important_dates": "redacted"
    }
```

### Opting in
Optin is a seperate model that keeps track of all optin requests, and updates the Identity. An optin can be created by making a Post request to the `/optin` endpoint. Only one address can be opted in at a time. This sets {"optedout": False} on the address, whether the "optedout" detail was there before or not.

e.g. Bob opts in +27123 after previously opting out +27123:
```
    "addresses": {
        "msisdn": {
            "+27123": {"default": True, "optedout": False},
            "+27124": {"description": "work cellphone"},
            "+27125": {}
        },
        "email": {
            "bob@example.com": {"default: True"},
            "bob@anotherexample.com": {}
        },
        "facebook": {
            "bobsfacebookid": {}
        }
    },
    "default_addr_type": "email"
```

and then Bob opts in +27125:
```
    "addresses": {
        "msisdn": {
            "+27123": {"default": True, "optedout": False},
            "+27124": {"description": "work cellphone"},
            "+27125": {"optedout": False}
        },
        "email": {
            "bob@example.com": {"default: True"},
            "bob@anotherexample.com": {}
        },
        "facebook": {
            "bobsfacebookid": {}
        }
    },
    "default_addr_type": "email"
```

### Changing addresses
Currently, an address can only be changed by making a Patch request to the Identity and passing in the changed address. For example, you could change this:
```
    details: {
        "addresses": {
            "msisdn": {
                "+27123": {"default": True}
            }
        },
        "default_addr_type": "msisdn"
    }
```
to this:
```
    details: {
        "addresses": {
            "msisdn": {
                "+27124": {"default": True},
            }
        },
        "default_addr_type": "msisdn"
    }
```
However, it is often useful to keep track of an Identity's old addresses. This can be handled by setting {"inactive": True} on an old address, for instance:
```
    details: {
        "addresses": {
            "msisdn": {
                "+27123": {"inactive": True},
                "+27124": {"default": True},
            }
        },
        "default_addr_type": "msisdn"
    }
```


### Looking up an identity's addresses
IdentityAddresses.get_queryset & utils.get_identity_address


### Finding an identity via an address
IdentitySearchList.get_queryset & seed-jsbox-utils.get_identity_by_address

