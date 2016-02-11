import uuid

from django.contrib.postgres.fields import JSONField
from django.contrib.auth.models import User
from django.db import models
from django.utils.encoding import python_2_unicode_compatible


class IdentityManager(models.Manager):

    def filter_by_addr(self, addr):
        # expects "addr_type:add" e.g. "msisdn:+123"
        return self.filter(details__addresses__contains=addr)


@python_2_unicode_compatible
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
    communicate_through = models.ForeignKey(
        'self', related_name='identities_communicate_through',
        null=True, blank=True)
    operator = models.ForeignKey(
        'self', related_name='identities_created_by',
        null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, related_name='identities_created',
                                   null=True)
    updated_by = models.ForeignKey(User, related_name='identities_updated',
                                   null=True)
    user = property(lambda self: self.created_by)

    objects = IdentityManager()

    def __str__(self):
        return str(self.id)
