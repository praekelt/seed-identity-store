from django.conf import settings
from identities.models import ADDRESS_TYPES


def get_available_metrics():
    available_metrics = []
    available_metrics.extend(settings.METRICS_REALTIME)
    available_metrics.extend(settings.METRICS_SCHEDULED)

    for a_type in ADDRESS_TYPES:
        available_metrics.append('identities.change.{}.sum'.format(a_type))

    return available_metrics
