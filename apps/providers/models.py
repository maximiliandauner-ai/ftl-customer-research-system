from __future__ import annotations

from django.db import models
from django.db.models import Q

from apps.core.models import UUIDModel


class CapabilityStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    LEGACY = "legacy", "Legacy"
    DEPRECATED = "deprecated", "Deprecated"
    DISABLED = "disabled", "Disabled"


class ModelCapability(UUIDModel):
    model_id = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=16, choices=CapabilityStatus.choices)
    supports_responses = models.BooleanField(default=True)
    supports_structured_outputs = models.BooleanField(default=True)
    supports_web_search = models.BooleanField(default=False)
    web_search_tool_type = models.CharField(max_length=64, blank=True)
    supports_source_list_include = models.BooleanField(default=False)
    supports_background = models.BooleanField(default=False)
    supports_background_store_false = models.BooleanField(default=False)
    supports_reasoning_effort = models.BooleanField(default=True)
    allowed_reasoning_efforts = models.JSONField(default=list)
    supports_store_false = models.BooleanField(default=True)
    maximum_tool_calls = models.PositiveSmallIntegerField(null=True, blank=True)
    effective_from = models.DateField()
    last_smoke_test_at = models.DateTimeField(null=True, blank=True)
    official_reference_snapshot = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("model_id",)
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=CapabilityStatus.values),
                name="providers_capability_status_known",
            )
        ]

    def __str__(self) -> str:
        return f"{self.model_id} / {self.status}"


class ModelPolicy(UUIDModel):
    policy_key = models.CharField(max_length=100)
    version = models.CharField(max_length=32)
    stage = models.CharField(max_length=100)
    capability = models.ForeignKey(
        ModelCapability,
        on_delete=models.PROTECT,
        related_name="policies",
    )
    reasoning_effort = models.CharField(max_length=16, default="medium")
    tool_type = models.CharField(max_length=64, blank=True)
    search_context_size = models.CharField(max_length=16, default="medium")
    max_tool_calls = models.PositiveSmallIntegerField(default=8)
    max_output_tokens = models.PositiveIntegerField(default=4_000)
    max_cost_usd = models.DecimalField(max_digits=8, decimal_places=4)
    max_daily_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=5)
    max_monthly_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=100)
    max_concurrent_calls = models.PositiveSmallIntegerField(default=2)
    store = models.BooleanField(default=False)
    active = models.BooleanField(default=False)
    policy_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("policy_key", "-version")
        constraints = [
            models.UniqueConstraint(
                fields=("policy_key", "version"),
                name="providers_policy_key_version_unique",
            ),
            models.UniqueConstraint(
                fields=("policy_key",),
                condition=Q(active=True),
                name="providers_policy_one_active",
            ),
            models.CheckConstraint(
                condition=Q(max_tool_calls__gte=1),
                name="providers_policy_tool_calls_gte_1",
            ),
            models.CheckConstraint(
                condition=Q(max_output_tokens__gte=256),
                name="providers_policy_output_gte_256",
            ),
            models.CheckConstraint(
                condition=Q(max_cost_usd__gte=0),
                name="providers_policy_cost_gte_0",
            ),
            models.CheckConstraint(
                condition=Q(max_daily_cost_usd__gte=models.F("max_cost_usd")),
                name="providers_policy_daily_covers_run",
            ),
            models.CheckConstraint(
                condition=Q(max_monthly_cost_usd__gte=models.F("max_daily_cost_usd")),
                name="providers_policy_monthly_covers_daily",
            ),
            models.CheckConstraint(
                condition=Q(max_concurrent_calls__gte=1),
                name="providers_policy_concurrency_gte_1",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.policy_key} / {self.version} / {self.capability.model_id}"
