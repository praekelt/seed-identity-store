=====
Setup
=====

Installing
==========

The steps required to install the Seed Identity Service are:

#. Get the code from the `Github Project`_ with git:

    .. code-block:: console

        $ git clone https://github.com/praekelt/seed-identity-store.git

    This will create a directory ``seed-identity-store`` in your current directory.

.. _Github Project: https://github.com/praekelt/seed-identity-store/

#. Install the Python requirements with pip:

    .. code-block:: console

        $ pip install -r requirements.txt

    This will download and install all the Python packages required to run the
    project.

#. Setup the database:

    .. code-block:: console

        $ python manage migrate

    This will create all the database tables required.

    .. note::
        The PostgreSQL database for the Seed Identity Store needs to exist before
        running this command. See :envvar:`IDENTITIES_DATABASE` for details.

#. Run the development server:

    .. code-block:: console

        $ python manage.py runserver

    .. note::
        This will run a development HTTP server. This is only suitable for
        testing and development, for production usage please
        see :ref:`running-in-production`

.. _configuration-options:

Configuration Options
=====================

The main configuration file is ``seed_identity_store/settings.py``.

The following environmental variables can be used to override some default settings:

.. envvar:: SECRET_KEY

    This overrides the Django :django:setting:`SECRET_KEY` setting.

.. envvar:: DEBUG

    This overrides the Django :django:setting:`DEBUG` setting.

.. envvar:: IDENTITIES_DATABASE

    The database parameters to use as a URL in the format specified by the
    `DJ-Database-URL`_ format.

.. _DJ-Database-URL: https://github.com/kennethreitz/dj-database-url

.. envvar:: IDENTITIES_SENTRY_DSN

    The DSN to the Sentry instance you would like to log errors to.

.. envvar:: HOOK_AUTH_TOKEN

    An Authorization Token to use when making a POST request to a webhook.

.. envvar:: BROKER_URL

    The Broker URL to use with Celery.

.. envvar:: METRICS_URL

    The URL to the `Go Metrics API`_ instance to push metrics to.

.. _Go Metrics API: https://github.com/praekelt/go-metrics-api

.. envvar:: METRICS_AUTH_TOKEN

    The `auth token` to use to connect to the `Go Metrics API`_ above.
