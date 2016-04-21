import uuid

from django.contrib.postgres.fields import JSONField
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.encoding import python_2_unicode_compatible
from django.core.exceptions import ValidationError
from rest_hooks.signals import raw_hook_event


class IdentityManager(models.Manager):

    def filter_by_addr(self, address_type, address):
        filter_string = "details__addresses__%s__has_key" % (address_type, )
        return self.filter(**{filter_string: address})


@python_2_unicode_compatible
class Identity(models.Model):

    """
    version: 1
    details should contain at minimum:
    addresses: structured like -
        "addresses": {
            "msisdn": {
                "+27123": {}
            },
            "email": {
                "foo1@bar.com": {"default": True},
                "foo2@bar.com": {"optedout": True}
            }
        }
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

    def serialize_hook(self, hook):
        return {
            'hook': hook.dict(),
            'data': {
                'id': str(self.id),
                'version': self.version,
                'details': self.details,
                'communicate_through': str(self.communicate_through),
                'operator': str(self.operator),
                'created_at': self.created_at.isoformat(),
                'created_by': self.created_by.username,
                'updated_at': self.updated_at.isoformat(),
                'updated_by': self.updated_by.username
            }
        }

    def __str__(self):
        return str(self.id)

    def remove_details(self, user):
        updated_details = {}
        for attribute, value in self.details.items():
            if attribute != "addresses":
                updated_details[attribute] = "redacted"
            else:
                updated_details[attribute] = {}
        self.details = updated_details
        self.communicate_through = None
        self.updated_by = user
        self.save()

    def optout_address(self, scope, address_type=None, address=None):
        # for each address type (e.g. email, msisdn, etc.)
        for cur_address_type, addresses in self.details["addresses"].items():
            if scope == "all" or cur_address_type == address_type:
                # for each address value (e.g. foo1@bar.com, +27123, etc.)
                for cur_address, cur_details in addresses.items():
                    if scope == "all" or cur_address == address:
                        cur_details["optedout"] = True
        self.save()


class OptOut(models.Model):
    """An optout"""
    OPTOUT_TYPE_CHOICES = (
        ('stop', "No communication on address"),
        ('stopall', "No communication on all addresses"),
        ('unsubscribe', "Unsubcribe"),
        ('forget', "Forget")
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False,
                          help_text="UUID of this optout request.")
    identity = models.ForeignKey(Identity, null=True,
                                 help_text="UUID for the identity opting out.")
    optout_type = models.CharField(
        null=False, max_length=20, default="stop", choices=OPTOUT_TYPE_CHOICES,
        help_text="Type of optout request.")
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
        null=True, max_length=500,
        help_text="ID for the user requesting the optout on the service that"
        " it was requested from. Ideally a UUID.")
    reason = models.CharField(
        null=True, max_length=200,
        help_text="Optional reason (e.g. 'not interested')")
    created_at = models.DateTimeField(auto_now_add=True,
                                      help_text="Time request was received.")
    created_by = models.ForeignKey(User, related_name='optout_created',
                                   null=True,
                                   help_text="User creating the OptOut")

    user = property(lambda self: self.created_by)

    def clean(self):
        """
        Don't allow optouts for non existant addresses or ambiguous ones
        This is a duplicte of the view code for DRF to stop future
        internal Django implementations breaking.
        """
        if self.identity is None:
            identities = Identity.objects.filter_by_addr(
                self.address_type, self.address)
            if len(identities) == 0:
                raise ValidationError(
                    "There is no identity with this address.")
            if len(identities) > 1:
                raise ValidationError(
                    "There are multiple identities with this address. "
                    "Please use an explict identity.")


@receiver(pre_save, sender=OptOut)
def optout_saved(sender, instance, **kwargs):
    """
    This is a duplicte of the view code for DRF to stop future
    internal Django implementations breaking.
    """
    if instance.identity is None:
        # look up using the address_type and address
        identities = Identity.objects.filter_by_addr(
            instance.address_type,
            instance.address)
        if identities.count() == 1:
            instance.identity = identities[0]


@receiver(post_save, sender=OptOut)
def handle_optout(sender, instance, created, **kwargs):
    if created is False or instance.identity is None:
        return

    identity = instance.identity

    raw_hook_event.send(
        sender=None,
        event_name='optout.requested',
        payload={
            'details': identity.details,
        },
        user=instance.user,
        send_hook_meta=False
    )

    if instance.optout_type == "forget":
        identity.remove_details(instance.user)
    elif instance.optout_type == "stop":
        identity.optout_address(scope="single",
                                address_type=instance.address_type,
                                address=instance.address)
    elif instance.optout_type == "stopall":
        identity.optout_address(scope="all")
