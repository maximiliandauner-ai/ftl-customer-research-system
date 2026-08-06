from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel, UUIDModel


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
