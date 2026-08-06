from __future__ import annotations

import uuid
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.companies.models import Company
from apps.operations.contracts import CreateCheckpointCommandV1
from apps.operations.forms import CheckpointCommandForm, OutboxRetryForm
from apps.operations.models import (
    AuditEvent,
    OutboxStatus,
    PipelineRun,
    PipelineStatus,
    TaskOutbox,
)
from apps.operations.services import (
    InvalidOutboxTransition,
    create_checkpoint_command,
    retry_outbox_command,
)
from apps.sources.models import CandidateStatus, SourceArtifact, SourceCandidate

PAGE_SIZE = 30


def _request_id(request: HttpRequest) -> uuid.UUID:
    return request.request_id  # type: ignore[attr-defined,no-any-return]


def _page(request: HttpRequest, queryset: Any) -> Any:
    return Paginator(queryset, PAGE_SIZE).get_page(request.GET.get("page"))


def _checkpoint_form() -> CheckpointCommandForm:
    return CheckpointCommandForm(
        initial={"idempotency_key": f"operations.checkpoint:{uuid.uuid4()}"}
    )


@login_required
@permission_required("operations.view_pipelinerun", raise_exception=True)
@require_GET
def overview(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "operations/overview.html",
        {
            "checkpoint_form": _checkpoint_form(),
            "failed_outbox_count": TaskOutbox.objects.filter(status=OutboxStatus.FAILED).count(),
            "pending_outbox_count": TaskOutbox.objects.filter(
                status__in=(OutboxStatus.PENDING, OutboxStatus.PUBLISHING)
            ).count(),
            "active_run_count": PipelineRun.objects.filter(
                status__in=("queued", "running", "waiting_external")
            ).count(),
            "company_count": Company.objects.count(),
            "source_artifact_count": SourceArtifact.objects.count(),
            "source_attention_count": SourceCandidate.objects.filter(
                status__in=(CandidateStatus.REJECTED, CandidateStatus.UNSAFE)
            ).count(),
            "recent_runs": PipelineRun.objects.select_related("requested_by")[:8],
            "recent_audit": AuditEvent.objects.all()[:8],
        },
    )


@login_required
@permission_required("operations.view_pipelinerun", raise_exception=True)
@require_GET
def operations_index(request: HttpRequest) -> HttpResponse:
    oldest = (
        TaskOutbox.objects.filter(status__in=(OutboxStatus.PENDING, OutboxStatus.FAILED))
        .order_by("created_at")
        .first()
    )
    return render(
        request,
        "operations/index.html",
        {
            "checkpoint_form": _checkpoint_form(),
            "outbox_counts": {
                status: TaskOutbox.objects.filter(status=status).count()
                for status in OutboxStatus.values
            },
            "run_counts": {
                status: PipelineRun.objects.filter(status=status).count()
                for status in ("queued", "running", "waiting_external", "complete", "failed")
            },
            "oldest_unpublished": oldest,
            "recent_runs": PipelineRun.objects.select_related("requested_by")[:10],
            "recent_commands": TaskOutbox.objects.select_related(
                "pipeline_run", "pipeline_run__requested_by"
            )[:10],
        },
    )


@login_required
@permission_required("operations.view_pipelinerun", raise_exception=True)
@require_GET
def run_list(request: HttpRequest) -> HttpResponse:
    runs = PipelineRun.objects.select_related("requested_by")
    status = request.GET.get("status", "")
    if status in PipelineStatus.values:
        runs = runs.filter(status=status)
    return render(
        request,
        "operations/run_list.html",
        {"page_obj": _page(request, runs), "selected_status": status},
    )


@login_required
@permission_required("operations.view_pipelinerun", raise_exception=True)
@require_GET
def run_detail(request: HttpRequest, run_id: uuid.UUID) -> HttpResponse:
    run = get_object_or_404(
        PipelineRun.objects.select_related("requested_by").prefetch_related(
            "steps", "outbox_commands", "audit_events"
        ),
        pk=run_id,
    )
    return render(request, "operations/run_detail.html", {"run": run})


@login_required
@permission_required("operations.view_taskoutbox", raise_exception=True)
@require_GET
def outbox_list(request: HttpRequest) -> HttpResponse:
    commands = TaskOutbox.objects.select_related("pipeline_run", "pipeline_run__requested_by")
    status = request.GET.get("status", "")
    if status in OutboxStatus.values:
        commands = commands.filter(status=status)
    return render(
        request,
        "operations/outbox_list.html",
        {"page_obj": _page(request, commands), "selected_status": status},
    )


@login_required
@permission_required("operations.view_taskoutbox", raise_exception=True)
@require_GET
def outbox_detail(request: HttpRequest, outbox_id: uuid.UUID) -> HttpResponse:
    command = get_object_or_404(
        TaskOutbox.objects.select_related("pipeline_run", "pipeline_run__requested_by"),
        pk=outbox_id,
    )
    return render(
        request,
        "operations/outbox_detail.html",
        {"command": command, "retry_form": OutboxRetryForm()},
    )


@login_required
@permission_required("operations.view_auditevent", raise_exception=True)
@require_GET
def audit_list(request: HttpRequest) -> HttpResponse:
    events = AuditEvent.objects.select_related("pipeline_run")
    action = request.GET.get("action", "").strip()
    if action:
        events = events.filter(action=action[:160])
    return render(
        request,
        "operations/audit_list.html",
        {"page_obj": _page(request, events), "selected_action": action},
    )


@login_required
@permission_required("operations.trigger_checkpoint", raise_exception=True)
@require_POST
def create_checkpoint(request: HttpRequest) -> HttpResponse:
    form = CheckpointCommandForm(request.POST)
    if not form.is_valid():
        messages.error(request, "The checkpoint request was invalid.")
        return redirect("operations:index")
    command = CreateCheckpointCommandV1(
        idempotency_key=form.cleaned_data["idempotency_key"],
        request_id=_request_id(request),
    )
    result = create_checkpoint_command(command=command, actor=request.user)  # type: ignore[arg-type]
    if result.created:
        messages.success(request, "Checkpoint committed to PostgreSQL and queued for dispatch.")
    else:
        messages.info(request, "That checkpoint already exists; its durable record was reused.")
    return redirect("operations:run-detail", run_id=result.pipeline_run.pk)


@login_required
@permission_required("operations.retry_taskoutbox", raise_exception=True)
@require_POST
def retry_outbox(request: HttpRequest, outbox_id: uuid.UUID) -> HttpResponse:
    form = OutboxRetryForm(request.POST)
    if not form.is_valid():
        messages.error(request, "A bounded retry reason is required.")
        return redirect("operations:outbox-detail", outbox_id=outbox_id)
    try:
        retry_outbox_command(
            outbox_id=outbox_id,
            actor=request.user,  # type: ignore[arg-type]
            request_id=_request_id(request),
            reason=form.cleaned_data["reason"],
        )
    except InvalidOutboxTransition as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "The failed command is eligible for immediate safe retry.")
    return redirect("operations:outbox-detail", outbox_id=outbox_id)
