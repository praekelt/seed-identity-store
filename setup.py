import codecs
import os
import re

from setuptools import find_packages, setup

HERE = os.path.abspath(os.path.dirname(__file__))


def read(*parts):  # Stolen from txacme
    with codecs.open(os.path.join(HERE, *parts), "rb", "utf-8") as f:
        return f.read()


def get_version(package):
    """
    Return package version as listed in `__version__` in `init.py`.
    """
    init_py = open(os.path.join(package, "__init__.py")).read()
    return re.search("__version__ = ['\"]([^'\"]+)['\"]", init_py).group(1)


version = get_version("seed_identity_store")


setup(
    name="seed-identity-store",
    version=version,
    url="http://github.com/praekelt/seed-identity-store",
    license="BSD",
    description="Seed Identity Store mircoservice",
    long_description=read("README.rst"),
    author="Praekelt.org",
    author_email="dev@praekelt.org",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "Django==2.1.4",
        "djangorestframework==3.9.0",
        "coreapi==2.3.3",
        "dj-database-url==0.5.0",
        "psycopg2==2.7.6.1",
        "raven==6.9.0",
        "django-filter==2.0.0",
        "celery==4.2.1",
        "django-rest-hooks==1.5.0",
        "seed-services-client>=0.31.0",
        "seed-papertrail>=1.5.1",
        "django-prometheus==1.0.15",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Framework :: Django",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
