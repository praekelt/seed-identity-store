from django import template

import seed_identity_store

register = template.Library()


@register.simple_tag
def current_version():
    return seed_identity_store.__version__
