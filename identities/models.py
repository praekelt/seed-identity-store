import uuid

from django.contrib.postgres.fields import JSONField
from django.contrib.auth.models import User
from django.db import models


class IdentityManager(models.Manager):

    def filter_by_addr(self, addr):
        # expects "addr_type:add" e.g. "msisdn:+123"
        return self.filter(details__addresses__contains=addr)


class Identity(models.Model):

    """
    version: 1
    details should contain at minimum:
    addresses: addr_type:addr_value pairs
        (e.g. "msisdn:+27001 msisdn:+27002 email:foo@bar.com")
    default_addr_type: which addr_type in addresses to default to if non-given
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.IntegerField(default=1)
    details = JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, related_name='identities_created',
                                   null=True)
    updated_by = models.ForeignKey(User, related_name='identities_updated',
                                   null=True)
    user = property(lambda self: self.created_by)

    objects = IdentityManager()

    def __str__(self):  # __unicode__ on Python 2
        return str(self.id)

    def address(self, addr_type=None):
        """
        returns a list of all matches or empty list
        """
        found = []
        if addr_type is None and "default_addr_type" in self.details:
            addr_type = self.details["default_addr_type"]
        elif addr_type is None and "default_addr_type" not in self.details:
            # fall back to sensible default
            addr_type = "msisdn"
        if "addresses" in self.details:
            addresses = self.details["addresses"].split()
            for address in addresses:
                parts = address.split(":")
                if parts[0] == str(addr_type):
                    found.append(parts[1])
        return found
