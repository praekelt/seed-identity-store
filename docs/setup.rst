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
    running this command. See :ref:`configuration-options` for details.

#. Run the development server:

    .. code-block:: console

        $ python manage.py runserver

    This will run a development HTTP server. This is only suitable for testing
    and development, for production usage please see :ref:`running-in-production`

.. _configuration-options:

Configuration Options
=====================

The main configuration file is ``seed_identity_store/settings.py``.

The following environmental variables can be used to override some default settings:

.. envvar:: SECRET_KEY

SECRET_KEY
    This matches and overrides the Django :django:setting:`SECRET_KEY` setting.

.. envvar:: DEBUG

DEBUG
    This matches and overrides the Django :django:setting:`DEBUG` setting.

.. envvar:: IDENTITIES_DATABASE

IDENTITIES_DATABASE

.. envvar:: IDENTITIES_SENTRY_DSN

IDENTITIES_SENTRY_DSN

.. envvar:: HOOK_AUTH_TOKEN

HOOK_AUTH_TOKEN

.. envvar:: BROKER_URL

BROKER_URL

.. envvar:: METRICS_URL

METRICS_URL

.. envvar:: METRICS_AUTH_TOKEN

METRICS_AUTH_TOKEN

.. _running-in-production:

Running in Production
=====================



