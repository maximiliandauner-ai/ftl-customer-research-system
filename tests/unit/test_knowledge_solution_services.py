import json
import shutil
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.knowledge.models import Asset, KnowledgeRegistryState, KnowledgeRelease
from apps.knowledge.services import (
    KnowledgeValidationError,
    activate_knowledge_release,
    sync_knowledge_release,
)
from apps.operations.commands import (
    ASSET_MATCH_COMMAND_TYPE,
    RESEARCH_EXTRACT_COMMAND_TYPE,
    RESEARCH_PUBLIC_COMMAND_TYPE,
    SOLUTION_DESIGN_COMMAND_TYPE,
)
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.research.services import (
    execute_public_research,
    execute_research_extraction,
    request_standard_research,
)
from apps.solutions.models import (
    AssetMatch,
    AssetSelection,
    OpportunitySolutionState,
    SolutionStateStatus,
    SolutionVersion,
)
from apps.solutions.services import (
    SolutionValidationError,
    approve_solution,
    create_edited_solution,
    execute_asset_matching,
    execute_solution_design,
    request_solution_design,
)
from tests.unit.test_research_services import (
    FixtureResearchProvider,
    _opportunity,
    _runtime,
)

SOURCE_ROOT = Path(__file__).parents[2] / "knowledge_base"


def _complete_research(user: User, tmp_path: object):
    opportunity = _opportunity(user, tmp_path)
    provider = FixtureResearchProvider()
    scheduled = request_standard_research(opportunity_id=opportunity.pk, actor=user)
    execute_public_research(
        build_envelope(TaskOutbox.objects.get(command_type=RESEARCH_PUBLIC_COMMAND_TYPE)),
        provider=provider,
    )
    execute_research_extraction(
        build_envelope(TaskOutbox.objects.get(command_type=RESEARCH_EXTRACT_COMMAND_TYPE)),
        provider=provider,
    )
    return opportunity, scheduled.research_run


def _catalog_with_assets(tmp_path: Path, assets: list[dict[str, object]]) -> Path:
    root = tmp_path / "editorial"
    shutil.copytree(SOURCE_ROOT, root)
    (root / "assets" / "assets.json").write_text(json.dumps(assets), encoding="utf-8")
    return root


def _asset(asset_id: str, *, confidentiality: str, approved: bool) -> dict[str, object]:
    now = timezone.now().isoformat()
    return {
        "asset_id": asset_id,
        "version": 1,
        "title": f"{asset_id} workflow system",
        "type": "case_study",
        "public_url": f"https://example.com/assets/{asset_id}",
        "short_description": "A public create and build workflow example.",
        "detailed_description": "Demonstrates a reusable workflow and enablement method.",
        "capability_tags": ["workflow", "enablement"],
        "ftl_layers": ["create", "build", "enable"],
        "industries": ["professional_services"],
        "languages": ["en", "de"],
        "audiences": ["public_business"],
        "confidentiality": confidentiality,
        "approved_for_external_use": approved,
        "status": "live",
        "last_reviewed_at": now,
        "url_last_checked_at": now,
    }


@pytest.mark.django_db
def test_sync_and_activation_are_separate_and_idempotent() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="knowledge-editor")

    first = sync_knowledge_release(source_root=SOURCE_ROOT, source_commit="abcdef1", actor=user)
    second = sync_knowledge_release(source_root=SOURCE_ROOT, source_commit="abcdef1", actor=user)

    assert first.created
    assert not second.created
    assert first.release.pk == second.release.pk
    assert KnowledgeRegistryState.objects.count() == 0
    assert first.release.offers.get().key == "pilot_plus_system"
    assert first.release.assets.count() == 0

    event = activate_knowledge_release(
        release_id=first.release.pk,
        actor=user,
        reason="Reviewed initial local asset database.",
    )
    assert event.activated_release == first.release
    assert KnowledgeRegistryState.objects.get().active_release == first.release


@pytest.mark.django_db
def test_knowledge_management_commands_enforce_operator_permissions() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    researcher = User.objects.create_user(username="knowledge-command-researcher")
    founder = User.objects.create_user(username="knowledge-command-founder")
    assign_team_role(
        user=researcher,
        role=TeamRoleName.RESEARCHER,
        actor=None,
        reason="command_permission_fixture",
    )
    assign_team_role(
        user=founder,
        role=TeamRoleName.FOUNDER,
        actor=None,
        reason="command_permission_fixture",
    )

    with pytest.raises(CommandError, match="may not sync"):
        call_command(
            "sync_ftl_knowledge",
            commit="abcdef6",
            validate=True,
            username=researcher.username,
            source_root=SOURCE_ROOT,
        )

    call_command(
        "sync_ftl_knowledge",
        commit="abcdef6",
        validate=True,
        username=founder.username,
        source_root=SOURCE_ROOT,
    )
    release = KnowledgeRelease.objects.get()
    with pytest.raises(CommandError, match="may not activate"):
        call_command(
            "activate_ftl_knowledge",
            release.pk,
            username=researcher.username,
            reason="Permission boundary fixture.",
        )


