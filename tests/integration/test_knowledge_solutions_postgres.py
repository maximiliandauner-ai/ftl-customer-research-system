import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.test import override_settings

from apps.knowledge.services import activate_knowledge_release, sync_knowledge_release
from apps.operations.commands import ASSET_MATCH_COMMAND_TYPE, SOLUTION_DESIGN_COMMAND_TYPE
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.solutions.models import SolutionVersion
from apps.solutions.services import (
    execute_asset_matching,
    execute_solution_design,
    request_solution_design,
)
from tests.unit.test_knowledge_solution_services import SOURCE_ROOT, _complete_research
from tests.unit.test_research_services import _runtime


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_knowledge_and_solution_versions_are_append_only(tmp_path) -> None:
    assert connection.vendor == "postgresql"
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="knowledge-solution-trigger")
    with override_settings(RUNTIME_SETTINGS=_runtime(enabled=True), MEDIA_ROOT=tmp_path):
        opportunity, _research = _complete_research(user, tmp_path)
        release = sync_knowledge_release(
            source_root=SOURCE_ROOT,
            source_commit="abcde91",
            actor=user,
        ).release
        activate_knowledge_release(
            release_id=release.pk,
            actor=user,
            reason="Reviewed PostgreSQL immutability fixture.",
        )
        request_solution_design(opportunity_id=opportunity.pk, actor=user)
        execute_solution_design(
            build_envelope(TaskOutbox.objects.get(command_type=SOLUTION_DESIGN_COMMAND_TYPE))
        )
        execute_asset_matching(
            build_envelope(TaskOutbox.objects.get(command_type=ASSET_MATCH_COMMAND_TYPE))
        )
    solution = SolutionVersion.objects.get()

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE knowledge_knowledgerelease SET source_commit = %s WHERE id = %s",
            ["fffffff", release.pk],
        )

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE solutions_solutionversion SET output_sha256 = %s WHERE id = %s",
            ["0" * 64, solution.pk],
        )

    solution.refresh_from_db()
    assert solution.output_sha256 != "0" * 64
