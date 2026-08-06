from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.companies.models import Company
from apps.core.models import TimeStampedModel, UUIDModel
from apps.operations.models import PipelineRun
from apps.signals.models import SignalEvent


class DerivedStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    SUPERSEDED = "superseded", "Superseded"
    REVIEW_REQUIRED = "review_required", "Review required"


class PatternKey(models.TextChoices):
    ISOLATED_EXPERIMENT = "isolated_experiment", "Isolated experiment"
    CROSS_FUNCTIONAL_BUILD = "cross_functional_capability_build", "Cross-functional build"
    PRODUCTION_EXPANSION = "production_capacity_expansion", "Production expansion"
    INTERNAL_PLATFORM = "internal_platform_build", "Internal platform build"
    LEARNING_ENABLEMENT = "learning_and_enablement_program", "Learning and enablement"
    LOCAL_PRIVATE_AI = "local_private_ai_investment", "Local/private AI investment"
    MATURE_INTERNAL_TEAM = "mature_internal_team", "Mature internal team"
    WEAK_AMBIGUOUS = "weak_or_ambiguous_pattern", "Weak or ambiguous"


class QualificationStatus(models.TextChoices):
    CANDIDATE = "candidate", "Candidate"
    WATCHLIST = "watchlist", "Watchlist"
    RESEARCH_ELIGIBLE = "research_eligible", "Research eligible"
    REVIEW_REQUIRED = "review_required", "Review required"
    QUALIFIED = "qualified", "Qualified"
    REJECTED = "rejected", "Rejected"


class ResearchStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    QUEUED = "queued", "Queued"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETE = "complete", "Complete"
    PARTIAL = "partial", "Partial"
    REVIEW_REQUIRED = "review_required", "Review required"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"
    STALE = "stale", "Stale"


class WorkStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    IN_PROGRESS = "in_progress", "In progress"
    REVIEW = "review", "Review"
    COMPLETE = "complete", "Complete"


class RelationshipStage(models.TextChoices):
    UNCONTACTED = "uncontacted", "Uncontacted"
    CONTACTED = "contacted", "Contacted"
    ENGAGED = "engaged", "Engaged"
    PAUSED = "paused", "Paused"


class Opportunity(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="opportunities")
    title = models.CharField(max_length=500)
    use_case_family = models.CharField(max_length=100, default="capability_systems")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_opportunities",
    )
    primary_signal = models.ForeignKey(
        SignalEvent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="primary_for_opportunities",
    )
    qualification_status = models.CharField(
        max_length=24,
        choices=QualificationStatus.choices,
        default=QualificationStatus.CANDIDATE,
    )
    research_status = models.CharField(
        max_length=24, choices=ResearchStatus.choices, default=ResearchStatus.NOT_STARTED
    )
    solution_status = models.CharField(
        max_length=24, choices=WorkStatus.choices, default=WorkStatus.NOT_STARTED
    )
    outreach_status = models.CharField(
        max_length=24, choices=WorkStatus.choices, default=WorkStatus.NOT_STARTED
    )
    relationship_stage = models.CharField(
        max_length=24,
        choices=RelationshipStage.choices,
        default=RelationshipStage.UNCONTACTED,
    )
    priority_score = models.PositiveSmallIntegerField(null=True, blank=True)
    score_coverage = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    opportunity_mode = models.CharField(max_length=24, blank=True)
    entry_offer_key = models.CharField(max_length=100, blank=True)
    next_action_key = models.CharField(max_length=100, blank=True)
    next_action_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    row_version = models.PositiveBigIntegerField(default=1)

    class Meta:
        ordering = ("-priority_score", "company__name")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "use_case_family"),
                condition=Q(active=True),
                name="opportunities_one_active_company_family",
            ),
            models.CheckConstraint(
                condition=Q(priority_score__isnull=True) | Q(priority_score__lte=100),
                name="opportunities_priority_lte_100",
            ),
        ]
        permissions = [("override_opportunity", "Can override opportunity qualification")]

    def __str__(self) -> str:
        return f"{self.company} / {self.title}"


