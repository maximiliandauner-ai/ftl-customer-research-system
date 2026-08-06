from django.contrib import admin

from apps.accounts.models import TeamRole


@admin.register(TeamRole)
class TeamRoleAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("user", "role", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")
