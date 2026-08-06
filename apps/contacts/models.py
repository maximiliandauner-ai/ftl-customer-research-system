from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.companies.models import Company
from apps.core.models import UUIDModel
from apps.operations.models import PipelineRun
from apps.opportunities.models import Opportunity
from apps.research.models import ResearchSource
from apps.solutions.models import SolutionVersion


class ImmutableContactQuerySet(models.QuerySet[Any]):
    def update(self, **_kwargs: Any) -> int:
        raise TypeError("Immutable contact evidence records cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError("Immutable contact evidence records cannot be deleted.")


class ContactResearchStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETE = "complete", "Complete"
    PARTIAL = "partial", "Partial"
    FAILED = "failed", "Failed"


class ContactResearchRun(UUIDModel):
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.PROTECT, related_name="contact_research_runs"
    )
    solution_version = models.ForeignKey(
        SolutionVersion, on_delete=models.PROTECT, related_name="contact_research_runs"
    )
    pipeline_run = models.OneToOneField(
        PipelineRun, on_delete=models.PROTECT, related_name="contact_research_run"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_contact_research_runs",
    )
    status = models.CharField(
        max_length=16, choices=ContactResearchStatus.choices, default=ContactResearchStatus.QUEUED
    )
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)
    input_sha256 = models.CharField(max_length=64)
    row_version = models.PositiveBigIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ContactResearchStatus.values),
                name="contacts_research_status_known",
            )
        ]
        permissions = [("request_contact_research", "Can request buyer and contact research")]


class BuyerRoleResult(UUIDModel):
    contact_research_run = models.OneToOneField(
        ContactResearchRun, on_delete=models.PROTECT, related_name="buyer_role_result"
    )
    solution_version = models.OneToOneField(
        SolutionVersion, on_delete=models.PROTECT, related_name="buyer_role_result"
    )
    output_payload = models.JSONField(default=dict)
    input_sha256 = models.CharField(max_length=64)
    output_sha256 = models.CharField(max_length=64)
    prompt_version = models.CharField(max_length=32, default="2.1.0")
    schema_version = models.CharField(max_length=16, default="2.1")
    generator_method = models.CharField(max_length=32, default="deterministic")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableContactQuerySet.as_manager()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("BuyerRoleResult records are immutable.")
        super().save(*args, **kwargs)


class BuyerRoleHypothesis(UUIDModel):
    result = models.ForeignKey(BuyerRoleResult, on_delete=models.PROTECT, related_name="roles")
    public_id = models.CharField(max_length=16)
    role_key = models.CharField(max_length=100)
    owner_type = models.CharField(max_length=48)
    responsibility_match = models.TextField()
    priority = models.PositiveSmallIntegerField()
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    source_ids = models.JSONField(default=list)
    claim_ids = models.JSONField(default=list)
    evidence_ids = models.JSONField(default=list)
    unknowns = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableContactQuerySet.as_manager()

    class Meta:
        ordering = ("priority",)
        constraints = [
            models.UniqueConstraint(
                fields=("result", "public_id"), name="contacts_role_result_public_unique"
            ),
            models.UniqueConstraint(
                fields=("result", "role_key"), name="contacts_role_result_key_unique"
            ),
            models.UniqueConstraint(
                fields=("result", "priority"), name="contacts_role_result_priority_unique"
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0) & Q(confidence__lte=1),
                name="contacts_role_confidence_range",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("BuyerRoleHypothesis records are immutable.")
        super().save(*args, **kwargs)


class ContactSourceTargetStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"


class ContactSourceTarget(UUIDModel):
    contact_research_run = models.ForeignKey(
        ContactResearchRun, on_delete=models.PROTECT, related_name="source_targets"
    )
    research_source = models.ForeignKey(
        ResearchSource, on_delete=models.PROTECT, related_name="contact_source_targets"
    )
    requested_url = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=ContactSourceTargetStatus.choices,
        default=ContactSourceTargetStatus.QUEUED,
    )
    route_count = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("contact_research_run", "research_source"),
                name="contacts_target_run_source_unique",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ContactSourceTargetStatus.values),
                name="contacts_target_status_known",
            ),
        ]