@pytest.mark.django_db
def test_solution_and_valid_zero_asset_match_are_durable_and_approvable(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="solution-fixture")
    with override_settings(RUNTIME_SETTINGS=_runtime(enabled=True), MEDIA_ROOT=tmp_path):
        opportunity, _research = _complete_research(user, tmp_path)
        release = sync_knowledge_release(
            source_root=SOURCE_ROOT, source_commit="abcdef2", actor=user
        ).release
        activate_knowledge_release(
            release_id=release.pk,
            actor=user,
            reason="Reviewed fixture release for solution testing.",
        )
        scheduled = request_solution_design(opportunity_id=opportunity.pk, actor=user)
        design_outbox = TaskOutbox.objects.get(command_type=SOLUTION_DESIGN_COMMAND_TYPE)
        assert execute_solution_design(build_envelope(design_outbox))
        match_outbox = TaskOutbox.objects.get(command_type=ASSET_MATCH_COMMAND_TYPE)
        assert execute_asset_matching(build_envelope(match_outbox))
        assert execute_asset_matching(build_envelope(match_outbox)) is False

    solution = SolutionVersion.objects.get()
    match = AssetMatch.objects.get(solution_version=solution)
    state = OpportunitySolutionState.objects.get(opportunity=opportunity)
    assert scheduled.pipeline_run.status == "queued"
    scheduled.pipeline_run.refresh_from_db()
    assert scheduled.pipeline_run.status == "complete"
    assert solution.structured_output["entry_offer"] == "pilot_plus_system"
    assert solution.structured_output["problem_hypothesis"]["evidence_refs"] == ["CLM-000001"]
    assert match.output_payload["selected_assets"] == []
    assert "No current externally safe asset" in match.output_payload["unknowns"][0]
    assert state.status == SolutionStateStatus.DRAFT

    approve_solution(
        solution_id=solution.pk,
        actor=user,
        reason="Reviewed exact solution and zero-asset result.",
        request_id=None,
    )
    state.refresh_from_db()
    opportunity.refresh_from_db()
    assert state.status == SolutionStateStatus.APPROVED
    assert state.approved_version == solution
    assert opportunity.solution_status == "complete"


@pytest.mark.django_db
def test_asset_match_filters_confidential_asset_and_selects_public_current_asset(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="asset-filter-fixture")
    root = _catalog_with_assets(
        tmp_path,
        [
            _asset("public_workflow", confidentiality="public", approved=True),
            _asset("private_client", confidentiality="confidential_client", approved=False),
        ],
    )
    with override_settings(RUNTIME_SETTINGS=_runtime(enabled=True), MEDIA_ROOT=tmp_path):
        opportunity, _research = _complete_research(user, tmp_path)
        release = sync_knowledge_release(
            source_root=root, source_commit="abcdef3", actor=user
        ).release
        activate_knowledge_release(
            release_id=release.pk,
            actor=user,
            reason="Reviewed public and confidential asset filters.",
        )
        request_solution_design(opportunity_id=opportunity.pk, actor=user)
        execute_solution_design(
            build_envelope(TaskOutbox.objects.get(command_type=SOLUTION_DESIGN_COMMAND_TYPE))
        )
        execute_asset_matching(
            build_envelope(TaskOutbox.objects.get(command_type=ASSET_MATCH_COMMAND_TYPE))
        )

    match = AssetMatch.objects.get()
    selection = AssetSelection.objects.get()
    assert selection.asset.asset_id == "public_workflow"
    assert match.excluded_reasons["private_client"] == "confidentiality"
    assert "private_client" not in {
        item["asset_id"] for item in match.output_payload["selected_assets"]
    }


@pytest.mark.django_db
def test_human_edit_rejects_fabricated_evidence_reference(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="solution-edit-fixture")
    with override_settings(RUNTIME_SETTINGS=_runtime(enabled=True), MEDIA_ROOT=tmp_path):
        opportunity, _research = _complete_research(user, tmp_path)
        release = sync_knowledge_release(
            source_root=SOURCE_ROOT, source_commit="abcdef4", actor=user
        ).release
        activate_knowledge_release(
            release_id=release.pk,
            actor=user,
            reason="Reviewed release before structured editing.",
        )
        request_solution_design(opportunity_id=opportunity.pk, actor=user)
        execute_solution_design(
            build_envelope(TaskOutbox.objects.get(command_type=SOLUTION_DESIGN_COMMAND_TYPE))
        )
        source = SolutionVersion.objects.get()
        edited = dict(source.structured_output)
        edited["problem_hypothesis"] = {
            **edited["problem_hypothesis"],
            "evidence_refs": ["CLM-999999"],
        }
        with pytest.raises(SolutionValidationError, match="outside"):
            create_edited_solution(
                solution_id=source.pk,
                actor=user,
                payload_json=json.dumps(edited),
                request_id=None,
            )


@pytest.mark.django_db
def test_knowledge_catalog_rejects_external_approval_for_confidential_asset(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="knowledge-invalid-asset")
    root = _catalog_with_assets(
        tmp_path,
        [_asset("unsafe_asset", confidentiality="embargoed", approved=True)],
    )

    with pytest.raises(KnowledgeValidationError, match="Only public assets"):
        sync_knowledge_release(source_root=root, source_commit="abcdef5", actor=user)

    assert KnowledgeRelease.objects.count() == 0
    assert Asset.objects.count() == 0
