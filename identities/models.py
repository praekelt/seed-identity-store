import uuid
import datetime

from django.contrib.postgres.fields import JSONField
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.encoding import python_2_unicode_compatible
from rest_hooks.signals import raw_hook_event


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

    def remove_details(self, user):
        updated_details = {}
        for attribute, value in self.details.items():
            updated_details[attribute] = "removed"
        self.details = updated_details
        self.updated_by = user
        self.save()


class OptOut(models.Model):
    """An optout"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,
                          help_text="UUID of this optout request.")
    identity = models.ForeignKey(Identity, null=True,
                                 help_text="UUID for the identity opting out.")
    address_type = models.CharField(
        null=False, max_length=50, default="",
        help_text="Address type used to identify the identity.")
    address = models.CharField(
        null=False, max_length=255, default="",
        help_text="Address used to identify the identity.")
    request_source = models.CharField(
        null=False, max_length=100,
        help_text="Service that the optout was requested from.")
    requestor_source_id = models.CharField(
        null=True, max_length=100,
        help_text="ID for the user requesting the optout on the service that"
        " it was requested from.")
    created_at = models.DateTimeField(auto_now_add=True,
                                      help_text="Time request was received.")
    created_by = models.ForeignKey(User, related_name='optout_created',
                                   null=True,
                                   help_text="User creating the OptOut")

    user = property(lambda self: self.created_by)


@receiver(post_save, sender=OptOut)
def handle_optout(sender, instance, created, **kwargs):
    if created is False:
        return

    if instance.identity is not None:
        identity = instance.identity
    else:
        filter_string = \
            "details__addresses__" + instance.address_type + "__has_key"
        filter_value = instance.address
        identities = Identity.objects.filter(**{filter_string: filter_value})
        try:
            identity = identities[0]
        except IndexError:
            identity = Identity.objects.create(details={"addresses": {
                instance.address_type: {
                    instance.address: {}
                }
            }})
        instance.identity = identity
        instance.save()

    raw_hook_event.send(
        sender=None,
        event_name='optout.requested',
        payload={
            'details': identity.details,
        },
        user=instance.user,
        send_hook_meta=False
    )

    identity.remove_details(instance.user)