class ContactSourceArtifact(UUIDModel):
    target = models.OneToOneField(
        ContactSourceTarget, on_delete=models.PROTECT, related_name="artifact"
    )
    storage_key = models.CharField(max_length=1_000, unique=True)
    requested_url = models.TextField()
    final_url = models.TextField()
    sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField()
    content_type = models.CharField(max_length=255)
    storage_encrypted = models.BooleanField(default=True)
    encryption_key_id = models.CharField(max_length=64, default="")
    retrieved_at = models.DateTimeField()
    status_code = models.PositiveSmallIntegerField()
    redirect_chain = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableContactQuerySet.as_manager()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ContactSourceArtifact records are immutable.")
        super().save(*args, **kwargs)


class ContactEvidence(UUIDModel):
    artifact = models.ForeignKey(
        ContactSourceArtifact, on_delete=models.PROTECT, related_name="evidence_items"
    )
    public_id = models.CharField(max_length=10)
    evidence_kind = models.CharField(max_length=32)
    exact_text_ciphertext = models.TextField()
    display_text = models.CharField(max_length=500)
    public_normalized_text = models.CharField(max_length=4_096, blank=True)
    encryption_key_id = models.CharField(max_length=64)
    start_offset = models.PositiveIntegerField()
    end_offset = models.PositiveIntegerField()
    exact_text_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableContactQuerySet.as_manager()

    class Meta:
        ordering = ("public_id",)
        constraints = [
            models.UniqueConstraint(
                fields=("artifact", "public_id"), name="contacts_evidence_artifact_public_unique"
            ),
            models.CheckConstraint(
                condition=Q(end_offset__gt=models.F("start_offset")),
                name="contacts_evidence_offsets_ordered",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ContactEvidence records are immutable.")
        super().save(*args, **kwargs)


class ContactPerson(UUIDModel):
    professional_name = models.CharField(max_length=500)
    normalized_name = models.CharField(max_length=500, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_contact_people",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("professional_name",)


class ContactObservation(UUIDModel):
    person = models.ForeignKey(
        ContactPerson, on_delete=models.PROTECT, related_name="role_observations"
    )
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="contact_observations"
    )
    role_title = models.CharField(max_length=500)
    department = models.CharField(max_length=500, blank=True)
    observation_origin = models.CharField(max_length=32)
    research_source = models.ForeignKey(
        ResearchSource,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contact_observations",
    )
    evidence = models.ForeignKey(
        ContactEvidence,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contact_observations",
    )
    observed_at = models.DateTimeField()
    freshness_status = models.CharField(max_length=16, default="unknown")
    provenance_note = models.CharField(max_length=1_000, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_contact_observations",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableContactQuerySet.as_manager()

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ContactObservation records are immutable.")
        super().save(*args, **kwargs)


class RouteType(models.TextChoices):
    ROLE_EMAIL = "role_email", "Role email"
    INDIVIDUAL_BUSINESS_EMAIL = "individual_business_email", "Business email"
    CONTACT_FORM = "contact_form", "Contact form"
    PROFESSIONAL_PROFILE = "professional_profile", "Professional profile"
    PHONE = "phone", "Phone"
    OTHER_PUBLIC_ROUTE = "other_public_route", "Other public route"
    WARM_INTRODUCTION = "warm_introduction", "Warm introduction"
    EXISTING_RELATIONSHIP = "existing_relationship", "Existing relationship"
    EVENT_CONNECTION = "event_connection", "Event connection"


class RouteOrigin(models.TextChoices):
    PUBLIC_SOURCE = "public_source", "Public source"
    HUMAN_ENTERED = "human_entered", "Human entered"
    EXISTING_RELATIONSHIP = "existing_relationship", "Existing relationship"
    EVENT = "event", "Event"


class ContactRoute(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="contact_routes")
    contact_person = models.ForeignKey(
        ContactPerson,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contact_routes",
    )
    buyer_role = models.ForeignKey(
        BuyerRoleHypothesis,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contact_routes",
    )
    route_type = models.CharField(max_length=40, choices=RouteType.choices)
    route_origin = models.CharField(max_length=32, choices=RouteOrigin.choices)
    public_value = models.TextField(blank=True)
    encrypted_value = models.TextField(blank=True)
    value_masked = models.CharField(max_length=500)
    normalized_hmac = models.CharField(max_length=64)
    key_id = models.CharField(max_length=64)
    primary_research_source = models.ForeignKey(
        ResearchSource,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contact_routes",
    )
    primary_evidence = models.ForeignKey(
        ContactEvidence,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="contact_routes",
    )
    source_ids = models.JSONField(default=list)
    evidence_ids = models.JSONField(default=list)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_contact_routes",
    )
    provenance_note = models.CharField(max_length=1_000, blank=True)
    retrieved_at = models.DateTimeField()
    last_checked_at = models.DateTimeField()
    observation_status = models.CharField(max_length=32, default="unconfirmed")
    freshness_status = models.CharField(max_length=16, default="unknown")
    deliverability_status = models.CharField(max_length=16, default="unknown")
    outreach_eligibility = models.CharField(max_length=40, default="unreviewed")
    recommendation = models.CharField(max_length=48, default="research_more")
    jurisdiction = models.CharField(max_length=2, blank=True)
    legal_review_status = models.CharField(max_length=32, default="not_reviewed")
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    status = models.CharField(max_length=16, default="active")
    row_version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("route_type", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "normalized_hmac"), name="contacts_company_route_hmac_unique"
            ),
            models.CheckConstraint(
                condition=Q(confidence__gte=0) & Q(confidence__lte=1),
                name="contacts_route_confidence_range",
            ),
            models.CheckConstraint(
                condition=Q(route_type__in=RouteType.values), name="contacts_route_type_known"
            ),
            models.CheckConstraint(
                condition=Q(route_origin__in=RouteOrigin.values), name="contacts_route_origin_known"
            ),
        ]
        permissions = [
            ("add_human_route", "Can add an audited human-origin route"),
            ("review_contact_route", "Can review contact route eligibility"),
            ("select_contact_route", "Can select an exact contact route"),
            ("add_suppression", "Can add a suppression entry"),
        ]


