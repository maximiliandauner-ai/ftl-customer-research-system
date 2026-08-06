from django.contrib import admin

from apps.providers.models import ModelCapability, ModelPolicy

admin.site.register(ModelCapability)
admin.site.register(ModelPolicy)
