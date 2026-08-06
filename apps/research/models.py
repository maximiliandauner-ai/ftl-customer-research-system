from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDModel
from apps.jobs.models import EvidenceItem
from apps.operations.models import PipelineRun, ProviderCall
from apps.opportunities.models import Opportunity
from apps.signals.models import SignalEvent


class ResearchRunStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    QUEUED = "queued", "Queued"
    IN_PROGRESS = "in_progress", "In progress"
    SOURCE_COMPLETE = "source_complete", "Source complete"
    REGISTERING_SOURCES = "registering_sources", "Registering sources"
    EXTRACTING = "extracting", "Extracting"
    COMPLETE = "complete", "Complete"
    PARTIAL = "partial", "Partial"
    REVIEW_REQUIRED = "review_required", "Review required"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"
    STALE = "stale", "Stale"


class ResearchSourceType(models.TextChoices):
    OFFICIAL_COMPANY = "official_company", "Official company"
    OFFICIAL_REGISTRY = "official_registry", "Official registry"
    OFFICIAL_GOVERNMENT = "official_government", "Official government"
    REPUTABLE_PRESS = "reputable_press", "Reputable press"
    PUBLIC_OTHER = "public_other", "Other public source"


class ClaimType(models.TextChoices):
    OBSERVED_FACT = "observed_fact", "Observed fact"
    INFERENCE = "inference", "Inference"
    HYPOTHESIS = "hypothesis", "Hypothesis"
    UNKNOWN = "unknown", "Unknown"


class ClaimCategory(models.TextChoices):
    COMPANY_PROFILE = "company_profile", "Company profile"
    SIGNAL_CONTEXT = "signal_context", "Signal context"
    ORGANIZATIONAL_OWNERSHIP = "organizational_ownership", "Organizational ownership"
    EXTERNAL_PARTNER_CONTEXT = "external_partner_context", "External partner context"
    INFRASTRUCTURE_PRIVACY_GOVERNANCE = (
        "infrastructure_privacy_governance",
        "Infrastructure, privacy, and governance",
    )
    EVIDENCE_AGAINST = "evidence_against", "Evidence against"
    OTHER = "other", "Other"


class ImmutableResearchQuerySet(models.QuerySet[Any]):
    def update(self, **_kwargs: Any) -> int:
        raise TypeError("Immutable research records cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError("Immutable research records cannot be deleted.")


class ResearchRun(UUIDModel):
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.PROTECT, related_name="research_runs"
    )
    pipeline_run = models.OneToOneField(
        PipelineRun, on_delete=models.PROTECT, related_name="standard_research_run"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_research_runs",
    )
    version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=24, choices=ResearchRunStatus.choices, default=ResearchRunStatus.DRAFT
    )
    is_current = models.BooleanField(default=True)
    brief_payload = models.JSONField(default=dict)
    brief_sha256 = models.CharField(max_length=64)
    public_input_payload = models.JSONField(default=dict)
    public_input_sha256 = models.CharField(max_length=64)
    source_registry_sha256 = models.CharField(max_length=64, blank=True)
    extraction_output = models.JSONField(default=dict, blank=True)
    research_prompt_version = models.CharField(max_length=32, default="2.1.0")
    extraction_prompt_version = models.CharField(max_length=32, default="2.1.0")
    schema_version = models.CharField(max_length=32, default="2.1")
    public_policy_key = models.CharField(max_length=100)
    public_policy_version = models.CharField(max_length=32)
    extraction_policy_key = models.CharField(max_length=100)
    extraction_policy_version = models.CharField(max_length=32)
    public_provider_call = models.ForeignKey(
        ProviderCall,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="public_research_runs",
    )
    extraction_provider_call = models.ForeignKey(
        ProviderCall,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="extracted_research_runs",
    )
    idempotency_key = models.CharField(max_length=255, unique=True)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    source_completed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-version", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("opportunity", "version"), name="research_run_opportunity_version_unique"
            ),
            models.UniqueConstraint(
                fields=("opportunity",),
                condition=Q(is_current=True),
                name="research_one_current_run_per_opportunity",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ResearchRunStatus.values),
                name="research_run_status_known",
            ),
        ]
        permissions = [("request_research", "Can request standard company research")]

    def __str__(self) -> str:
        return f"{self.opportunity_id} / v{self.version} / {self.status}"


