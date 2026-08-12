from django.contrib import admin

from apps.companies.models import (
    Company,
    CompanyAlias,
    CompanyDomain,
    CompanyFieldObservation,
    CompanyMergeReview,
    CompanyProfileRun,
    CompanyProfileSource,
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("name", "status", "company_type", "updated_at")
    list_filter = ("status", "company_type")
    search_fields = ("name", "legal_name", "normalized_name")
    readonly_fields = ("id", "normalized_name", "row_version", "created_at", "updated_at")


@admin.register(CompanyDomain)
class CompanyDomainAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("hostname_ascii", "company", "verification_status", "is_primary")
    list_filter = ("verification_status", "is_primary")
    search_fields = ("hostname_ascii", "company__name")


@admin.register(CompanyAlias)
class CompanyAliasAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("alias", "company", "verification_status")
    list_filter = ("verification_status",)
    search_fields = ("alias", "company__name")


@admin.register(CompanyMergeReview)
class CompanyMergeReviewAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("left_company", "right_company", "match_method", "state", "created_at")
    list_filter = ("state", "match_method")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(CompanyProfileRun)
class CompanyProfileRunAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("company", "status", "field_count", "parser_version", "created_at")
    list_filter = ("status", "parser_version")
    search_fields = ("company__name", "idempotency_key")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(CompanyProfileSource)
class CompanyProfileSourceAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("final_url", "source_kind", "retrieved_at", "size_bytes")
    list_filter = ("source_kind",)
    search_fields = ("final_url", "body_sha256")
    readonly_fields = tuple(field.name for field in CompanyProfileSource._meta.fields)


@admin.register(CompanyFieldObservation)
class CompanyFieldObservationAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("field_name", "value_text", "confidence", "applied", "created_at")
    list_filter = ("field_name", "applied", "extraction_method")
    search_fields = ("value_text", "evidence_excerpt")
    readonly_fields = tuple(field.name for field in CompanyFieldObservation._meta.fields)
