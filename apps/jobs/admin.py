from django.contrib import admin

from apps.jobs.models import (
    ConnectorParseAttempt,
    DuplicateRelationship,
    EvidenceCatalog,
    EvidenceItem,
    JobLocation,
    JobPosting,
    JobPostingSnapshot,
    PostingChangeEvent,
    PostingObservation,
)


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("title", "company", "provider_type", "lifecycle_status", "last_seen_at")
    list_filter = ("provider_type", "lifecycle_status")
    search_fields = ("title", "company__name", "external_posting_id", "canonical_url")
    readonly_fields = ("id", "first_seen_at", "last_seen_at", "created_at", "updated_at")


@admin.register(JobLocation)
class JobLocationAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("display_text", "posting", "workplace_type", "remote")
    list_filter = ("workplace_type", "remote")


@admin.register(JobPostingSnapshot)
class JobPostingSnapshotAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("posting", "connector_key", "connector_version", "retrieved_at", "full_hash")
    search_fields = ("posting__title", "full_hash", "semantic_hash")
    readonly_fields = tuple(field.name for field in JobPostingSnapshot._meta.fields)


@admin.register(EvidenceCatalog)
class EvidenceCatalogAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("snapshot", "builder_version", "item_count", "created_at")
    readonly_fields = tuple(field.name for field in EvidenceCatalog._meta.fields)


@admin.register(EvidenceItem)
class EvidenceItemAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("public_id", "catalog", "field_path", "content_sha256")
    readonly_fields = tuple(field.name for field in EvidenceItem._meta.fields)


@admin.register(PostingObservation)
class PostingObservationAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("posting", "state", "observed_at", "source_snapshot")
    list_filter = ("state",)
    readonly_fields = tuple(field.name for field in PostingObservation._meta.fields)


@admin.register(ConnectorParseAttempt)
class ConnectorParseAttemptAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("source_snapshot", "connector_key", "status", "posting_count", "started_at")
    list_filter = ("status", "connector_key")
    readonly_fields = tuple(field.name for field in ConnectorParseAttempt._meta.fields)


@admin.register(PostingChangeEvent)
class PostingChangeEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("posting", "change_type", "occurred_at", "policy_version")
    list_filter = ("change_type", "policy_version")
    readonly_fields = tuple(field.name for field in PostingChangeEvent._meta.fields)


@admin.register(DuplicateRelationship)
class DuplicateRelationshipAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("primary_posting", "secondary_posting", "method", "review_status")
    list_filter = ("relationship_type", "method", "review_status")