class CompanyAssessment(UUIDModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="company_assessments"
    )
    pipeline_run = models.OneToOneField(
        PipelineRun, on_delete=models.PROTECT, related_name="company_assessment"
    )
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="company_assessments",
    )
    status = models.CharField(
        max_length=24, choices=DerivedStatus.choices, default=DerivedStatus.COMPLETED
    )
    feature_cutoff_at = models.DateTimeField()
    feature_builder_version = models.CharField(max_length=32)
    scoring_policy_version = models.CharField(max_length=32)
    features = models.JSONField(default=dict)
    pattern_keys = models.JSONField(default=list)
    capability_relevance = models.PositiveSmallIntegerField(null=True, blank=True)
    capability_coverage = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    commercial_actionability = models.PositiveSmallIntegerField(null=True, blank=True)
    commercial_coverage = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    long_term_system_potential = models.PositiveSmallIntegerField(null=True, blank=True)
    long_term_coverage = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    strategic_value = models.PositiveSmallIntegerField(null=True, blank=True)
    strategic_coverage = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    priority_score = models.PositiveSmallIntegerField(null=True, blank=True)
    overall_coverage = models.DecimalField(max_digits=4, decimal_places=3, default=0)
    selected_signal_ids = models.JSONField(default=list)
    selected_assessment_ids = models.JSONField(default=list)
    missing_components = models.JSONField(default=list)
    input_sha256 = models.CharField(max_length=64)
    idempotency_key = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-feature_cutoff_at", "-created_at")


class CompanyFeature(UUIDModel):
    company_assessment = models.ForeignKey(
        CompanyAssessment, on_delete=models.PROTECT, related_name="feature_rows"
    )
    feature_key = models.CharField(max_length=100)
    value = models.JSONField(null=True)
    unit = models.CharField(max_length=32)
    cutoff_at = models.DateTimeField()
    input_record_ids = models.JSONField(default=list)
    input_sha256 = models.CharField(max_length=64)
    feature_builder_version = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("feature_key",)
        constraints = [
            models.UniqueConstraint(
                fields=("company_assessment", "feature_key"),
                name="opportunities_feature_assessment_key_unique",
            )
        ]


class CompanyPattern(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="patterns")
    company_assessment = models.ForeignKey(
        CompanyAssessment, on_delete=models.PROTECT, related_name="patterns"
    )
    pattern_key = models.CharField(max_length=64, choices=PatternKey.choices)
    feature_cutoff_at = models.DateTimeField()
    rule_version = models.CharField(max_length=32)
    input_signal_ids = models.JSONField(default=list)
    input_sha256 = models.CharField(max_length=64)
    confidence = models.DecimalField(max_digits=4, decimal_places=3)
    status = models.CharField(
        max_length=24, choices=DerivedStatus.choices, default=DerivedStatus.COMPLETED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("pattern_key",)
        constraints = [
            models.UniqueConstraint(
                fields=("company_assessment", "pattern_key"),
                name="opportunities_pattern_assessment_key_unique",
            )
        ]


class OpportunitySignal(UUIDModel):
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.PROTECT, related_name="signal_links"
    )
    signal = models.ForeignKey(
        SignalEvent, on_delete=models.PROTECT, related_name="opportunity_links"
    )
    relationship_type = models.CharField(max_length=32, default="supporting")
    inclusion_reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("opportunity", "signal"),
                name="opportunities_signal_link_unique",
            )
        ]


class QualificationOverride(UUIDModel):
    opportunity = models.ForeignKey(
        Opportunity, on_delete=models.PROTECT, related_name="qualification_overrides"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="opportunity_overrides",
    )
    prior_status = models.CharField(max_length=24, choices=QualificationStatus.choices)
    selected_status = models.CharField(max_length=24, choices=QualificationStatus.choices)
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
