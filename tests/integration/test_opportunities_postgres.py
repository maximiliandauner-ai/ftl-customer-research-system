import json

import pytest
from django.contrib.auth.models import User
from django.db import DatabaseError, connection, transaction

from apps.operations.commands import (
    COMPANIES_AGGREGATE_COMMAND_TYPE,
    SIGNALS_CLASSIFY_COMMAND_TYPE,
)
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.opportunities.services import execute_company_aggregation
from apps.signals.classification import execute_signal_classification
from apps.signals.models import SignalAssessmentEvidence
from apps.signals.services import execute_signal_detection
from tests.unit.test_job_services import ASHBY_FIXTURE, poll_ashby


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_assessment_evidence_link_is_append_only(tmp_path) -> None:
    assert connection.vendor == "postgresql"
    user = User.objects.create_user(username="assessment-evidence-trigger")
    payload = json.loads(ASHBY_FIXTURE.read_text())
    payload["jobs"][0]["descriptionPlain"] = (
        "Build workflow automation and data integration for operations."
    )
    poll_ashby(user, "assessment.postgres:evidence", json.dumps(payload).encode(), tmp_path)
    detection = TaskOutbox.objects.get(command_type="signals.detect")
    execute_signal_detection(build_envelope(detection))
    classification = TaskOutbox.objects.get(command_type=SIGNALS_CLASSIFY_COMMAND_TYPE)
    execute_signal_classification(build_envelope(classification))
    link = SignalAssessmentEvidence.objects.get()

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM signals_signalassessmentevidence WHERE id = %s", [link.pk])

    assert SignalAssessmentEvidence.objects.filter(pk=link.pk).exists()
    aggregation = TaskOutbox.objects.get(command_type=COMPANIES_AGGREGATE_COMMAND_TYPE)
    assert execute_company_aggregation(build_envelope(aggregation))
