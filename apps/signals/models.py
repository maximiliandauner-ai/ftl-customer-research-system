from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.companies.models import Company
from apps.core.models import UUIDModel
from apps.jobs.models import EvidenceCatalog, EvidenceItem, JobPosting, PostingChangeEvent
from apps.operations.models import PipelineRun, ProviderCall


class SignalType(models.TextChoices):
    CAPABILITY_HIRING = "capability_hiring", "Capability hiring"
    MATERIAL_DESCRIPTION_CHANGE = "material_description_change", "Material description change"
    ROLE_REPOSTED = "role_reposted", "Role reposted"
    ROLE_REOPENED = "role_reopened", "Role reopened"
    ROLE_CLOSED = "role_closed", "Role closed"


class DetectionMethod(models.TextChoices):
    DETERMINISTIC = "deterministic", "Deterministic"
    MODEL_ASSISTED = "model_assisted", "Model assisted"


class DetectionStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETE = "complete", "Complete"
    NO_SIGNAL = "no_signal", "No signal"
    FAILED = "failed", "Failed"
    REVIEW_REQUIRED = "review_required", "Review required"


class SignalStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RETRACTED = "retracted", "Retracted"


class SignalReviewState(models.TextChoices):
    UNREVIEWED = "unreviewed", "Unreviewed"
    CONFIRMED = "confirmed", "Confirmed"
    FALSE_POSITIVE = "false_positive", "False positive"
    SUPERSEDED = "superseded", "Superseded by detector policy"


class ImmutableSignalQuerySet(models.QuerySet[Any]):
    def update(self, **_kwargs: Any) -> int:
        raise TypeError("Immutable signal records cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError("Immutable signal records cannot be deleted.")


class SignalOntology(UUIDModel):
    version = models.CharField(max_length=32, unique=True)
    allowed_signal_types = models.JSONField(default=list)
    allowed_capability_tags = models.JSONField(default=list)
    rule_payload = models.JSONField(default=dict)
    ontology_sha256 = models.CharField(max_length=64, unique=True)
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.version} / {'active' if self.active else 'inactive'}"


class SignalDetectionAttempt(UUIDModel):
    pipeline_run = models.OneToOneField(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="signal_detection_attempt",
    )
    change_event = models.ForeignKey(
        PostingChangeEvent,
        on_delete=models.PROTECT,
        related_name="signal_detection_attempts",
    )
    evidence_catalog = models.ForeignKey(
        EvidenceCatalog,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="signal_detection_attempts",
    )
    ontology = models.ForeignKey(
        SignalOntology,
        on_delete=models.PROTECT,
        related_name="detection_attempts",
    )
    provider_call = models.ForeignKey(
        ProviderCall,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="signal_detection_attempts",
    )
    status = models.CharField(
        max_length=24,
        choices=DetectionStatus.choices,
        default=DetectionStatus.QUEUED,
    )
    detector_method = models.CharField(
        max_length=24,
        choices=DetectionMethod.choices,
        default=DetectionMethod.DETERMINISTIC,
    )
    prompt_version = models.CharField(max_length=32)
    schema_version = models.CharField(max_length=32)
    detector_version = models.CharField(max_length=32)
    input_sha256 = models.CharField(max_length=64, blank=True)
    output_payload = models.JSONField(default=dict, blank=True)
    no_signal_reason = models.CharField(max_length=500, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=DetectionStatus.values),
                name="signals_attempt_status_known",
            )
        ]

    def __str__(self) -> str:
        return f"{self.change_event_id} / {self.status}"


class SignalEvent(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="signal_events")
    posting = models.ForeignKey(
        JobPosting,
        on_delete=models.PROTECT,
        related_name="signal_events",
    )
    change_event = models.ForeignKey(
        PostingChangeEvent,
        on_delete=models.PROTECT,
        related_name="signals",
    )
    detection_attempt = models.ForeignKey(
        SignalDetectionAttempt,
        on_delete=models.PROTECT,
        related_name="signals",
    )
    signal_type = models.CharField(max_length=48, choices=SignalType.choices)
    event_kind = models.CharField(max_length=16)
    capability_tags = models.JSONField(default=list)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    rationale = models.CharField(max_length=1_000)
    occurred_at = models.DateTimeField()
    observed_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=SignalStatus.choices,
        default=SignalStatus.ACTIVE,
    )
    review_state = models.CharField(
        max_length=24,
        choices=SignalReviewState.choices,
        default=SignalReviewState.UNREVIEWED,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_signal_events",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.CharField(max_length=500, blank=True)
    idempotency_key = models.CharField(max_length=255, unique=True)
    ontology_version = models.CharField(max_length=32)
    prompt_version = models.CharField(max_length=32)
    schema_version = models.CharField(max_length=32)
    detector_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-observed_at", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=Q(signal_type__in=SignalType.values),
                name="signals_event_type_known",
            ),
            models.CheckConstraint(
                condition=Q(status__in=SignalStatus.values),
                name="signals_event_status_known",
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0) & Q(confidence__lte=1),
                name="signals_event_confidence_range",
            ),
        ]
        permissions = [("review_signalevent", "Can review and retract a signal event")]

    def __str__(self) -> str:
        return f"{self.company_id} / {self.signal_type} / {self.status}"


