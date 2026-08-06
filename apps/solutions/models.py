from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDModel
from apps.knowledge.models import Asset, KnowledgeRelease, OfferModule
from apps.operations.models import PipelineRun
from apps.opportunities.models import Opportunity
from apps.research.models import ResearchRun


class SolutionStateStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"
    REVIEW_REQUIRED = "review_required", "Review required"
    STALE = "stale", "Stale"


class ImmutableSolutionQuerySet(models.QuerySet[Any]):
    def update(self, **_kwargs: Any) -> int:
        raise TypeError("Immutable solution records cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError("Immutable solution records cannot be deleted.")


class SolutionVersion(UUIDModel):
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.PROTECT, related_name="solution_versions"
    )
    research_run = models.ForeignKey(
        ResearchRun, on_delete=models.PROTECT, related_name="solution_versions"
    )
    knowledge_release = models.ForeignKey(
        KnowledgeRelease, on_delete=models.PROTECT, related_name="solution_versions"
    )
    entry_offer = models.ForeignKey(
        OfferModule, on_delete=models.PROTECT, related_name="solution_versions"
    )
    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solution_versions",
    )
    version = models.PositiveIntegerField()
    structured_output = models.JSONField(default=dict)
    output_sha256 = models.CharField(max_length=64)
    input_sha256 = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=32, default="2.1.0")
    schema_version = models.CharField(max_length=16, default="2.1")
    generator_method = models.CharField(max_length=32, default="deterministic")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_solution_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableSolutionQuerySet.as_manager()

    class Meta:
        ordering = ("-version",)
        constraints = [
            models.UniqueConstraint(
                fields=("opportunity", "version"),
                name="solutions_opportunity_version_unique",
            )
        ]
        permissions = [
            ("request_solution", "Can request an FTL solution hypothesis"),
            ("edit_solution", "Can create an edited solution version"),
            ("approve_solution", "Can approve an exact solution version"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("SolutionVersion records are immutable.")
        super().save(*args, **kwargs)


class OpportunitySolutionState(UUIDModel):
    opportunity = models.OneToOneField(
        Opportunity, on_delete=models.PROTECT, related_name="solution_state"
    )
    current_version = models.ForeignKey(
        SolutionVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_for_states",
    )
    approved_version = models.ForeignKey(
        SolutionVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_for_states",
    )
    status = models.CharField(
        max_length=24, choices=SolutionStateStatus.choices, default=SolutionStateStatus.DRAFT
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_solution_states",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    stale_reason = models.CharField(max_length=500, blank=True)
    row_version = models.PositiveBigIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=SolutionStateStatus.values),
                name="solutions_state_status_known",
            )
        ]


class SolutionPhase(UUIDModel):
    solution_version = models.ForeignKey(
        SolutionVersion, on_delete=models.PROTECT, related_name="phases"
    )
    phase_order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=500)
    objective = models.TextField()
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableSolutionQuerySet.as_manager()

    class Meta:
        ordering = ("phase_order",)
        constraints = [
            models.UniqueConstraint(
                fields=("solution_version", "phase_order"),
                name="solutions_phase_version_order_unique",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("SolutionPhase records are immutable.")
        super().save(*args, **kwargs)


class AssetMatch(UUIDModel):
    solution_version = models.OneToOneField(
        SolutionVersion, on_delete=models.PROTECT, related_name="asset_match"
    )
    knowledge_release = models.ForeignKey(
        KnowledgeRelease, on_delete=models.PROTECT, related_name="asset_matches"
    )
    pipeline_run = models.ForeignKey(
        PipelineRun, on_delete=models.PROTECT, related_name="asset_matches"
    )
    output_payload = models.JSONField(default=dict)
    output_sha256 = models.CharField(max_length=64)
    matcher_version = models.CharField(max_length=32, default="1.0.0")
    candidate_asset_ids = models.JSONField(default=list)
    excluded_reasons = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableSolutionQuerySet.as_manager()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("AssetMatch records are immutable.")
        super().save(*args, **kwargs)


class AssetSelection(UUIDModel):
    asset_match = models.ForeignKey(AssetMatch, on_delete=models.PROTECT, related_name="selections")
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="selections")
    priority = models.PositiveSmallIntegerField()
    supported_solution_phase = models.PositiveSmallIntegerField()
    relevance_reason = models.CharField(max_length=2_000)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableSolutionQuerySet.as_manager()

    class Meta:
        ordering = ("priority",)
        constraints = [
            models.UniqueConstraint(
                fields=("asset_match", "asset"),
                name="solutions_match_asset_unique",
            ),
            models.UniqueConstraint(
                fields=("asset_match", "priority"),
                name="solutions_match_priority_unique",
            ),
            models.CheckConstraint(
                condition=Q(priority__gte=1) & Q(priority__lte=2),
                name="solutions_selection_priority_range",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("AssetSelection records are immutable.")
        super().save(*args, **kwargs)
