from django.contrib import admin

from apps.companies.models import (
    Company,
    CompanyAlias,
    CompanyDomain,
    CompanyMergeReview,
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
