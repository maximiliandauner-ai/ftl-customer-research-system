import pytest
from django.contrib.auth.models import User
from django.db import DatabaseError, connection, transaction

from apps.jobs.models import EvidenceCatalog
from apps.signals.models import SignalEvidence
from tests.unit.test_job_services import poll_ashby
from tests.unit.test_signal_services import ashby_body, execute_only_signal_command


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_evidence_catalog_and_items_reject_mutation(tmp_path) -> None:
    assert connection.vendor == "postgresql"
    user = User.objects.create_user(username="signal-evidence-trigger")
    poll_ashby(
        user,
        "signals.postgres:evidence",
        ashby_body("Build workflow automation for operations."),
        tmp_path,
    )
    execute_only_signal_command()
    catalog = EvidenceCatalog.objects.get()
    item = catalog.items.get(public_id="EV-000002")

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE jobs_evidenceitem SET exact_text = %s WHERE id = %s",
            ["mutated", item.pk],
        )
    item.refresh_from_db()
    assert item.exact_text == "Build workflow automation for operations."

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE jobs_evidencecatalog SET item_count = 0 WHERE id = %s",
            [catalog.pk],
        )
    catalog.refresh_from_db()
    assert catalog.item_count == 2


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_signal_evidence_link_rejects_deletion(tmp_path) -> None:
    assert connection.vendor == "postgresql"
    user = User.objects.create_user(username="signal-link-trigger")
    poll_ashby(
        user,
        "signals.postgres:link",
        ashby_body("Build a governed knowledge base."),
        tmp_path,
    )
    execute_only_signal_command()
    link = SignalEvidence.objects.get()

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM signals_signalevidence WHERE id = %s", [link.pk])

    assert SignalEvidence.objects.filter(pk=link.pk).exists()
