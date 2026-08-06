from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.signals.classification import AssessmentValidationError, override_assessment_mode
from apps.signals.models import OpportunityMode, SignalEvent, SignalStatus, SignalType
from apps.signals.services import SignalValidationError, retract_signal

PAGE_SIZE = 30


@login_required
@permission_required("signals.view_signalevent", raise_exception=True)
@require_GET
def signal_list(request: HttpRequest) -> HttpResponse:
    signals = SignalEvent.objects.select_related("company", "posting", "detection_attempt")
    status = request.GET.get("status", SignalStatus.ACTIVE)
    signal_type = request.GET.get("type", "")
    if status in SignalStatus.values:
        signals = signals.filter(status=status)
    if signal_type in SignalType.values:
        signals = signals.filter(signal_type=signal_type)
    return render(
        request,
        "signals/signal_list.html",
        {
            "page_obj": Paginator(signals, PAGE_SIZE).get_page(request.GET.get("page")),
            "selected_status": status,
            "selected_type": signal_type,
            "signal_types": SignalType.choices,
            "active_count": SignalEvent.objects.filter(status=SignalStatus.ACTIVE).count(),
        },
    )


@login_required
@permission_required("signals.view_signalevent", raise_exception=True)
@require_GET
def signal_detail(request: HttpRequest, signal_id: uuid.UUID) -> HttpResponse:
    signal = get_object_or_404(
        SignalEvent.objects.select_related(
            "company",
            "posting",
            "change_event__new_snapshot__source_snapshot__artifact",
            "detection_attempt__pipeline_run",
            "detection_attempt__evidence_catalog",
            "detection_attempt__ontology",
            "reviewed_by",
        ).prefetch_related(
            "evidence_links__evidence_item",
            "assessments__capability_clusters",
            "assessments__capability_gaps",
            "assessments__overrides__actor",
        ),
        pk=signal_id,
    )
    assessment = signal.assessments.first()
    return render(
        request,
        "signals/signal_detail.html",
        {
            "signal": signal,
            "assessment": assessment,
            "current_override": assessment.overrides.first() if assessment else None,
            "mode_choices": OpportunityMode.choices,
        },
    )


@login_required
@permission_required("signals.review_signalevent", raise_exception=True)
@require_POST
def retract(request: HttpRequest, signal_id: uuid.UUID) -> HttpResponse:
    try:
        retract_signal(
            signal_id=signal_id,
            actor=request.user,  # type: ignore[arg-type]
            reason=request.POST.get("reason", ""),
            request_id=getattr(request, "request_id", None),
        )
    except SignalValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, "The signal was retracted as a false positive; evidence was preserved."
        )
    return redirect("signals:detail", signal_id=signal_id)


@login_required
@permission_required("signals.override_signalassessment", raise_exception=True)
@require_POST
def assessment_override(request: HttpRequest, signal_id: uuid.UUID) -> HttpResponse:
    signal = get_object_or_404(SignalEvent.objects.prefetch_related("assessments"), pk=signal_id)
    assessment = signal.assessments.first()
    if assessment is None:
        messages.error(request, "This signal has no assessment to override.")
        return redirect("signals:detail", signal_id=signal_id)
    try:
        override_assessment_mode(
            assessment_id=assessment.pk,
            actor=request.user,  # type: ignore[arg-type]
            opportunity_mode=request.POST.get("opportunity_mode", ""),
            reason=request.POST.get("reason", ""),
            request_id=getattr(request, "request_id", None),
        )
    except AssessmentValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Opportunity-mode override recorded; re-aggregation was queued.")
    return redirect("signals:detail", signal_id=signal_id)
