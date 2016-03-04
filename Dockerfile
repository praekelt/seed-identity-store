FROM praekeltfoundation/django-bootstrap
ENV DJANGO_SETTINGS_MODULE "seed_identity_store.settings"
RUN django-admin collectstatic --noinput
CMD ["seed_identity_store.wsgi:application"]