class SuppressionEntry(UUIDModel):
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="suppression_entries",
    )
    contact_person = models.ForeignKey(
        ContactPerson,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="suppression_entries",
    )
    normalized_hmac = models.CharField(max_length=64, blank=True)
    scope_type = models.CharField(max_length=24)
    reason_type = models.CharField(max_length=32)
    reason_note = models.CharField(max_length=1_000)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_suppressions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableContactQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(company__isnull=False)
                    | Q(contact_person__isnull=False)
                    | ~Q(normalized_hmac="")
                ),
                name="contacts_suppression_has_scope",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("SuppressionEntry records are immutable.")
        super().save(*args, **kwargs)


class ContactSelection(UUIDModel):
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.PROTECT, related_name="contact_selections"
    )
    solution_version = models.ForeignKey(
        SolutionVersion, on_delete=models.PROTECT, related_name="contact_selections"
    )
    buyer_role = models.ForeignKey(
        BuyerRoleHypothesis, on_delete=models.PROTECT, related_name="selections"
    )
    contact_route = models.ForeignKey(
        ContactRoute, on_delete=models.PROTECT, related_name="selections"
    )
    selected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="contact_selections"
    )
    contact_purpose = models.CharField(max_length=500)
    jurisdiction = models.CharField(max_length=2)
    legal_review_status = models.CharField(max_length=32)
    lawful_basis_note = models.CharField(max_length=1_000, blank=True)
    retention_policy = models.CharField(max_length=100)
    route_row_version = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ImmutableContactQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("ContactSelection records are immutable.")
        super().save(*args, **kwargs)
