from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.companies.models import Company
from apps.core.models import TimeStampedModel, UUIDModel
from apps.operations.models import PipelineRun


class CandidateOrigin(models.TextChoices):
    MANUAL = "manual", "Manual"
    DISCOVERY = "discovery", "Discovery"


class CandidateStatus(models.TextChoices):
    NEW = "new", "New"
    FETCH_QUEUED = "fetch_queued", "Fetch queued"
    REGISTERED = "registered", "Registered"
    REJECTED = "rejected", "Rejected"
    UNSAFE = "unsafe", "Unsafe"
    DUPLICATE = "duplicate", "Duplicate"


class EndpointStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DEGRADED = "degraded", "Degraded"
    BLOCKED = "blocked", "Blocked"
    ARCHIVED = "archived", "Archived"


class ProviderType(models.TextChoices):
    UNKNOWN = "unknown", "Unknown"
    PERSONIO = "personio", "Personio"
    GREENHOUSE = "greenhouse", "Greenhouse"
    LEVER = "lever", "Lever"
    ASHBY = "ashby", "Ashby"
    JSON_LD = "json_ld", "JSON-LD"
    GENERIC_WEB = "generic_web", "Generic web"


class RobotsPolicy(models.TextChoices):
    ALLOWED = "allowed", "Allowed"
    BLOCKED = "blocked", "Blocked"
    UNKNOWN = "unknown", "Unknown"
    NOT_APPLICABLE = "not_applicable", "Not applicable"


class FetchStatus(models.TextChoices):
    STARTED = "started", "Started"
    FETCHED = "fetched", "Fetched"
    NOT_MODIFIED = "not_modified", "Not modified"
    BLOCKED = "blocked", "Blocked"
    FAILED = "failed", "Failed"
    TOO_LARGE = "too_large", "Too large"
    UNSUPPORTED = "unsupported", "Unsupported"


class NetworkPolicy(models.TextChoices):
    ALLOWED = "allowed", "Allowed"
    BLOCKED = "blocked", "Blocked"


class RetentionClass(models.TextChoices):
    PUBLIC_SOURCE = "public_source", "Public source"
    SHORT_LIVED = "short_lived", "Short lived"
    LEGAL_HOLD = "legal_hold", "Legal hold"


class SourceCandidate(UUIDModel):
    origin = models.CharField(
        max_length=16,
        choices=CandidateOrigin.choices,
        default=CandidateOrigin.MANUAL,
    )
    url_original = models.TextField()
    url_canonical = models.TextField(blank=True)
    url_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    source_type_hint = models.CharField(max_length=32, blank=True)
    company_name_hint = models.TextField(blank=True)
    company_domain_hint = models.TextField(blank=True)
    title_hint = models.TextField(blank=True)
    snippet_hint = models.TextField(blank=True)
    matched_terms = models.JSONField(default=list, blank=True)
    candidate_confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True)
    status = models.CharField(
        max_length=16,
        choices=CandidateStatus.choices,
        default=CandidateStatus.NEW,
    )
    rejection_reason = models.CharField(max_length=500, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_source_candidates",
    )
    registered_endpoint = models.ForeignKey(
        "SourceEndpoint",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="candidate_registrations",
    )
    pipeline_run = models.OneToOneField(
        PipelineRun,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="source_candidate",
    )
    request_id = models.UUIDField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(candidate_confidence__isnull=True)
                | (Q(candidate_confidence__gte=0) & Q(candidate_confidence__lte=1)),
                name="sources_candidate_confidence_range",
            ),
            models.CheckConstraint(
                condition=Q(status__in=CandidateStatus.values),
                name="sources_candidate_status_known",
            ),
        ]
        permissions = [("submit_public_source", "Can submit a confirmed public source")]

    def __str__(self) -> str:
        return f"{self.url_canonical or self.url_original} / {self.status}"


class SourceEndpoint(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="source_endpoints",
    )
    candidate = models.ForeignKey(
        SourceCandidate,
        on_delete=models.PROTECT,
        related_name="source_endpoints",
    )
    provider_type = models.CharField(
        max_length=24,
        choices=ProviderType.choices,
        default=ProviderType.UNKNOWN,
    )
    base_url_original = models.TextField()
    base_url_canonical = models.TextField()
    base_url_sha256 = models.CharField(max_length=64, unique=True)
    tenant_key = models.CharField(max_length=255, blank=True)
    configuration = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16,
        choices=EndpointStatus.choices,
        default=EndpointStatus.ACTIVE,
    )
    robots_policy = models.CharField(
        max_length=16,
        choices=RobotsPolicy.choices,
        default=RobotsPolicy.UNKNOWN,
    )
    rate_policy_key = models.CharField(max_length=64, default="public_default")
    etag = models.TextField(blank=True)
    last_modified = models.TextField(blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_failure_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    next_allowed_fetch_at = models.DateTimeField(null=True, blank=True)
    connector_key = models.CharField(max_length=64, default="unclassified")
    connector_version = models.CharField(max_length=32, default="1.0.0")
    last_schema_change_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=EndpointStatus.values),
                name="sources_endpoint_status_known",
            )
        ]

    def __str__(self) -> str:
        return f"{self.base_url_canonical} / {self.status}"


