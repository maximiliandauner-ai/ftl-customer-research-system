from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel, UUIDModel
from apps.operations.models import PipelineRun, ProviderCall
from apps.sources.models import SourceCandidate, SourceEndpoint


class DiscoveryRunReason(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    MANUAL = "manual", "Manual"


class DiscoveryStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETE = "complete", "Complete"
    PARTIAL = "partial", "Partial"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class QueryStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class SearchDefinition(UUIDModel):
    definition_key = models.SlugField(max_length=100)
    version = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    query_template = models.TextField()
    language = models.CharField(max_length=16, default="en")
    countries = models.JSONField(default=list)
    locations = models.JSONField(default=list)
    capability_clusters = models.JSONField(default=list)
    positive_terms = models.JSONField(default=list)
    negative_terms = models.JSONField(default=list)
    preferred_domains = models.JSONField(default=list)
    excluded_domains = models.JSONField(default=list)
    source_type_filters = models.JSONField(default=list)
    schedule_key = models.CharField(max_length=64, default="daily_morning")
    active = models.BooleanField(default=True)
    max_candidates = models.PositiveSmallIntegerField(default=50)
    lookback_days = models.PositiveSmallIntegerField(default=21)
    payload_sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_search_definitions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("definition_key", "-version")
        constraints = [
            models.UniqueConstraint(
                fields=("definition_key", "version"),
                name="discovery_definition_key_version_unique",
            ),
            models.UniqueConstraint(
                fields=("definition_key",),
                condition=Q(active=True),
                name="discovery_definition_one_active",
            ),
            models.CheckConstraint(
                condition=Q(version__gte=1),
                name="discovery_definition_version_gte_1",
            ),
            models.CheckConstraint(
                condition=Q(max_candidates__gte=1) & Q(max_candidates__lte=200),
                name="discovery_definition_candidates_range",
            ),
        ]
        permissions = [
            ("run_searchdefinition", "Can run a search definition"),
            ("version_searchdefinition", "Can create a search definition version"),
        ]

    def __str__(self) -> str:
        return f"{self.name} / v{self.version}"


class DiscoveryRun(UUIDModel, TimeStampedModel):
    definition = models.ForeignKey(
        SearchDefinition,
        on_delete=models.PROTECT,
        related_name="runs",
    )
    pipeline_run = models.OneToOneField(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="discovery_run",
    )
    logical_window_start = models.DateTimeField()
    logical_window_end = models.DateTimeField()
    run_reason = models.CharField(max_length=16, choices=DiscoveryRunReason.choices)
    status = models.CharField(
        max_length=16,
        choices=DiscoveryStatus.choices,
        default=DiscoveryStatus.QUEUED,
    )
    idempotency_key = models.CharField(max_length=255, unique=True)
    max_tool_calls = models.PositiveSmallIntegerField(default=8)
    max_candidates = models.PositiveSmallIntegerField(default=50)
    max_provider_cost_usd = models.DecimalField(max_digits=8, decimal_places=4)
    known_endpoints_queued = models.PositiveIntegerField(default=0)
    candidates_found = models.PositiveIntegerField(default=0)
    accepted_candidates = models.PositiveIntegerField(default=0)
    unsafe_candidates = models.PositiveIntegerField(default=0)
    duplicate_candidates = models.PositiveIntegerField(default=0)
    first_party_candidates = models.PositiveIntegerField(default=0)
    provider_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    warnings = models.JSONField(default=list)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)
    lease_owner = models.CharField(max_length=128, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-logical_window_end", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("definition", "logical_window_start", "logical_window_end", "run_reason"),
                name="discovery_run_definition_window_reason_unique",
            ),
            models.CheckConstraint(
                condition=Q(logical_window_end__gt=models.F("logical_window_start")),
                name="discovery_run_window_order",
            ),
            models.CheckConstraint(
                condition=Q(status__in=DiscoveryStatus.values),
                name="discovery_run_status_known",
            ),
            models.CheckConstraint(
                condition=Q(lease_owner="") | Q(lease_expires_at__isnull=False),
                name="discovery_run_lease_owner_expiry",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.definition} / {self.logical_window_start} / {self.status}"


class DiscoveryQuery(UUIDModel):
    discovery_run = models.ForeignKey(
        DiscoveryRun,
        on_delete=models.PROTECT,
        related_name="queries",
    )
    ordinal = models.PositiveSmallIntegerField()
    query_text = models.TextField()
    query_sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=QueryStatus.choices)
    provider_call = models.OneToOneField(
        ProviderCall,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="discovery_query",
    )
    candidate_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("ordinal",)
        constraints = [
            models.UniqueConstraint(
                fields=("discovery_run", "ordinal"),
                name="discovery_query_run_ordinal_unique",
            ),
            models.CheckConstraint(
                condition=Q(status__in=QueryStatus.values),
                name="discovery_query_status_known",
            ),
        ]


class DiscoveryCandidate(UUIDModel):
    discovery_run = models.ForeignKey(
        DiscoveryRun,
        on_delete=models.PROTECT,
        related_name="discovery_candidates",
    )
    discovery_query = models.ForeignKey(
        DiscoveryQuery,
        on_delete=models.PROTECT,
        related_name="discovery_candidates",
    )
    source_candidate = models.OneToOneField(
        SourceCandidate,
        on_delete=models.PROTECT,
        related_name="discovery_provenance",
    )
    url_sha256 = models.CharField(max_length=64)
    provider_source_reference = models.CharField(max_length=500, blank=True)
    location_hints = models.JSONField(default=list)
    first_party = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("discovery_run", "url_sha256"),
                name="discovery_candidate_run_url_unique",
            )
        ]


class EndpointWatch(UUIDModel, TimeStampedModel):
    source_endpoint = models.OneToOneField(
        SourceEndpoint,
        on_delete=models.PROTECT,
        related_name="discovery_watch",
    )
    active = models.BooleanField(default=True)
    poll_interval_hours = models.PositiveSmallIntegerField(default=24)
    next_poll_at = models.DateTimeField()
    last_queued_at = models.DateTimeField(null=True, blank=True)
    lease_owner = models.CharField(max_length=128, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("next_poll_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(poll_interval_hours__gte=1),
                name="discovery_watch_interval_gte_1",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.lease_owner and self.lease_expires_at is None:
            raise ValidationError({"lease_expires_at": "A lease owner requires an expiry."})
