from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel, UUIDModel
from apps.operations.models import PipelineRun


class CompanyStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PROVISIONAL = "provisional", "Provisional"
    ARCHIVED = "archived", "Archived"
    MERGE_REVIEW = "merge_review", "Merge review"


class CompanyType(models.TextChoices):
    COMPANY = "company", "Company"
    NONPROFIT = "nonprofit", "Nonprofit"
    PUBLIC_BODY = "public_body", "Public body"
    AGENCY = "agency", "Agency"
    RECRUITER = "recruiter", "Recruiter"
    UNKNOWN = "unknown", "Unknown"


class EmployeeRange(models.TextChoices):
    ONE_TO_TEN = "1_10", "1-10"
    ELEVEN_TO_FIFTY = "11_50", "11-50"
    FIFTY_ONE_TO_TWO_HUNDRED = "51_200", "51-200"
    TWO_HUNDRED_ONE_TO_ONE_THOUSAND = "201_1000", "201-1,000"
    OVER_ONE_THOUSAND = "1001_plus", "1,001+"
    UNKNOWN = "unknown", "Unknown"


class DomainVerificationStatus(models.TextChoices):
    UNVERIFIED = "unverified", "Unverified"
    SOURCE_CONFIRMED = "source_confirmed", "Source confirmed"
    HUMAN_VERIFIED = "human_verified", "Human verified"
    DISPUTED = "disputed", "Disputed"


class AliasVerificationStatus(models.TextChoices):
    UNVERIFIED = "unverified", "Unverified"
    SOURCE_CONFIRMED = "source_confirmed", "Source confirmed"
    HUMAN_VERIFIED = "human_verified", "Human verified"
    DISPUTED = "disputed", "Disputed"


class MergeReviewState(models.TextChoices):
    OPEN = "open", "Open"
    CONFIRMED_SAME = "confirmed_same", "Confirmed same"
    CONFIRMED_DISTINCT = "confirmed_distinct", "Confirmed distinct"
    DISMISSED = "dismissed", "Dismissed"


class CompanyEnrichmentStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETE = "complete", "Complete"
    PARTIAL = "partial", "Partial"
    FAILED = "failed", "Failed"


class CompanyProfileSourceKind(models.TextChoices):
    HOMEPAGE = "homepage", "Homepage"
    IMPRINT = "imprint", "Imprint / legal notice"
    ABOUT = "about", "About / company page"
    OTHER = "other", "Other official page"


class CompanyProfileField(models.TextChoices):
    LEGAL_NAME = "legal_name", "Legal name"
    COMPANY_TYPE = "company_type", "Company type"
    INDUSTRY = "industry_key", "Industry"
    HEADQUARTERS_CITY = "headquarters_city", "Headquarters city"
    HEADQUARTERS_COUNTRY = "headquarters_country", "Headquarters country"
    EMPLOYEE_RANGE = "employee_range", "Employee range"
    DESCRIPTION = "description", "Description"


class Company(UUIDModel, TimeStampedModel):
    legal_name = models.TextField(blank=True)
    name = models.TextField()
    normalized_name = models.TextField(db_index=True)
    company_type = models.CharField(
        max_length=24,
        choices=CompanyType.choices,
        default=CompanyType.UNKNOWN,
    )
    industry_key = models.CharField(max_length=100, blank=True)
    headquarters_country = models.CharField(max_length=2, blank=True)
    headquarters_city = models.TextField(blank=True)
    employee_range = models.CharField(
        max_length=16,
        choices=EmployeeRange.choices,
        default=EmployeeRange.UNKNOWN,
    )
    description = models.TextField(blank=True)
    strategic_fit_manual = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=CompanyStatus.choices,
        default=CompanyStatus.PROVISIONAL,
    )
    row_version = models.PositiveBigIntegerField(default=1)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(strategic_fit_manual__isnull=True) | Q(strategic_fit_manual__lte=100),
                name="companies_strategic_fit_lte_100",
            ),
            models.CheckConstraint(
                condition=Q(status__in=CompanyStatus.values),
                name="companies_status_known",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def industry_display(self) -> str:
        return self.industry_key.replace("_", " ").capitalize() if self.industry_key else ""


class CompanyDomain(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="domains")
    hostname_ascii = models.TextField()
    hostname_unicode = models.TextField(blank=True)
    registrable_domain = models.TextField()
    is_primary = models.BooleanField(default=False)
    verification_status = models.CharField(
        max_length=24,
        choices=DomainVerificationStatus.choices,
        default=DomainVerificationStatus.UNVERIFIED,
    )
    verification_source_url = models.TextField(blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()

    class Meta:
        ordering = ("-is_primary", "hostname_ascii")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "hostname_ascii"),
                name="companies_domain_company_host_unique",
            ),
            models.UniqueConstraint(
                fields=("company",),
                condition=Q(is_primary=True),
                name="companies_one_primary_domain",
            ),
        ]
        indexes = [models.Index(fields=("hostname_ascii",), name="companies_domain_host")]

    def __str__(self) -> str:
        return self.hostname_ascii