class FetchAttempt(UUIDModel):
    source_endpoint = models.ForeignKey(
        SourceEndpoint,
        on_delete=models.PROTECT,
        related_name="fetch_attempts",
    )
    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="fetch_attempts",
    )
    idempotency_key = models.CharField(max_length=255, unique=True)
    requested_url = models.TextField()
    final_url = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=FetchStatus.choices,
        default=FetchStatus.STARTED,
    )
    network_policy = models.CharField(
        max_length=16,
        choices=NetworkPolicy.choices,
        default=NetworkPolicy.ALLOWED,
    )
    robots_policy = models.CharField(
        max_length=16,
        choices=RobotsPolicy.choices,
        default=RobotsPolicy.UNKNOWN,
    )
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    elapsed_ms = models.PositiveIntegerField(null=True, blank=True)
    redirect_chain = models.JSONField(default=list, blank=True)
    response_headers_filtered = models.JSONField(default=dict, blank=True)
    body_sha256 = models.CharField(max_length=64, blank=True)
    body_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=255, blank=True)
    encoding = models.CharField(max_length=64, blank=True)
    retryable = models.BooleanField(default=False)
    attempt_count = models.PositiveIntegerField(default=1)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-started_at",)
        indexes = [
            models.Index(
                fields=("source_endpoint", "-started_at"), name="sources_attempt_endpoint_time"
            ),
            models.Index(fields=("status", "-started_at"), name="sources_attempt_status_time"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=FetchStatus.values),
                name="sources_attempt_status_known",
            ),
            models.CheckConstraint(
                condition=Q(attempt_count__gte=1),
                name="sources_attempt_count_gte_1",
            ),
            models.UniqueConstraint(
                fields=("pipeline_run", "attempt_count"),
                name="sources_attempt_run_number_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_endpoint_id} / {self.status} / {self.started_at}"


class ImmutableSourceQuerySet(models.QuerySet[Any]):
    def update(self, **_kwargs: Any) -> int:
        raise TypeError("Immutable source records cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError("Immutable source records cannot be deleted.")


class SourceArtifact(UUIDModel):
    source_endpoint = models.ForeignKey(
        SourceEndpoint,
        on_delete=models.PROTECT,
        related_name="artifacts",
    )
    storage_key = models.TextField(unique=True)
    sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=255)
    encoding = models.CharField(max_length=64, blank=True)
    retrieved_at = models.DateTimeField()
    retention_class = models.CharField(
        max_length=24,
        choices=RetentionClass.choices,
        default=RetentionClass.PUBLIC_SOURCE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableSourceQuerySet.as_manager()

    class Meta:
        ordering = ("-retrieved_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("source_endpoint", "sha256"),
                name="sources_artifact_endpoint_sha_unique",
            ),
            models.CheckConstraint(
                condition=Q(size_bytes__gte=1),
                name="sources_artifact_size_gte_1",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("SourceArtifact records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("SourceArtifact records are immutable.")

    def __str__(self) -> str:
        return f"{self.sha256} / {self.size_bytes} bytes"


class SourceSnapshot(UUIDModel):
    source_endpoint = models.ForeignKey(
        SourceEndpoint,
        on_delete=models.PROTECT,
        related_name="snapshots",
    )
    fetch_attempt = models.OneToOneField(
        FetchAttempt,
        on_delete=models.PROTECT,
        related_name="snapshot",
    )
    artifact = models.ForeignKey(
        SourceArtifact,
        on_delete=models.PROTECT,
        related_name="snapshots",
    )
    retrieved_at = models.DateTimeField()
    body_sha256 = models.CharField(max_length=64)
    content_type = models.CharField(max_length=255)
    encoding = models.CharField(max_length=64, blank=True)
    parser_hint = models.CharField(max_length=64, blank=True)
    retention_class = models.CharField(
        max_length=24,
        choices=RetentionClass.choices,
        default=RetentionClass.PUBLIC_SOURCE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableSourceQuerySet.as_manager()

    class Meta:
        ordering = ("-retrieved_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("source_endpoint", "body_sha256"),
                name="sources_snapshot_endpoint_sha_unique",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("SourceSnapshot records are immutable.")
        if self.artifact_id and self.body_sha256 != self.artifact.sha256:
            raise ValidationError("Snapshot and artifact hashes must match.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("SourceSnapshot records are immutable.")

    def __str__(self) -> str:
        return f"{self.source_endpoint_id} / {self.body_sha256}"
