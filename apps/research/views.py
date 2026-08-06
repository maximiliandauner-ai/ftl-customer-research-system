from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.research.models import ResearchRun
from apps.research.services import (
    ResearchRequestError,
    ResearchValidationError,
    read_report_text,
    request_standard_research,
)

PAGE_SIZE = 30


@login_required
@permission_required("research.view_researchrun", raise_exception=True)
@require_GET
def research_list(request: HttpRequest) -> HttpResponse:
    runs = ResearchRun.objects.select_related("opportunity", "opportunity__company")
    return render(
        request,
        "research/research_list.html",
        {"page_obj": Paginator(runs, PAGE_SIZE).get_page(request.GET.get("page"))},
    )


@login_required
@permission_required("research.view_researchrun", raise_exception=True)
@require_GET
def research_detail(request: HttpRequest, research_run_id: uuid.UUID) -> HttpResponse:
    research_run = get_object_or_404(
        ResearchRun.objects.select_related(
            "opportunity",
            "opportunity__company",
            "pipeline_run",
            "public_provider_call",
            "extraction_provider_call",
        ).prefetch_related("sources", "claims"),
        pk=research_run_id,
    )
    report_text = ""
    if hasattr(research_run, "report_artifact"):
        try:
            report_text = read_report_text(research_run.report_artifact)
        except (OSError, UnicodeError, ResearchValidationError):
            messages.error(request, "The stored public report failed its integrity check.")
    dossier_text = research_run.dossier.markdown_text if hasattr(research_run, "dossier") else ""
    return render(
        request,
        "research/research_detail.html",
        {
            "research_run": research_run,
            "report_text": report_text,
            "dossier_text": dossier_text,
        },
    )


@login_required
@permission_required("research.request_research", raise_exception=True)
@require_POST
def request_research(request: HttpRequest, opportunity_id: uuid.UUID) -> HttpResponse:
    try:
        scheduled = request_standard_research(
            opportunity_id=opportunity_id,
            actor=request.user,  # type: ignore[arg-type]
            request_id=getattr(request, "request_id", None),
        )
    except ResearchRequestError as exc:
        messages.error(request, str(exc))
        return redirect("opportunities:detail", opportunity_id=opportunity_id)
    if scheduled.created:
        messages.success(
            request,
            "Research was committed to PostgreSQL and queued through the durable outbox.",
        )
    else:
        messages.info(request, "The identical research input is already queued or recorded.")
    return redirect("research:detail", research_run_id=scheduled.research_run.pk)
