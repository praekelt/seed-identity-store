import json
import uuid

import requests
from celery.task import Task
from django.conf import settings
from seed_papertrail.decorators import papertrail

from .models import DetailKey


class DeliverHook(Task):
    def run(self, target, payload, instance_id=None, hook_id=None, **kwargs):
        """
        target:     the url to receive the payload.
        payload:    a python primitive data structure
        instance_id:   a possibly None "trigger" instance ID
        hook_id:       the ID of defining Hook object
        """
        requests.post(
            url=target,
            data=json.dumps(payload),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Token %s" % settings.HOOK_AUTH_TOKEN,
            },
        )


def deliver_hook_wrapper(target, payload, instance, hook):
    if instance is not None:
        if isinstance(instance.id, uuid.UUID):
            instance_id = str(instance.id)
        else:
            instance_id = instance.id
    else:
        instance_id = None
    kwargs = dict(
        target=target, payload=payload, instance_id=instance_id, hook_id=hook.id
    )
    DeliverHook.apply_async(kwargs=kwargs)


class PopulateDetailKey(Task):

    """ Fires last created subscriptions count
    """

    name = "seed_identity_store.identities.tasks.populate_detail_key"

    @papertrail.debug(name)
    def run(self, key_names):
        existing_keys = DetailKey.objects.values_list("key_name", flat=True)
        # get key_names NOT in existing_keys
        new_items = [n for n in key_names if n not in existing_keys]
        for i in new_items:
            DetailKey.objects.create(key_name=i)
        return "Added <%s> new DetailKey records" % len(new_items)


populate_detail_key = PopulateDetailKey()
