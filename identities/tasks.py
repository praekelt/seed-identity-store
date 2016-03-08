import json
import requests
from celery.task import Task
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


class The_Incr(Task):

    """
    Task to incr something
    """
    name = "seed_identity_store.identities.tasks.the_incr"

    def run(self, anum, **kwargs):
        """
        Returns an incr'd number
        """
        l = self.get_logger(**kwargs)
        l.info("Incrementing <%s>" % (anum,))
        return int(anum)+1

the_incr = The_Incr()


class DeliverHook(Task):
    def run(self, target, payload, instance=None, hook=None, **kwargs):
        """
        target:     the url to receive the payload.
        payload:    a python primitive data structure
        instance:   a possibly null "trigger" instance
        hook:       the defining Hook object
        """
        requests.post(
            url=target,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )

deliver_hook_wrapper = DeliverHook.delay
