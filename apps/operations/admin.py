from django.contrib import admin

from apps.operations.models import (
    AuditEvent,
    PipelineRun,
    PipelineStepRun,
    ProviderCall,
    TaskOutbox,
)


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("pipeline_name", "stage", "status", "requested_by", "created_at")
    list_filter = ("status", "trigger", "pipeline_name")
    search_fields = ("idempotency_key", "request_id", "id")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(PipelineStepRun)
class PipelineStepRunAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("pipeline_run", "stage", "status", "attempt", "created_at")
    list_filter = ("status", "stage")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(TaskOutbox)
class TaskOutboxAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("command_type", "status", "attempts", "available_at", "created_at")
    list_filter = ("status", "command_type")
    search_fields = ("idempotency_key", "broker_message_id", "id")
    readonly_fields = tuple(field.name for field in TaskOutbox._meta.fields)

    def has_add_permission(self, _request: object) -> bool:
        return False

    def has_delete_permission(self, _request: object, _obj: object = None) -> bool:
        return False


@admin.register(ProviderCall)
class ProviderCallAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("provider", "operation", "status", "pipeline_run", "created_at")
    list_filter = ("provider", "operation", "status")
    readonly_fields = tuple(field.name for field in ProviderCall._meta.fields)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("occurred_at", "actor_type", "action", "object_type", "object_id")
    list_filter = ("actor_type", "action", "object_type")
    search_fields = ("request_id", "object_id", "action")
    readonly_fields = tuple(field.name for field in AuditEvent._meta.fields)

    def has_add_permission(self, _request: object) -> bool:
        return False

    def has_change_permission(self, _request: object, _obj: object = None) -> bool:
        return False

    def has_delete_permission(self, _request: object, _obj: object = None) -> bool:
        return False
