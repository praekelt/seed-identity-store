import json
import uuid
import requests
from celery.task import Task
from django.conf import settings
from go_http.metrics import MetricsApiClient
from .models import Identity, DetailKey
from seed_papertrail.decorators import papertrail


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
                'Content-Type': 'application/json',
                'Authorization': 'Token %s' % settings.HOOK_AUTH_TOKEN
            }
        )


def deliver_hook_wrapper(target, payload, instance, hook):
    if instance is not None:
        if isinstance(instance.id, uuid.UUID):
            instance_id = str(instance.id)
        else:
            instance_id = instance.id
    else:
        instance_id = None
    kwargs = dict(target=target, payload=payload,
                  instance_id=instance_id, hook_id=hook.id)
    DeliverHook.apply_async(kwargs=kwargs)


def get_metric_client(session=None):
    return MetricsApiClient(
        auth_token=settings.METRICS_AUTH_TOKEN,
        api_url=settings.METRICS_URL,
        session=session)


class FireMetric(Task):

    """ Fires a metric using the MetricsApiClient
    """
    name = "seed_identity_store.identities.tasks.fire_metric"

    @papertrail.debug(name)
    def run(self, metric_name, metric_value, session=None, **kwargs):
        metric_value = float(metric_value)
        metric = {
            metric_name: metric_value
        }
        try:
            metric_client = get_metric_client(session=session)
            metric_client.fire(metric)
            return "Fired metric <%s> with value <%s>" % (
                metric_name, metric_value)
        except (requests.exceptions.HTTPError,) as e:
            return "Failed to fire metric <%s> with value <%s> because %s" % (
                metric_name, metric_value, e)


fire_metric = FireMetric()


class ScheduledMetrics(Task):

    """ Fires off tasks for all the metrics that should run
        on a schedule
    """
    name = "seed_identity_store.subscriptions.tasks.scheduled_metrics"

    @papertrail.debug(name)
    def run(self, **kwargs):
        globs = globals()  # execute globals() outside for loop for efficiency
        for metric in settings.METRICS_SCHEDULED_TASKS:
            globs[metric].apply_async()

        return "%d Scheduled metrics launched" % len(
            settings.METRICS_SCHEDULED_TASKS)


scheduled_metrics = ScheduledMetrics()


class FireCreatedLast(Task):

    """ Fires last created subscriptions count
    """
    name = "seed_identity_store.subscriptions.tasks.fire_created_last"

    @papertrail.debug(name)
    def run(self):
        created_identities = Identity.objects.all().count()
        return fire_metric.apply_async(kwargs={
            "metric_name": 'identities.created.last',
            "metric_value": created_identities
        })


fire_created_last = FireCreatedLast()


class PopulateDetailKey(Task):

    """ Fires last created subscriptions count
    """
    name = "seed_identity_store.identities.tasks.populate_detail_key"

    @papertrail.debug(name)
    def run(self, key_names):
        existing_keys = DetailKey.objects.values_list('key_name', flat=True)
        # get key_names NOT in existing_keys
        new_items = [n for n in key_names if n not in existing_keys]
        for i in new_items:
            DetailKey.objects.create(key_name=i)
        return "Added <%s> new DetailKey records" % len(new_items)


populate_detail_key = PopulateDetailKey()
