from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.contacts.models import ContactResearchRun
from apps.knowledge.services import active_knowledge_release
from apps.opportunities.models import Opportunity, QualificationStatus
from apps.opportunities.services import AggregationValidationError, override_qualification
from apps.solutions.models import OpportunitySolutionState

PAGE_SIZE = 30


@login_required
@permission_required("opportunities.view_opportunity", raise_exception=True)
@require_GET
def opportunity_list(request: HttpRequest) -> HttpResponse:
    opportunities = Opportunity.objects.filter(active=True).select_related(
        "company", "owner", "primary_signal"
    )
    status = request.GET.get("status", "")
    if status in QualificationStatus.values:
        opportunities = opportunities.filter(qualification_status=status)
    return render(
        request,
        "opportunities/opportunity_list.html",
        {
            "page_obj": Paginator(opportunities, PAGE_SIZE).get_page(request.GET.get("page")),
            "selected_status": status,
            "status_choices": QualificationStatus.choices,
        },
    )


@login_required
@permission_required("opportunities.view_opportunity", raise_exception=True)
@require_GET
def opportunity_detail(request: HttpRequest, opportunity_id: uuid.UUID) -> HttpResponse:
    opportunity = get_object_or_404(
        Opportunity.objects.select_related("company", "owner", "primary_signal").prefetch_related(
            "signal_links__signal__posting",
            "company_assessments__feature_rows",
            "company_assessments__patterns",
            "qualification_overrides__actor",
            "research_runs",
        ),
        pk=opportunity_id,
    )
    latest_assessment = opportunity.company_assessments.order_by(
        "-feature_cutoff_at", "-created_at"
    ).first()
    solution_state = (
        OpportunitySolutionState.objects.select_related("current_version")
        .filter(opportunity=opportunity)
        .first()
    )
    contact_run = (
        ContactResearchRun.objects.select_related("buyer_role_result")
        .filter(opportunity=opportunity)
        .order_by("-created_at")
        .first()
    )
    return render(
        request,
        "opportunities/opportunity_detail.html",
        {
            "opportunity": opportunity,
            "assessment": latest_assessment,
            "status_choices": QualificationStatus.choices,
            "current_research": opportunity.research_runs.filter(is_current=True).first(),
            "research_enabled": settings.RUNTIME_SETTINGS.features.standard_research_enabled,
            "active_knowledge_release": active_knowledge_release(),
            "solution_state": solution_state,
            "contact_run": contact_run,
            "contact_research_enabled": (
                settings.RUNTIME_SETTINGS.features.contact_route_research_enabled
            ),
        },
    )


@login_required
@permission_required("opportunities.override_opportunity", raise_exception=True)
@require_POST
def qualification_override(request: HttpRequest, opportunity_id: uuid.UUID) -> HttpResponse:
    try:
        override_qualification(
            opportunity_id=opportunity_id,
            actor=request.user,  # type: ignore[arg-type]
            selected_status=request.POST.get("qualification_status", ""),
            reason=request.POST.get("reason", ""),
            request_id=getattr(request, "request_id", None),
        )
    except AggregationValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Qualification override recorded with its actor and reason.")
    return redirect("opportunities:detail", opportunity_id=opportunity_id)
