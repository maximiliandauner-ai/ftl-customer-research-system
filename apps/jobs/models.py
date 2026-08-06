from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.companies.models import Company
from apps.core.models import TimeStampedModel, UUIDModel
from apps.operations.models import PipelineRun
from apps.sources.models import FetchAttempt, SourceEndpoint, SourceSnapshot


class PostingLifecycle(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    UNKNOWN = "unknown", "Unknown"


class ClosureReason(models.TextChoices):
    CONSECUTIVE_ABSENCE = "consecutive_absence", "Consecutive successful absence"
    EXPLICIT_PROVIDER = "explicit_provider", "Explicit provider closure"
    VALID_THROUGH = "valid_through", "Valid-through date"


class WorkplaceType(models.TextChoices):
    ONSITE = "onsite", "On-site"
    HYBRID = "hybrid", "Hybrid"
    REMOTE = "remote", "Remote"
    UNKNOWN = "unknown", "Unknown"


class ObservationState(models.TextChoices):
    FOUND = "found", "Found"
    MISSING = "missing", "Missing"
    NOT_MODIFIED = "not_modified", "Not modified"
    EXPLICIT_CLOSED = "explicit_closed", "Explicitly closed"


class PostingChangeType(models.TextChoices):
    CREATED = "created", "Created"
    UNCHANGED = "unchanged", "Unchanged"
    COSMETIC = "cosmetic", "Cosmetic"
    MATERIAL = "material", "Material"
    CLOSED = "closed", "Closed"
    REOPENED = "reopened", "Reopened"


class DuplicateRelationshipType(models.TextChoices):
    DUPLICATE = "duplicate", "Duplicate"
    TRANSLATION = "translation", "Translation"
    SYNDICATED = "syndicated", "Syndicated"
    RELATED = "related", "Related"


class DuplicateMethod(models.TextChoices):
    PROVIDER_ID = "provider_id", "Provider identity"
    CANONICAL_URL = "canonical_url", "Canonical URL"
    CONTENT_HASH = "content_hash", "Content hash"
    RULE = "rule", "Deterministic rule"
    SEMANTIC_REVIEW = "semantic_review", "Semantic review"


class DuplicateReviewStatus(models.TextChoices):
    AUTOMATIC = "automatic", "Automatic"
    NEEDS_REVIEW = "needs_review", "Needs review"
    CONFIRMED = "confirmed", "Confirmed"
    REJECTED = "rejected", "Rejected"


class ParseStatus(models.TextChoices):
    STARTED = "started", "Started"
    SUCCEEDED = "succeeded", "Succeeded"
    UNSUPPORTED = "unsupported", "Unsupported"
    INVALID_SCHEMA = "invalid_schema", "Invalid schema"
    FAILED = "failed", "Failed"


class JobPosting(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="job_postings")
    primary_source_endpoint = models.ForeignKey(
        SourceEndpoint,
        on_delete=models.PROTECT,
        related_name="job_postings",
    )
    provider_type = models.CharField(max_length=24)
    external_posting_id = models.CharField(max_length=255)
    canonical_url = models.TextField()
    apply_url = models.TextField(blank=True)
    source_url = models.TextField()
    title = models.CharField(max_length=500)
    normalized_title = models.CharField(max_length=500, db_index=True, default="")
    department = models.CharField(max_length=255, blank=True)
    team = models.CharField(max_length=255, blank=True)
    employment_type = models.CharField(max_length=100, blank=True)
    language = models.CharField(max_length=16, blank=True)
    lifecycle_status = models.CharField(
        max_length=16,
        choices=PostingLifecycle.choices,
        default=PostingLifecycle.OPEN,
    )
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    closure_reason = models.CharField(max_length=32, choices=ClosureReason.choices, blank=True)
    successful_absence_count = models.PositiveSmallIntegerField(default=0)
    current_snapshot = models.ForeignKey(
        "JobPostingSnapshot",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_for_postings",
    )
    row_version = models.PositiveBigIntegerField(default=1)

    class Meta:
        ordering = ("-last_seen_at", "title")
        constraints = [
            models.UniqueConstraint(
                fields=("primary_source_endpoint", "provider_type", "external_posting_id"),
                name="jobs_posting_endpoint_provider_external_unique",
            ),
            models.CheckConstraint(
                condition=Q(lifecycle_status__in=PostingLifecycle.values),
                name="jobs_posting_lifecycle_known",
            ),
            models.CheckConstraint(
                condition=Q(last_seen_at__gte=models.F("first_seen_at")),
                name="jobs_posting_seen_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} / {self.company}"


class JobLocation(UUIDModel):
    posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="locations")
    ordinal = models.PositiveSmallIntegerField()
    display_text = models.CharField(max_length=500)
    city = models.CharField(max_length=255, blank=True)
    region = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=2, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    remote = models.BooleanField(default=False)
    workplace_type = models.CharField(
        max_length=16,
        choices=WorkplaceType.choices,
        default=WorkplaceType.UNKNOWN,
    )

    class Meta:
        ordering = ("ordinal",)
        constraints = [
            models.UniqueConstraint(
                fields=("posting", "ordinal"), name="jobs_location_posting_ordinal_unique"
            ),
            models.CheckConstraint(
                condition=Q(workplace_type__in=WorkplaceType.values),
                name="jobs_location_workplace_known",
            ),
        ]

    def __str__(self) -> str:
        return self.display_text


class ImmutableJobQuerySet(models.QuerySet[Any]):
    def update(self, **_kwargs: Any) -> int:
        raise TypeError("Immutable job records cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError("Immutable job records cannot be deleted.")


class JobPostingSnapshot(UUIDModel):
    posting = models.ForeignKey(JobPosting, on_delete=models.PROTECT, related_name="snapshots")
    source_snapshot = models.ForeignKey(
        SourceSnapshot,
        on_delete=models.PROTECT,
        related_name="job_posting_snapshots",
    )
    parse_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="job_posting_snapshots",
    )
    connector_key = models.CharField(max_length=64)
    connector_version = models.CharField(max_length=32)
    normalizer_version = models.CharField(max_length=32)
    retrieved_at = models.DateTimeField()
    title = models.CharField(max_length=500)
    description_text = models.TextField()
    structured_sections = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)
    locations_payload = models.JSONField(default=list)
    full_hash = models.CharField(max_length=64)
    semantic_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableJobQuerySet.as_manager()

    class Meta:
        ordering = ("-retrieved_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("posting", "full_hash"), name="jobs_snapshot_posting_full_hash_unique"
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("JobPostingSnapshot records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("JobPostingSnapshot records are immutable.")

    def __str__(self) -> str:
        return f"{self.posting_id} / {self.full_hash}"


class EvidenceCatalog(UUIDModel):
    """Immutable, deterministic address space over one normalized job snapshot."""

    snapshot = models.ForeignKey(
        JobPostingSnapshot,
        on_delete=models.PROTECT,
        related_name="evidence_catalogs",
    )
    builder_version = models.CharField(max_length=32)
    item_count = models.PositiveIntegerField()
    catalog_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableJobQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("snapshot", "builder_version"),
                name="jobs_evidence_catalog_snapshot_builder_unique",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("EvidenceCatalog records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("EvidenceCatalog records are immutable.")

    def __str__(self) -> str:
        return f"{self.snapshot_id} / {self.builder_version}"


class EvidenceItem(UUIDModel):
    """An exact quote owned by an evidence catalog; model output may only reference it."""

    catalog = models.ForeignKey(
        EvidenceCatalog,
        on_delete=models.PROTECT,
        related_name="items",
    )
    public_id = models.CharField(max_length=16)
    field_path = models.CharField(max_length=255)
    exact_text = models.TextField()
    normalized_text = models.TextField()
    start_offset = models.PositiveIntegerField(null=True, blank=True)
    end_offset = models.PositiveIntegerField(null=True, blank=True)
    language = models.CharField(max_length=16, blank=True)
    content_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableJobQuerySet.as_manager()

    class Meta:
        ordering = ("public_id",)
        constraints = [
            models.UniqueConstraint(
                fields=("catalog", "public_id"),
                name="jobs_evidence_item_catalog_public_unique",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(start_offset__isnull=True) & Q(end_offset__isnull=True))
                    | (
                        Q(start_offset__isnull=False)
                        & Q(end_offset__isnull=False)
                        & Q(end_offset__gt=models.F("start_offset"))
                    )
                ),
                name="jobs_evidence_item_offset_pair",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("EvidenceItem records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("EvidenceItem records are immutable.")

    def __str__(self) -> str:
        return f"{self.catalog_id} / {self.public_id}"


class PostingObservation(UUIDModel):
    posting = models.ForeignKey(JobPosting, on_delete=models.PROTECT, related_name="observations")
    source_snapshot = models.ForeignKey(
        SourceSnapshot,
        on_delete=models.PROTECT,
        related_name="posting_observations",
    )
    parse_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="posting_observations",
    )
    fetch_attempt = models.ForeignKey(
        FetchAttempt,
        on_delete=models.PROTECT,
        related_name="posting_observations",
    )
    state = models.CharField(
        max_length=16,
        choices=ObservationState.choices,
        default=ObservationState.FOUND,
    )
    provider_identity = models.CharField(max_length=255)
    observed_url = models.TextField()
    observed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-observed_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("posting", "fetch_attempt"),
                name="jobs_observation_posting_fetch_unique",
            ),
            models.CheckConstraint(
                condition=Q(state__in=ObservationState.values),
                name="jobs_observation_state_known",
            ),
        ]


class PostingChangeEvent(UUIDModel):
    posting = models.ForeignKey(JobPosting, on_delete=models.PROTECT, related_name="change_events")
    source_snapshot = models.ForeignKey(
        SourceSnapshot,
        on_delete=models.PROTECT,
        related_name="posting_change_events",
    )
    observation = models.OneToOneField(
        PostingObservation,
        on_delete=models.PROTECT,
        related_name="change_event",
    )
    parse_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="posting_change_events",
    )
    old_snapshot = models.ForeignKey(
        JobPostingSnapshot,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="changes_from",
    )
    new_snapshot = models.ForeignKey(
        JobPostingSnapshot,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="changes_to",
    )
    change_type = models.CharField(max_length=16, choices=PostingChangeType.choices)
    changed_fields = models.JSONField(default=list)
    before_full_hash = models.CharField(max_length=64, blank=True)
    after_full_hash = models.CharField(max_length=64, blank=True)
    policy_version = models.CharField(max_length=32)
    idempotency_key = models.CharField(max_length=255, unique=True)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableJobQuerySet.as_manager()

    class Meta:
        ordering = ("-occurred_at", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=Q(change_type__in=PostingChangeType.values),
                name="jobs_change_type_known",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("PostingChangeEvent records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("PostingChangeEvent records are immutable.")

    def __str__(self) -> str:
        return f"{self.posting_id} / {self.change_type} / {self.occurred_at}"


class DuplicateRelationship(UUIDModel, TimeStampedModel):
    primary_posting = models.ForeignKey(
        JobPosting,
        on_delete=models.PROTECT,
        related_name="duplicate_relationships_as_primary",
    )
    secondary_posting = models.ForeignKey(
        JobPosting,
        on_delete=models.PROTECT,
        related_name="duplicate_relationships_as_secondary",
    )
    relationship_type = models.CharField(
        max_length=16,
        choices=DuplicateRelationshipType.choices,
        default=DuplicateRelationshipType.DUPLICATE,
    )
    method = models.CharField(max_length=24, choices=DuplicateMethod.choices)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    review_status = models.CharField(max_length=16, choices=DuplicateReviewStatus.choices)
    source_priority = models.CharField(max_length=16, default="first_party")
    evidence = models.JSONField(default=dict)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=~Q(primary_posting=models.F("secondary_posting")),
                name="jobs_duplicate_distinct_postings",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0) & Q(confidence__lte=1),
                name="jobs_duplicate_confidence_range",
            ),
            models.UniqueConstraint(
                fields=("primary_posting", "secondary_posting"),
                name="jobs_duplicate_posting_pair_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.primary_posting_id} / {self.secondary_posting_id} / {self.review_status}"


class ConnectorParseAttempt(UUIDModel):
    source_snapshot = models.ForeignKey(
        SourceSnapshot,
        on_delete=models.PROTECT,
        related_name="parse_attempts",
    )
    pipeline_run = models.OneToOneField(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="connector_parse_attempt",
    )
    status = models.CharField(max_length=24, choices=ParseStatus.choices)
    connector_key = models.CharField(max_length=64, blank=True)
    connector_version = models.CharField(max_length=32, blank=True)
    normalizer_version = models.CharField(max_length=32)
    detected_content_type = models.CharField(max_length=255, blank=True)
    posting_count = models.PositiveIntegerField(default=0)
    snapshot_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    warnings = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    elapsed_ms = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-started_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ParseStatus.values),
                name="jobs_parse_status_known",
            )
        ]
        permissions = [("reparse_source_snapshot", "Can reparse a source snapshot")]

    def __str__(self) -> str:
        return f"{self.source_snapshot_id} / {self.status}"
