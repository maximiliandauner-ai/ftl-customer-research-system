from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.companies.models import Company, CompanyProfileRun, CompanyStatus
from apps.companies.services import schedule_company_enrichment
from apps.contacts.models import ContactResearchRun

PAGE_SIZE = 30


@login_required
@permission_required("companies.view_company", raise_exception=True)
@require_GET
def company_list(request: HttpRequest) -> HttpResponse:
    companies = Company.objects.prefetch_related("domains", "source_endpoints")
    status = request.GET.get("status", "")
    if status in CompanyStatus.values:
        companies = companies.filter(status=status)
    page_obj = Paginator(companies, PAGE_SIZE).get_page(request.GET.get("page"))
    return render(
        request,
        "companies/company_list.html",
        {"page_obj": page_obj, "selected_status": status},
    )


@login_required
@permission_required("companies.view_company", raise_exception=True)
@require_GET
def company_detail(request: HttpRequest, company_id: uuid.UUID) -> HttpResponse:
    company = get_object_or_404(
        Company.objects.prefetch_related(
            "domains",
            "aliases",
            "source_endpoints__fetch_attempts",
            "source_endpoints__snapshots",
            "job_postings__locations",
            "signal_events__posting",
            "signal_events__evidence_links",
            "opportunities",
            "company_assessments__patterns",
            "contact_routes__buyer_role",
        ),
        pk=company_id,
    )
    contact_runs = (
        ContactResearchRun.objects.filter(opportunity__company=company)
        .select_related("solution_version", "buyer_role_result")
        .prefetch_related("buyer_role_result__roles", "source_targets")
    )
    latest_profile_run = (
        CompanyProfileRun.objects.filter(company=company)
        .select_related("pipeline_run")
        .prefetch_related("sources", "field_observations__source")
        .first()
    )
    profile_observations = (
        latest_profile_run.field_observations.filter(applied=True).select_related("source")
        if latest_profile_run is not None
        else ()
    )
    return render(
        request,
        "companies/company_detail.html",
        {
            "company": company,
            "contact_runs": contact_runs,
            "latest_profile_run": latest_profile_run,
            "profile_observations": profile_observations,
        },
    )


@login_required
@permission_required("companies.request_company_enrichment", raise_exception=True)
@require_POST
def request_company_enrichment(request: HttpRequest, company_id: uuid.UUID) -> HttpResponse:
    company = get_object_or_404(Company, pk=company_id)
    scheduled = schedule_company_enrichment(
        company,
        actor=request.user,  # type: ignore[arg-type]
        request_id=getattr(request, "request_id", None),
    )
    if scheduled is None:
        messages.error(request, "A non-disputed company domain is required for public enrichment.")
    elif scheduled.created:
        messages.success(
            request,
            "Official-site company enrichment was committed and queued through the durable outbox.",
        )
    else:
        messages.info(
            request, "This company's current daily enrichment is already queued or recorded."
        )
    return redirect("companies:detail", company_id=company.pk)
