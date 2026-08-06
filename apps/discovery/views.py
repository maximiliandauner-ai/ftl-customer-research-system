from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.discovery.models import (
    DiscoveryCandidate,
    DiscoveryRun,
    DiscoveryStatus,
    EndpointWatch,
    SearchDefinition,
)
from apps.discovery.services import create_discovery_run
from apps.sources.models import CandidateStatus

PAGE_SIZE = 30


@login_required
@permission_required("discovery.view_discoveryrun", raise_exception=True)
@require_GET
def discovery_index(request: HttpRequest) -> HttpResponse:
    runs = DiscoveryRun.objects.select_related("definition", "pipeline_run__requested_by")
    status = request.GET.get("status", "")
    if status in DiscoveryStatus.values:
        runs = runs.filter(status=status)
    definitions = SearchDefinition.objects.filter(active=True).order_by("name")
    return render(
        request,
        "discovery/index.html",
        {
            "definitions": definitions,
            "page_obj": Paginator(runs, PAGE_SIZE).get_page(request.GET.get("page")),
            "selected_status": status,
            "active_definition_count": definitions.count(),
            "watched_endpoint_count": EndpointWatch.objects.filter(active=True).count(),
            "candidate_count": sum(run.candidates_found for run in runs[:500]),
        },
    )


@login_required
@permission_required("discovery.view_discoveryrun", raise_exception=True)
@require_GET
def discovery_run_detail(request: HttpRequest, run_id: uuid.UUID) -> HttpResponse:
    run = get_object_or_404(
        DiscoveryRun.objects.select_related(
            "definition",
            "pipeline_run__requested_by",
        ).prefetch_related(
            "queries__provider_call",
            "discovery_candidates__source_candidate__registered_endpoint__company",
        ),
        pk=run_id,
    )
    return render(request, "discovery/run_detail.html", {"run": run})


@login_required
@permission_required("discovery.view_discoverycandidate", raise_exception=True)
@require_GET
def discovery_candidate_list(request: HttpRequest) -> HttpResponse:
    candidates = DiscoveryCandidate.objects.select_related(
        "discovery_run__definition",
        "source_candidate__registered_endpoint__company",
    )
    status = request.GET.get("status", "")
    if status in CandidateStatus.values:
        candidates = candidates.filter(source_candidate__status=status)
    source_hint = request.GET.get("source", "").strip()[:32]
    if source_hint:
        candidates = candidates.filter(source_candidate__source_type_hint=source_hint)
    definition_key = request.GET.get("definition", "").strip()[:100]
    if definition_key:
        candidates = candidates.filter(discovery_run__definition__definition_key=definition_key)
    domain = request.GET.get("domain", "").strip()[:255]
    if domain:
        candidates = candidates.filter(source_candidate__url_canonical__icontains=domain)
    return render(
        request,
        "discovery/candidate_list.html",
        {
            "page_obj": Paginator(candidates, PAGE_SIZE).get_page(request.GET.get("page")),
            "selected_status": status,
            "selected_source": source_hint,
            "selected_definition": definition_key,
            "selected_domain": domain,
            "definitions": SearchDefinition.objects.filter(active=True).order_by("name"),
        },
    )


@login_required
@permission_required("discovery.run_searchdefinition", raise_exception=True)
@require_POST
def run_definition(request: HttpRequest, definition_id: uuid.UUID) -> HttpResponse:
    definition = get_object_or_404(SearchDefinition, pk=definition_id, active=True)
    window_end = timezone.now()
    window_start = window_end - timedelta(days=definition.lookback_days)
    result = create_discovery_run(
        definition,
        logical_window_start=window_start,
        logical_window_end=window_end,
        reason="manual",
        actor=request.user,  # type: ignore[arg-type]
    )
    if result.created:
        messages.success(
            request,
            "Discovery was committed to PostgreSQL and queued through the durable outbox.",
        )
    else:
        messages.info(request, "The idempotent discovery run already exists.")
    return redirect("discovery:run-detail", run_id=result.run.pk)
