from django.contrib import admin

from .models import Identity, OptOut, OptIn

admin.site.register(Identity)
admin.site.register(OptOut)
admin.site.register(OptIn)
