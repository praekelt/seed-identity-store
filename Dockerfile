# TODO: Add production Dockerfile to
# https://github.com/praekeltfoundation/docker-seed
FROM praekeltfoundation/django-bootstrap:py3.6

COPY . /app
RUN pip install -e .

ENV DJANGO_SETTINGS_MODULE "seed_identity_store.settings"
RUN python manage.py collectstatic --noinput
CMD ["seed_identity_store.wsgi:application"]
