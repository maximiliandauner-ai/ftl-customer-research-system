from __future__ import annotations

import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.sources.contracts import SubmitPublicSourceV1
from apps.sources.forms import PublicSourceSubmissionForm
from apps.sources.models import (
    CandidateStatus,
    FetchAttempt,
    SourceArtifact,
    SourceCandidate,
    SourceEndpoint,
)
from apps.sources.services import submit_public_source

PAGE_SIZE = 30


def _request_id(request: HttpRequest) -> uuid.UUID:
    return request.request_id  # type: ignore[attr-defined,no-any-return]


def _submission_form() -> PublicSourceSubmissionForm:
    return PublicSourceSubmissionForm(initial={"idempotency_key": f"sources.manual:{uuid.uuid4()}"})


@login_required
@permission_required("sources.view_sourcecandidate", raise_exception=True)
@require_http_methods(["GET"])
def source_index(request: HttpRequest) -> HttpResponse:
    candidates = SourceCandidate.objects.select_related(
        "submitted_by", "registered_endpoint", "pipeline_run"
    )
    status = request.GET.get("status", "")
    if status in CandidateStatus.values:
        candidates = candidates.filter(status=status)
    return render(
        request,
        "sources/index.html",
        {
            "page_obj": Paginator(candidates, PAGE_SIZE).get_page(request.GET.get("page")),
            "selected_status": status,
            "endpoint_count": SourceEndpoint.objects.count(),
            "artifact_count": SourceArtifact.objects.count(),
            "failed_count": SourceCandidate.objects.filter(
                status__in=(CandidateStatus.REJECTED, CandidateStatus.UNSAFE)
            ).count(),
        },
    )


@login_required
@permission_required("sources.submit_public_source", raise_exception=True)
@require_http_methods(["GET", "POST"])
def submit_source(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        return render(request, "sources/submit.html", {"form": _submission_form()})
    form = PublicSourceSubmissionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "The public-source request needs correction.")
        return render(request, "sources/submit.html", {"form": form}, status=400)
    command = SubmitPublicSourceV1(
        requested_url=form.cleaned_data["requested_url"],
        company_name=form.cleaned_data.get("company_name") or None,
        company_domain=form.cleaned_data.get("company_domain") or None,
        public_source_confirmed=True,
        idempotency_key=form.cleaned_data["idempotency_key"],
        request_id=_request_id(request),
    )
    result = submit_public_source(
        command=command,
        actor=request.user,  # type: ignore[arg-type]
        policy=settings.RUNTIME_SETTINGS.fetch,
    )
    if result.accepted:
        messages.success(
            request,
            "The source was committed to PostgreSQL and queued for a policy-checked fetch.",
        )
    else:
        messages.error(request, result.candidate.rejection_reason)
    return redirect("sources:candidate-detail", candidate_id=result.candidate.pk)


@login_required
@permission_required("sources.view_sourcecandidate", raise_exception=True)
@require_http_methods(["GET"])
def candidate_detail(request: HttpRequest, candidate_id: uuid.UUID) -> HttpResponse:
    candidate = get_object_or_404(
        SourceCandidate.objects.select_related(
            "submitted_by",
            "registered_endpoint__company",
            "pipeline_run",
        ),
        pk=candidate_id,
    )
    return render(request, "sources/candidate_detail.html", {"candidate": candidate})


@login_required
@permission_required("sources.view_sourceendpoint", raise_exception=True)
@require_http_methods(["GET"])
def endpoint_detail(request: HttpRequest, endpoint_id: uuid.UUID) -> HttpResponse:
    endpoint = get_object_or_404(
        SourceEndpoint.objects.select_related("company", "candidate").prefetch_related(
            "fetch_attempts",
            "snapshots__artifact",
            "snapshots__parse_attempts__pipeline_run",
            "job_postings",
        ),
        pk=endpoint_id,
    )
    return render(request, "sources/endpoint_detail.html", {"endpoint": endpoint})


@login_required
@permission_required("sources.view_fetchattempt", raise_exception=True)
@require_http_methods(["GET"])
def attempt_detail(request: HttpRequest, attempt_id: uuid.UUID) -> HttpResponse:
    attempt = get_object_or_404(
        FetchAttempt.objects.select_related("source_endpoint", "pipeline_run"),
        pk=attempt_id,
    )
    return render(request, "sources/attempt_detail.html", {"attempt": attempt})


@login_required
@permission_required("sources.view_sourceartifact", raise_exception=True)
@require_http_methods(["GET"])
def artifact_detail(request: HttpRequest, artifact_id: uuid.UUID) -> HttpResponse:
    artifact = get_object_or_404(
        SourceArtifact.objects.select_related("source_endpoint"),
        pk=artifact_id,
    )
    return render(request, "sources/artifact_detail.html", {"artifact": artifact})
