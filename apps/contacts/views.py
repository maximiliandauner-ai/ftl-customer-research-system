from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.contacts.models import (
    ContactResearchRun,
    ContactRoute,
    ContactSelection,
    SuppressionEntry,
)
from apps.contacts.services import (
    ContactValidationError,
    add_suppression,
    create_human_route,
    request_contact_research,
    review_contact_route,
    select_contact_route,
)

PAGE_SIZE = 30


@login_required
@permission_required("contacts.view_contactresearchrun", raise_exception=True)
@require_GET
def contact_list(request: HttpRequest) -> HttpResponse:
    runs = ContactResearchRun.objects.select_related(
        "opportunity__company", "solution_version", "pipeline_run"
    )
    return render(
        request,
        "contacts/contact_list.html",
        {"page_obj": Paginator(runs, PAGE_SIZE).get_page(request.GET.get("page"))},
    )


@login_required
@permission_required("contacts.view_contactresearchrun", raise_exception=True)
@require_GET
def contact_detail(request: HttpRequest, contact_run_id: uuid.UUID) -> HttpResponse:
    contact_run = get_object_or_404(
        ContactResearchRun.objects.select_related(
            "opportunity__company", "solution_version", "pipeline_run", "buyer_role_result"
        ).prefetch_related(
            "buyer_role_result__roles",
            "source_targets__research_source",
            "source_targets__artifact__evidence_items",
            "opportunity__company__contact_routes__buyer_role",
            "opportunity__company__suppression_entries",
            "opportunity__contact_selections__contact_route",
        ),
        pk=contact_run_id,
    )
    return render(
        request,
        "contacts/contact_detail.html",
        {
            "contact_run": contact_run,
            "routes": ContactRoute.objects.filter(company=contact_run.opportunity.company),
            "suppressions": SuppressionEntry.objects.filter(
                company=contact_run.opportunity.company
            ),
            "selections": ContactSelection.objects.filter(opportunity=contact_run.opportunity),
        },
    )


@login_required
@permission_required("contacts.request_contact_research", raise_exception=True)
@require_POST
def request_contacts(request: HttpRequest, opportunity_id: uuid.UUID) -> HttpResponse:
    try:
        scheduled = request_contact_research(
            opportunity_id=opportunity_id,
            actor=request.user,  # type: ignore[arg-type]
            request_id=getattr(request, "request_id", None),
        )
    except ContactValidationError as exc:
        messages.error(request, str(exc))
        return redirect("opportunities:detail", opportunity_id=opportunity_id)
    messages.success(request, "Buyer-role and registered-source contact research queued.")
    return redirect("contacts:detail", contact_run_id=scheduled.contact_research_run.pk)


@login_required
@permission_required("contacts.add_human_route", raise_exception=True)
@require_POST
def add_human_route(request: HttpRequest, contact_run_id: uuid.UUID) -> HttpResponse:
    contact_run = get_object_or_404(ContactResearchRun, pk=contact_run_id)
    try:
        create_human_route(
            company_id=contact_run.opportunity.company_id,
            buyer_role_id=uuid.UUID(request.POST.get("buyer_role_id", "")),
            actor=request.user,  # type: ignore[arg-type]
            route_type=request.POST.get("route_type", ""),
            value=request.POST.get("value", ""),
            provenance_note=request.POST.get("provenance_note", ""),
            request_id=getattr(request, "request_id", None),
        )
    except (ContactValidationError, ValueError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, "Human-origin route recorded with protected value and provenance."
        )
    return redirect("contacts:detail", contact_run_id=contact_run_id)


@login_required
@permission_required("contacts.review_contact_route", raise_exception=True)
@require_POST
def review_route(request: HttpRequest, route_id: uuid.UUID) -> HttpResponse:
    route = get_object_or_404(
        ContactRoute.objects.select_related("buyer_role__result"), pk=route_id
    )
    buyer_role = route.buyer_role
    if buyer_role is None:
        messages.error(request, "The route has no buyer-role binding.")
        return redirect("contacts:list")
    try:
        review_contact_route(
            route_id=route_id,
            actor=request.user,  # type: ignore[arg-type]
            outreach_eligibility=request.POST.get("outreach_eligibility", ""),
            legal_review_status=request.POST.get("legal_review_status", ""),
            jurisdiction=request.POST.get("jurisdiction", ""),
            recommendation=request.POST.get("recommendation", ""),
            reason=request.POST.get("reason", ""),
            request_id=getattr(request, "request_id", None),
        )
    except ContactValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Independent route and legal review states updated.")
    return redirect("contacts:detail", contact_run_id=buyer_role.result.contact_research_run_id)


@login_required
@permission_required("contacts.select_contact_route", raise_exception=True)
@require_POST
def select_route(request: HttpRequest, route_id: uuid.UUID) -> HttpResponse:
    route = get_object_or_404(
        ContactRoute.objects.select_related("buyer_role__result"), pk=route_id
    )
    buyer_role = route.buyer_role
    if buyer_role is None:
        messages.error(request, "The route has no buyer-role binding.")
        return redirect("contacts:list")
    contact_run = buyer_role.result.contact_research_run
    try:
        select_contact_route(
            opportunity_id=contact_run.opportunity_id,
            route_id=route_id,
            actor=request.user,  # type: ignore[arg-type]
            contact_purpose=request.POST.get("contact_purpose", ""),
            lawful_basis_note=request.POST.get("lawful_basis_note", ""),
            retention_policy=request.POST.get("retention_policy", ""),
            request_id=getattr(request, "request_id", None),
        )
    except ContactValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Exact reviewed target route selected; no message was generated.")
    return redirect("contacts:detail", contact_run_id=contact_run.pk)


@login_required
@permission_required("contacts.add_suppression", raise_exception=True)
@require_POST
def suppress_route(request: HttpRequest, route_id: uuid.UUID) -> HttpResponse:
    route = get_object_or_404(
        ContactRoute.objects.select_related("buyer_role__result"), pk=route_id
    )
    buyer_role = route.buyer_role
    if buyer_role is None:
        messages.error(request, "The route has no buyer-role binding.")
        return redirect("contacts:list")
    try:
        add_suppression(
            actor=request.user,  # type: ignore[arg-type]
            route_id=route_id,
            reason_type=request.POST.get("reason_type", ""),
            reason_note=request.POST.get("reason_note", ""),
            request_id=getattr(request, "request_id", None),
        )
    except ContactValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Suppression applied synchronously.")
    return redirect("contacts:detail", contact_run_id=buyer_role.result.contact_research_run_id)
