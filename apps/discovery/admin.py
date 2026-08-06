from django.contrib import admin

from apps.discovery.models import (
    DiscoveryCandidate,
    DiscoveryQuery,
    DiscoveryRun,
    EndpointWatch,
    SearchDefinition,
)


@admin.register(SearchDefinition)
class SearchDefinitionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("definition_key", "version", "name", "active", "schedule_key", "created_at")
    list_filter = ("active", "schedule_key", "language")
    search_fields = ("definition_key", "name", "description")
    readonly_fields = ("payload_sha256", "created_at")


@admin.register(DiscoveryRun)
class DiscoveryRunAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "definition",
        "run_reason",
        "status",
        "known_endpoints_queued",
        "candidates_found",
        "created_at",
    )
    list_filter = ("status", "run_reason")
    readonly_fields = ("idempotency_key", "created_at", "updated_at")


admin.site.register(DiscoveryQuery)
admin.site.register(DiscoveryCandidate)
admin.site.register(EndpointWatch)
