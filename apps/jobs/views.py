from __future__ import annotations

import json
import uuid
from typing import Any

from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.jobs.models import JobPosting, PostingLifecycle

PAGE_SIZE = 30


def _snapshot_value(snapshot: Any, field_path: str) -> str:
    if snapshot is None:
        return "—"
    if field_path == "posting":
        return "Posting created"
    if field_path == "title":
        return str(snapshot.title)
    if field_path == "description_text":
        return (
            f"{len(snapshot.description_text)} characters · "
            f"{snapshot.semantic_hash[:16]}… semantic hash"
        )
    if field_path == "locations":
        return json.dumps(snapshot.locations_payload, ensure_ascii=False, sort_keys=True)[:2_000]
    if field_path == "normalizer_version":
        return str(snapshot.normalizer_version)
    if field_path.startswith("metadata."):
        return str(snapshot.metadata.get(field_path.removeprefix("metadata."), "—"))
    if field_path == "lifecycle_status":
        return "Lifecycle transition"
    if field_path == "successful_absence_count":
        return "Closure threshold reached"
    if field_path == "closure_reason":
        return "Deterministic closure policy"
    return "Changed"


def _change_rows(posting: JobPosting) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for event in posting.change_events.all():
        fields = [
            {
                "path": field_path,
                "before": _snapshot_value(event.old_snapshot, field_path),
                "after": _snapshot_value(event.new_snapshot, field_path),
            }
            for field_path in event.changed_fields[:50]
        ]
        rows.append({"event": event, "fields": fields})
    return rows


@login_required
@permission_required("jobs.view_jobposting", raise_exception=True)
@require_GET
def job_list(request: HttpRequest) -> HttpResponse:
    postings = JobPosting.objects.select_related(
        "company", "primary_source_endpoint"
    ).prefetch_related("locations")
    lifecycle = request.GET.get("status", "")
    if lifecycle in PostingLifecycle.values:
        postings = postings.filter(lifecycle_status=lifecycle)
    query = request.GET.get("q", "").strip()
    if query:
        postings = postings.filter(title__icontains=query[:200])
    return render(
        request,
        "jobs/job_list.html",
        {
            "page_obj": Paginator(postings, PAGE_SIZE).get_page(request.GET.get("page")),
            "selected_status": lifecycle,
            "query": query,
            "open_count": JobPosting.objects.filter(lifecycle_status=PostingLifecycle.OPEN).count(),
        },
    )


@login_required
@permission_required("jobs.view_jobposting", raise_exception=True)
@require_GET
def job_detail(request: HttpRequest, posting_id: uuid.UUID) -> HttpResponse:
    posting = get_object_or_404(
        JobPosting.objects.select_related(
            "company",
            "primary_source_endpoint",
            "current_snapshot__source_snapshot__artifact",
            "current_snapshot__parse_run",
        ).prefetch_related(
            "locations",
            "snapshots__source_snapshot__artifact",
            "observations__source_snapshot",
            "change_events__old_snapshot",
            "change_events__new_snapshot",
            "duplicate_relationships_as_primary__secondary_posting__company",
            "duplicate_relationships_as_secondary__primary_posting__company",
            "signal_events__detection_attempt",
            "signal_events__evidence_links",
        ),
        pk=posting_id,
    )
    duplicate_relationships = list(posting.duplicate_relationships_as_primary.all()) + list(
        posting.duplicate_relationships_as_secondary.all()
    )
    return render(
        request,
        "jobs/job_detail.html",
        {
            "posting": posting,
            "change_rows": _change_rows(posting),
            "duplicate_relationships": duplicate_relationships,
        },
    )
