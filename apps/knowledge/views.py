from __future__ import annotations

import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.knowledge.models import KnowledgeRegistryState, KnowledgeRelease
from apps.knowledge.services import KnowledgeValidationError, activate_knowledge_release


@login_required
@permission_required("knowledge.view_knowledgerelease", raise_exception=True)
@require_GET
def release_list(request: HttpRequest) -> HttpResponse:
    state = (
        KnowledgeRegistryState.objects.select_related("active_release")
        .filter(registry_key="default")
        .first()
    )
    return render(
        request,
        "knowledge/release_list.html",
        {
            "releases": KnowledgeRelease.objects.prefetch_related(
                "offers", "approved_claims", "assets"
            ),
            "active_release": state.active_release if state else None,
        },
    )


@login_required
@permission_required("knowledge.view_knowledgerelease", raise_exception=True)
@require_GET
def release_detail(request: HttpRequest, release_id: uuid.UUID) -> HttpResponse:
    release = get_object_or_404(
        KnowledgeRelease.objects.prefetch_related(
            "offers", "approved_claims", "prohibited_claims", "assets", "activation_events"
        ),
        pk=release_id,
    )
    state = KnowledgeRegistryState.objects.filter(registry_key="default").first()
    return render(
        request,
        "knowledge/release_detail.html",
        {
            "release": release,
            "is_active": bool(state and state.active_release_id == release.pk),
        },
    )


@login_required
@permission_required("knowledge.activate_knowledge", raise_exception=True)
@require_POST
def activate_release(request: HttpRequest, release_id: uuid.UUID) -> HttpResponse:
    try:
        event = activate_knowledge_release(
            release_id=release_id,
            actor=request.user,  # type: ignore[arg-type]
            reason=request.POST.get("reason", ""),
        )
    except KnowledgeValidationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Knowledge release v{event.activated_release.version} is now active.",
        )
    return redirect("knowledge:detail", release_id=release_id)
