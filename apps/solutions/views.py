from __future__ import annotations

import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.solutions.models import OpportunitySolutionState, SolutionVersion
from apps.solutions.services import (
    SolutionValidationError,
    approve_solution,
    create_edited_solution,
    request_solution_design,
)

PAGE_SIZE = 30


@login_required
@permission_required("solutions.view_solutionversion", raise_exception=True)
@require_GET
def solution_list(request: HttpRequest) -> HttpResponse:
    versions = SolutionVersion.objects.select_related(
        "opportunity", "opportunity__company", "knowledge_release", "research_run"
    )
    return render(
        request,
        "solutions/solution_list.html",
        {"page_obj": Paginator(versions, PAGE_SIZE).get_page(request.GET.get("page"))},
    )


@login_required
@permission_required("solutions.view_solutionversion", raise_exception=True)
@require_GET
def solution_detail(request: HttpRequest, solution_id: uuid.UUID) -> HttpResponse:
    solution = get_object_or_404(
        SolutionVersion.objects.select_related(
            "opportunity",
            "opportunity__company",
            "research_run",
            "knowledge_release",
            "entry_offer",
            "pipeline_run",
        ).prefetch_related("phases", "asset_match__selections__asset"),
        pk=solution_id,
    )
    state = OpportunitySolutionState.objects.get(opportunity=solution.opportunity)
    return render(
        request,
        "solutions/solution_detail.html",
        {
            "solution": solution,
            "state": state,
            "is_current": state.current_version_id == solution.pk,
            "is_approved": state.approved_version_id == solution.pk,
            "editable_json": json.dumps(solution.structured_output, indent=2, ensure_ascii=False),
        },
    )


@login_required
@permission_required("solutions.request_solution", raise_exception=True)
@require_POST
def request_solution(request: HttpRequest, opportunity_id: uuid.UUID) -> HttpResponse:
    try:
        scheduled = request_solution_design(
            opportunity_id=opportunity_id,
            actor=request.user,  # type: ignore[arg-type]
            request_id=getattr(request, "request_id", None),
        )
    except SolutionValidationError as exc:
        messages.error(request, str(exc))
    else:
        message = (
            "Solution design was committed and queued."
            if scheduled.created
            else "The identical solution input is already queued or recorded."
        )
        messages.success(request, message)
    return redirect("opportunities:detail", opportunity_id=opportunity_id)


@login_required
@permission_required("solutions.edit_solution", raise_exception=True)
@require_POST
def edit_solution(request: HttpRequest, solution_id: uuid.UUID) -> HttpResponse:
    try:
        scheduled = create_edited_solution(
            solution_id=solution_id,
            actor=request.user,  # type: ignore[arg-type]
            payload_json=request.POST.get("structured_output", ""),
            request_id=getattr(request, "request_id", None),
        )
    except SolutionValidationError as exc:
        messages.error(request, str(exc))
        return redirect("solutions:detail", solution_id=solution_id)
    messages.success(request, "Edited solution version saved; asset rematching is queued.")
    return redirect("operations:run-detail", run_id=scheduled.pipeline_run.pk)


@login_required
@permission_required("solutions.approve_solution", raise_exception=True)
@require_POST
def approve_solution_view(request: HttpRequest, solution_id: uuid.UUID) -> HttpResponse:
    try:
        approve_solution(
            solution_id=solution_id,
            actor=request.user,  # type: ignore[arg-type]
            reason=request.POST.get("reason", ""),
            request_id=getattr(request, "request_id", None),
        )
    except SolutionValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "The exact solution and asset-match hashes are approved.")
    return redirect("solutions:detail", solution_id=solution_id)