class SignalEvidence(UUIDModel):
    signal = models.ForeignKey(
        SignalEvent,
        on_delete=models.PROTECT,
        related_name="evidence_links",
    )
    evidence_item = models.ForeignKey(
        EvidenceItem,
        on_delete=models.PROTECT,
        related_name="signal_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableSignalQuerySet.as_manager()

    class Meta:
        ordering = ("evidence_item__public_id",)
        constraints = [
            models.UniqueConstraint(
                fields=("signal", "evidence_item"),
                name="signals_evidence_signal_item_unique",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("SignalEvidence records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("SignalEvidence records are immutable.")


class OpportunityMode(models.TextChoices):
    EMPLOYMENT_ONLY = "employment_only", "Employment only"
    EXTERNAL_SERVICE = "external_service", "External service"
    HYBRID = "hybrid", "Hybrid"
    WATCH_SIGNAL = "watch_signal", "Watch signal"
    IRRELEVANT = "irrelevant", "Irrelevant"
    UNKNOWN = "unknown", "Unknown"


class AssessmentStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    REVIEW_REQUIRED = "review_required", "Review required"
    FAILED = "failed", "Failed"
    SUPERSEDED = "superseded", "Superseded"


class SignalAssessment(UUIDModel):
    signal = models.ForeignKey(
        SignalEvent,
        on_delete=models.PROTECT,
        related_name="assessments",
    )
    pipeline_run = models.OneToOneField(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="signal_assessment",
    )
    status = models.CharField(
        max_length=24,
        choices=AssessmentStatus.choices,
        default=AssessmentStatus.QUEUED,
    )
    classification_method = models.CharField(max_length=24, default="deterministic")
    ontology_version = models.CharField(max_length=32)
    scoring_policy_version = models.CharField(max_length=32)
    prompt_key = models.CharField(max_length=64, default="capability_gap_classifier")
    prompt_version = models.CharField(max_length=32)
    schema_version = models.CharField(max_length=32)
    structured_output = models.JSONField(default=dict, blank=True)
    component_values = models.JSONField(default=dict, blank=True)
    component_coverage = models.JSONField(default=dict, blank=True)
    missing_components = models.JSONField(default=list, blank=True)
    capability_relevance = models.PositiveSmallIntegerField(null=True, blank=True)
    score_coverage = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    opportunity_mode = models.CharField(max_length=24, choices=OpportunityMode.choices)
    mode_confidence = models.DecimalField(max_digits=4, decimal_places=3)
    mode_rationale = models.CharField(max_length=1_000)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    input_sha256 = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=255, unique=True)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=AssessmentStatus.values),
                name="signals_assessment_status_known",
            ),
            models.CheckConstraint(
                condition=Q(opportunity_mode__in=OpportunityMode.values),
                name="signals_assessment_mode_known",
            ),
            models.CheckConstraint(
                condition=Q(capability_relevance__isnull=True) | Q(capability_relevance__lte=100),
                name="signals_assessment_relevance_lte_100",
            ),
            models.CheckConstraint(
                condition=Q(mode_confidence__gte=0) & Q(mode_confidence__lte=1),
                name="signals_assessment_mode_confidence_range",
            ),
        ]


class CapabilityClusterRecord(UUIDModel):
    assessment = models.ForeignKey(
        SignalAssessment,
        on_delete=models.PROTECT,
        related_name="capability_clusters",
    )
    cluster_key = models.CharField(max_length=100)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    evidence_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("cluster_key",)
        constraints = [
            models.UniqueConstraint(
                fields=("assessment", "cluster_key"),
                name="signals_cluster_assessment_key_unique",
            )
        ]


class CapabilityGapRecord(UUIDModel):
    assessment = models.ForeignKey(
        SignalAssessment,
        on_delete=models.PROTECT,
        related_name="capability_gaps",
    )
    gap_key = models.CharField(max_length=100)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    rationale = models.CharField(max_length=1_000)
    evidence_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("gap_key",)
        constraints = [
            models.UniqueConstraint(
                fields=("assessment", "gap_key"),
                name="signals_gap_assessment_key_unique",
            )
        ]


class SignalAssessmentEvidence(UUIDModel):
    assessment = models.ForeignKey(
        SignalAssessment,
        on_delete=models.PROTECT,
        related_name="evidence_links",
    )
    evidence_item = models.ForeignKey(
        EvidenceItem,
        on_delete=models.PROTECT,
        related_name="assessment_links",
    )
    relationship_type = models.CharField(max_length=32, default="classification_input")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableSignalQuerySet.as_manager()

    class Meta:
        ordering = ("evidence_item__public_id",)
        constraints = [
            models.UniqueConstraint(
                fields=("assessment", "evidence_item"),
                name="signals_assessment_evidence_unique",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("SignalAssessmentEvidence records are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("SignalAssessmentEvidence records are immutable.")


class AssessmentOverride(UUIDModel):
    assessment = models.ForeignKey(
        SignalAssessment,
        on_delete=models.PROTECT,
        related_name="overrides",
    )
    opportunity_mode = models.CharField(max_length=24, choices=OpportunityMode.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="signal_assessment_overrides",
    )
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        permissions = [("override_signalassessment", "Can override a signal assessment")]
