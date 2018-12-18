============
Requirements
============

Overview
========

The Seed Identity Store requires the following dependencies to run:

* Python 3.6
* PostgreSQL >= 9.3
* Redis >= 2.10 or RabbitMQ >= 3.4 as the Celery Broker

Python requirements
===================

The full list of Python packages required are detailed in the project's
setup.py file, but the major ones are:

* Django 2.1
* Django REST Framework 3.9
* Celery 4.2

.. note::

    A celery worker needs to be running to process post-save tasks

Seed Requirements
=================

The Seed Identity Store doesn't depends on any other seed services
