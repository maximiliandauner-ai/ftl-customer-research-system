import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.db import DatabaseError, connection, transaction
from django.test import override_settings

from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.sources.models import SourceArtifact, SourceSnapshot
from apps.sources.services import execute_source_fetch
from tests.unit.test_source_services import StaticFetcher, submit


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_source_artifact_and_snapshot_triggers_reject_mutation(tmp_path) -> None:
    assert connection.vendor == "postgresql"
    user = User.objects.create_user(username="source-trigger-test")
    submitted = submit(user, "sources.manual:postgres-trigger")
    assert submitted.pipeline_run is not None
    envelope = build_envelope(TaskOutbox.objects.get(pipeline_run=submitted.pipeline_run))
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_source_fetch(
            envelope,
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=StaticFetcher(),
        )
    artifact = SourceArtifact.objects.get()
    snapshot = SourceSnapshot.objects.get()

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "UPDATE sources_sourceartifact SET content_type = %s WHERE id = %s",
            ["text/plain", artifact.pk],
        )
    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM sources_sourcesnapshot WHERE id = %s", [snapshot.pk])

    artifact.refresh_from_db()
    snapshot.refresh_from_db()
    assert artifact.content_type == "text/html"
    assert SourceSnapshot.objects.filter(pk=snapshot.pk).exists()
