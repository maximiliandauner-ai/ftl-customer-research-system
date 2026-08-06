from django.contrib import admin

from apps.sources.models import (
    FetchAttempt,
    SourceArtifact,
    SourceCandidate,
    SourceEndpoint,
    SourceSnapshot,
)


@admin.register(SourceCandidate)
class SourceCandidateAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("url_canonical", "origin", "status", "submitted_by", "created_at")
    list_filter = ("origin", "status")
    search_fields = ("url_original", "url_canonical", "company_name_hint")
    readonly_fields = ("id", "url_sha256", "request_id", "created_at")


@admin.register(SourceEndpoint)
class SourceEndpointAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("base_url_canonical", "provider_type", "status", "last_success_at")
    list_filter = ("provider_type", "status", "robots_policy")
    search_fields = ("base_url_canonical", "company__name")
    readonly_fields = ("id", "base_url_sha256", "created_at", "updated_at")


@admin.register(FetchAttempt)
class FetchAttemptAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("source_endpoint", "status", "http_status", "retryable", "started_at")
    list_filter = ("status", "network_policy", "retryable")
    search_fields = ("requested_url", "final_url", "error_code", "idempotency_key")
    readonly_fields = tuple(field.name for field in FetchAttempt._meta.fields)


@admin.register(SourceArtifact)
class SourceArtifactAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("sha256", "source_endpoint", "size_bytes", "content_type", "retrieved_at")
    search_fields = ("sha256", "storage_key", "source_endpoint__base_url_canonical")
    readonly_fields = tuple(field.name for field in SourceArtifact._meta.fields)


@admin.register(SourceSnapshot)
class SourceSnapshotAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("source_endpoint", "body_sha256", "content_type", "retrieved_at")
    search_fields = ("body_sha256", "source_endpoint__base_url_canonical")
    readonly_fields = tuple(field.name for field in SourceSnapshot._meta.fields)
