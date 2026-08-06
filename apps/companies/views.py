from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.companies.models import Company, CompanyStatus
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
    return render(
        request,
        "companies/company_detail.html",
        {"company": company, "contact_runs": contact_runs},
    )
