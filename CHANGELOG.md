0.10.3 (2019-12-05)
-------------------
- Upgrade Django to 2.2.8 (Security vulnerability)

0.10.2 (2018-09-03)
-------------------
- Upgrade dependancies with security vulneribilities
- Cache auth token lookups
- Remove identity address change metric for performance
- Reduce number of DB queries for UpdateFailedMessageCount view

0.10.1 (2018-02-07)
-------------------
 - Add database index for created_at and updated_at timestamp fields on the
   Identity (#66)

0.10.0
------
 - Upgrade to Python 3, Django 2, Celery 4, and other dependancies
 - Add prometheus metrics endpoint