class ResearchReportArtifact(UUIDModel):
    research_run = models.OneToOneField(
        ResearchRun, on_delete=models.PROTECT, related_name="report_artifact"
    )
    storage_key = models.CharField(max_length=1_000, unique=True)
    sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=100, default="text/markdown")
    renderer_hint = models.CharField(max_length=32, default="plain_markdown")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableResearchQuerySet.as_manager()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ResearchReportArtifact records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("ResearchReportArtifact records are immutable.")


class ResearchSource(UUIDModel):
    research_run = models.ForeignKey(ResearchRun, on_delete=models.PROTECT, related_name="sources")
    public_id = models.CharField(max_length=16)
    exact_provider_url = models.TextField()
    canonical_url = models.TextField()
    canonical_url_sha256 = models.CharField(max_length=64)
    title = models.CharField(max_length=1_000, blank=True)
    publisher = models.CharField(max_length=500, blank=True)
    source_type = models.CharField(max_length=32, choices=ResearchSourceType.choices)
    retrieved_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True, blank=True)
    provider_reference = models.JSONField(default=dict, blank=True)
    citation_locations = models.JSONField(default=list, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableResearchQuerySet.as_manager()

    class Meta:
        ordering = ("public_id",)
        constraints = [
            models.UniqueConstraint(
                fields=("research_run", "public_id"), name="research_source_run_public_unique"
            ),
            models.UniqueConstraint(
                fields=("research_run", "canonical_url_sha256"),
                name="research_source_run_url_unique",
            ),
            models.CheckConstraint(
                condition=Q(source_type__in=ResearchSourceType.values),
                name="research_source_type_known",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ResearchSource records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("ResearchSource records are immutable.")


class ResearchClaim(UUIDModel):
    research_run = models.ForeignKey(ResearchRun, on_delete=models.PROTECT, related_name="claims")
    public_id = models.CharField(max_length=16)
    claim_type = models.CharField(max_length=24, choices=ClaimType.choices)
    claim_category = models.CharField(max_length=48, choices=ClaimCategory.choices)
    statement = models.CharField(max_length=2_000)
    source_ids = models.JSONField(default=list)
    signal_ids = models.JSONField(default=list)
    evidence_ids = models.JSONField(default=list)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    current_as_of = models.DateField(null=True, blank=True)
    expires_at = models.DateField(null=True, blank=True)
    conflict_group = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sources: models.ManyToManyField[ResearchSource, ResearchClaimSource] = models.ManyToManyField(
        ResearchSource, through="ResearchClaimSource"
    )
    signals: models.ManyToManyField[SignalEvent, ResearchClaimSignal] = models.ManyToManyField(
        SignalEvent, through="ResearchClaimSignal"
    )
    evidence_items: models.ManyToManyField[EvidenceItem, ResearchClaimEvidence] = (
        models.ManyToManyField(EvidenceItem, through="ResearchClaimEvidence")
    )

    objects = ImmutableResearchQuerySet.as_manager()

    class Meta:
        ordering = ("public_id",)
        constraints = [
            models.UniqueConstraint(
                fields=("research_run", "public_id"), name="research_claim_run_public_unique"
            ),
            models.CheckConstraint(
                condition=Q(claim_type__in=ClaimType.values), name="research_claim_type_known"
            ),
            models.CheckConstraint(
                condition=Q(claim_category__in=ClaimCategory.values),
                name="research_claim_category_known",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0) & Q(confidence__lte=1),
                name="research_claim_confidence_range",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ResearchClaim records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("ResearchClaim records are immutable.")


class ResearchClaimSource(UUIDModel):
    claim = models.ForeignKey(ResearchClaim, on_delete=models.PROTECT)
    source = models.ForeignKey(ResearchSource, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("claim", "source"), name="research_claim_source_unique")
        ]


class ResearchClaimSignal(UUIDModel):
    claim = models.ForeignKey(ResearchClaim, on_delete=models.PROTECT)
    signal = models.ForeignKey(SignalEvent, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("claim", "signal"), name="research_claim_signal_unique")
        ]


class ResearchClaimEvidence(UUIDModel):
    claim = models.ForeignKey(ResearchClaim, on_delete=models.PROTECT)
    evidence_item = models.ForeignKey(EvidenceItem, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("claim", "evidence_item"), name="research_claim_evidence_unique"
            )
        ]


class ResearchDossier(UUIDModel):
    research_run = models.OneToOneField(
        ResearchRun, on_delete=models.PROTECT, related_name="dossier"
    )
    markdown_text = models.TextField()
    markdown_sha256 = models.CharField(max_length=64)
    renderer_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableResearchQuerySet.as_manager()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ResearchDossier records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("ResearchDossier records are immutable.")
