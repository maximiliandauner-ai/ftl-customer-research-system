from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDModel


class PipelineStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    WAITING_EXTERNAL = "waiting_external", "Waiting external"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class PipelineTrigger(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    MANUAL = "manual", "Manual"
    BACKFILL = "backfill", "Backfill"
    WEBHOOK = "webhook", "Webhook"
    RECOVERY = "recovery", "Recovery"


class StepStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class ProviderCallStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETE = "complete", "Complete"
    FAILED = "failed", "Failed"
    REFUSED = "refused", "Refused"
    INCOMPLETE = "incomplete", "Incomplete"
    CANCELED = "canceled", "Canceled"


class OutboxStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PUBLISHING = "publishing", "Publishing"
    PUBLISHED = "published", "Published"
    FAILED = "failed", "Failed"
    CANCELED = "canceled", "Canceled"


class ActorType(models.TextChoices):
    USER = "user", "User"
    SYSTEM = "system", "System"
    PROVIDER = "provider", "Provider"


class PipelineRun(UUIDModel, TimeStampedModel):
    pipeline_name = models.CharField(max_length=100)
    stage = models.CharField(max_length=100)
    status = models.CharField(
        max_length=24,
        choices=PipelineStatus.choices,
        default=PipelineStatus.QUEUED,
    )
    trigger = models.CharField(max_length=16, choices=PipelineTrigger.choices)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_pipeline_runs",
    )
    idempotency_key = models.CharField(max_length=255, unique=True)
    request_id = models.UUIDField(null=True, blank=True)
    trace_id = models.CharField(max_length=128, blank=True)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.UUIDField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    next_action_at = models.DateTimeField(null=True, blank=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    input_count = models.PositiveIntegerField(default=0)
    output_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    policy_versions = models.JSONField(default=dict, blank=True)
    context = models.JSONField(default=dict, blank=True)
    estimated_cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
    )
    actual_cost_usd = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
    )
    last_error_code = models.CharField(max_length=64, blank=True)
    last_error_message = models.CharField(max_length=500, blank=True)
    row_version = models.PositiveBigIntegerField(default=1)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "heartbeat_at"), name="ops_run_status_heartbeat"),
            models.Index(fields=("pipeline_name", "-created_at"), name="ops_run_pipeline_created"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=PipelineStatus.values),
                name="ops_pipeline_status_known",
            )
        ]
        permissions = [
            ("trigger_checkpoint", "Can trigger an operations checkpoint"),
            ("view_dependency_health", "Can view detailed dependency health"),
        ]

    def __str__(self) -> str:
        return f"{self.pipeline_name} / {self.stage} / {self.status}"


class PipelineStepRun(UUIDModel, TimeStampedModel):
    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="steps",
    )
    stage = models.CharField(max_length=100)
    status = models.CharField(max_length=16, choices=StepStatus.choices)
    idempotency_key = models.CharField(max_length=255, unique=True)
    attempt = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    input_ids = models.JSONField(default=dict, blank=True)
    output_ids = models.JSONField(default=dict, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    last_error_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("status", "heartbeat_at"), name="ops_step_status_heartbeat")
        ]

    def __str__(self) -> str:
        return f"{self.pipeline_run_id} / {self.stage} / {self.status}"


class TaskOutbox(UUIDModel):
    command_type = models.CharField(max_length=160)
    payload = models.JSONField(default=dict)
    payload_schema_version = models.CharField(max_length=16, default="2.1")
    idempotency_key = models.CharField(max_length=255, unique=True)
    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.PROTECT,
        related_name="outbox_commands",
    )
    request_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=OutboxStatus.choices,
        default=OutboxStatus.PENDING,
    )
    available_at = models.DateTimeField(default=timezone.now)
    attempts = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=64, blank=True)
    last_error_message = models.CharField(max_length=500, blank=True)
    claimed_by = models.CharField(max_length=128, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    broker_message_id = models.CharField(max_length=255, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("status", "available_at"), name="ops_outbox_status_available"),
            models.Index(fields=("claimed_at",), name="ops_outbox_claimed"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=OutboxStatus.values),
                name="ops_outbox_status_known",
            ),
            models.CheckConstraint(condition=Q(attempts__gte=0), name="ops_outbox_attempts_gte_0"),
        ]
        permissions = [("retry_taskoutbox", "Can retry an eligible outbox command")]

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.payload, dict):
            raise ValidationError({"payload": "Outbox payload must be a JSON object."})
        if len(str(self.payload).encode()) > 8_192:
            raise ValidationError({"payload": "Outbox payload exceeds the 8 KiB policy limit."})

    def __str__(self) -> str:
        return f"{self.command_type} / {self.status}"


class ProviderCall(UUIDModel):
    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="provider_calls",
    )
    provider = models.CharField(max_length=64)
    operation = models.CharField(max_length=100)
    request_sha256 = models.CharField(max_length=64)
    model_policy_snapshot = models.JSONField(default=dict, blank=True)
    external_response_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=ProviderCallStatus.choices)
    usage = models.JSONField(default=dict, blank=True)
    tool_calls = models.JSONField(default=list, blank=True)
    cost_metadata = models.JSONField(default=dict, blank=True)
    safe_error_code = models.CharField(max_length=64, blank=True)
    safe_error_message = models.CharField(max_length=500, blank=True)
    retention_class = models.CharField(max_length=64)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("provider", "operation", "-created_at"), name="ops_provider_operation"
            ),
            models.Index(fields=("status", "-created_at"), name="ops_provider_status"),
        ]

    def __str__(self) -> str:
        return f"{self.provider} / {self.operation} / {self.status}"


class AuditEventQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **_kwargs: Any) -> int:
        raise TypeError("AuditEvent records are append-only.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise TypeError("AuditEvent records are append-only.")


class AuditEvent(UUIDModel):
    occurred_at = models.DateTimeField(default=timezone.now, editable=False)
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_id = models.UUIDField(null=True, blank=True)
    action = models.CharField(max_length=160)
    object_type = models.CharField(max_length=100)
    object_id = models.UUIDField()
    before_summary = models.JSONField(default=dict, blank=True)
    after_summary = models.JSONField(default=dict, blank=True)
    reason_key = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=500, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    trace_id = models.CharField(max_length=128, blank=True)
    pipeline_run = models.ForeignKey(
        PipelineRun,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="audit_events",
    )

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ("-occurred_at",)
        indexes = [
            models.Index(
                fields=("object_type", "object_id", "-occurred_at"), name="ops_audit_object_time"
            ),
            models.Index(fields=("request_id",), name="ops_audit_request"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise TypeError("AuditEvent records are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise TypeError("AuditEvent records are append-only.")

    def __str__(self) -> str:
        return f"{self.action} / {self.object_type}:{self.object_id}"
