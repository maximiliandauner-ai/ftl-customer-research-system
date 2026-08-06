import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.test import override_settings

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.contacts.models import BuyerRoleHypothesis, ContactEvidence
from apps.contacts.services import (
    execute_buyer_role_inference,
    execute_contact_source_scan,
    request_contact_research,
)
from apps.operations.commands import (
    BUYER_ROLES_INFER_COMMAND_TYPE,
    CONTACT_SOURCE_SCAN_COMMAND_TYPE,
)
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from tests.unit.test_contact_services import (
    FixtureContactFetcher,
    _approved_solution,
    _contact_runtime,
)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_rejects_contact_evidence_mutation(tmp_path) -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="contact-postgres-founder")
    assign_team_role(
        user=user,
        role=TeamRoleName.FOUNDER,
        actor=None,
        reason="contact_postgres_fixture",
    )
    with override_settings(RUNTIME_SETTINGS=_contact_runtime(), MEDIA_ROOT=tmp_path):
        opportunity, _solution = _approved_solution(user, tmp_path)
        request_contact_research(opportunity_id=opportunity.pk, actor=user)
        execute_buyer_role_inference(
            build_envelope(TaskOutbox.objects.get(command_type=BUYER_ROLES_INFER_COMMAND_TYPE))
        )
        execute_contact_source_scan(
            build_envelope(TaskOutbox.objects.get(command_type=CONTACT_SOURCE_SCAN_COMMAND_TYPE)),
            fetcher=FixtureContactFetcher(b'<a href="mailto:info@acme.example">Official inbox</a>'),
        )

    role = BuyerRoleHypothesis.objects.get()
    evidence = ContactEvidence.objects.get()
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE contacts_buyerrolehypothesis SET responsibility_match = %s WHERE id = %s",
            ["mutated", role.pk],
        )
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("DELETE FROM contacts_contactevidence WHERE id = %s", [evidence.pk])