class CompanyAlias(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="aliases")
    alias = models.TextField()
    normalized_alias = models.TextField()
    verification_status = models.CharField(
        max_length=24,
        choices=AliasVerificationStatus.choices,
        default=AliasVerificationStatus.UNVERIFIED,
    )
    verification_source_url = models.TextField(blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("alias",)
        constraints = [
            models.UniqueConstraint(
                fields=("company", "normalized_alias"),
                name="companies_alias_company_normalized_unique",
            )
        ]
        indexes = [models.Index(fields=("normalized_alias",), name="companies_alias_normalized")]

    def __str__(self) -> str:
        return self.alias


class CompanyMergeReview(UUIDModel, TimeStampedModel):
    left_company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="merge_reviews_as_left",
    )
    right_company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="merge_reviews_as_right",
    )
    match_method = models.CharField(max_length=64)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    evidence_source_ids = models.JSONField(default=list, blank=True)
    state = models.CharField(
        max_length=24,
        choices=MergeReviewState.choices,
        default=MergeReviewState.OPEN,
    )
    decision_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_merge_decisions",
    )
    decision_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=~Q(left_company=models.F("right_company")),
                name="companies_merge_distinct_companies",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0) & Q(confidence__lte=1),
                name="companies_merge_confidence_range",
            ),
            models.UniqueConstraint(
                fields=("left_company", "right_company"),
                condition=Q(state=MergeReviewState.OPEN),
                name="companies_one_open_merge_review_pair",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.left_company_id} / {self.right_company_id} / {self.state}"


class CompanyProfileRun(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="profile_runs",
    )
    pipeline_run = models.OneToOneField(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="company_profile_run",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_company_profile_runs",
    )
    status = models.CharField(
        max_length=16,
        choices=CompanyEnrichmentStatus.choices,
        default=CompanyEnrichmentStatus.QUEUED,
    )
    parser_version = models.CharField(max_length=32)
    idempotency_key = models.CharField(max_length=255, unique=True)
    source_urls = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    field_count = models.PositiveSmallIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=CompanyEnrichmentStatus.values),
                name="companies_profile_run_status_known",
            )
        ]
        permissions = [("request_company_enrichment", "Can request company profile enrichment")]

    def __str__(self) -> str:
        return f"{self.company_id} / {self.status} / {self.parser_version}"


class ImmutableCompanyProfileQuerySet(models.QuerySet[Any]):
    def update(self, **_kwargs: Any) -> int:
        raise TypeError("Company profile evidence records are immutable.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError("Company profile evidence records are immutable.")


class CompanyProfileSource(UUIDModel):
    enrichment_run = models.ForeignKey(
        CompanyProfileRun,
        on_delete=models.PROTECT,
        related_name="sources",
    )
    source_kind = models.CharField(max_length=16, choices=CompanyProfileSourceKind.choices)
    requested_url = models.TextField()
    final_url = models.TextField()
    canonical_url_sha256 = models.CharField(max_length=64)
    storage_key = models.TextField(unique=True)
    body_sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=255)
    encoding = models.CharField(max_length=64, blank=True)
    retrieved_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableCompanyProfileQuerySet.as_manager()

    class Meta:
        ordering = ("retrieved_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("enrichment_run", "canonical_url_sha256"),
                name="companies_profile_source_run_url_unique",
            ),
            models.CheckConstraint(
                condition=Q(source_kind__in=CompanyProfileSourceKind.values),
                name="companies_profile_source_kind_known",
            ),
            models.CheckConstraint(
                condition=Q(size_bytes__gte=1),
                name="companies_profile_source_size_gte_1",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("CompanyProfileSource records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("CompanyProfileSource records are immutable.")

    def __str__(self) -> str:
        return f"{self.final_url} / {self.body_sha256}"


class CompanyFieldObservation(UUIDModel):
    enrichment_run = models.ForeignKey(
        CompanyProfileRun,
        on_delete=models.PROTECT,
        related_name="field_observations",
    )
    source = models.ForeignKey(
        CompanyProfileSource,
        on_delete=models.PROTECT,
        related_name="field_observations",
    )
    field_name = models.CharField(max_length=32, choices=CompanyProfileField.choices)
    value_text = models.TextField()
    normalized_value = models.TextField()
    evidence_excerpt = models.CharField(max_length=1_000)
    evidence_sha256 = models.CharField(max_length=64)
    extraction_method = models.CharField(max_length=64)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    applied = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableCompanyProfileQuerySet.as_manager()

    class Meta:
        ordering = ("field_name", "-confidence", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("enrichment_run", "source", "field_name", "evidence_sha256"),
                name="companies_profile_observation_unique",
            ),
            models.CheckConstraint(
                condition=Q(field_name__in=CompanyProfileField.values),
                name="companies_profile_field_known",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0) & Q(confidence__lte=1),
                name="companies_profile_confidence_range",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("CompanyFieldObservation records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("CompanyFieldObservation records are immutable.")

    def __str__(self) -> str:
        return f"{self.enrichment_run_id} / {self.field_name} / {self.value_text}"
