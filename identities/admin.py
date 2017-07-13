from django.contrib import admin

from .models import Identity, OptOut, OptIn


class IdentityAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "updated_at", "created_by",
                    "updated_by"]
    list_filter = ["created_at"]
    raw_id_fields = ['communicate_through', 'operator', 'created_by',
                     'updated_by']


class OptOutAdmin(admin.ModelAdmin):
    list_display = ["id", "identity", "optout_type", "address_type", "address",
                    "reason", "created_at", "created_by"]
    list_filter = ["optout_type", "address_type", "reason", "created_at",
                   "created_by"]
    search_fields = ["identity__id", "address"]
    raw_id_fields = ['identity', 'created_by']


class OptInAdmin(admin.ModelAdmin):
    list_display = ["id", "identity", "address_type", "address",
                    "created_at", "created_by"]
    list_filter = ["address_type", "created_at", "created_by"]
    search_fields = ["identity__id", "address"]
    raw_id_fields = ['identity', 'created_by']


admin.site.register(Identity, IdentityAdmin)
admin.site.register(OptOut, OptOutAdmin)
admin.site.register(OptIn, OptInAdmin)
