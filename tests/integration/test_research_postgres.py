import json

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.test import override_settings

from apps.operations.commands import (
    COMPANIES_AGGREGATE_COMMAND_TYPE,
    RESEARCH_PUBLIC_COMMAND_TYPE,
    SIGNALS_CLASSIFY_COMMAND_TYPE,
)
from apps.operations.models import TaskOutbox
from apps.operations.outbox import build_envelope
from apps.opportunities.models import Opportunity
from apps.opportunities.services import execute_company_aggregation
from apps.research.models import ResearchSource
from apps.research.services import execute_public_research, request_standard_research
from apps.signals.classification import execute_signal_classification
from apps.signals.services import execute_signal_detection
from tests.unit.test_job_services import ASHBY_FIXTURE, poll_ashby
from tests.unit.test_research_services import FixtureResearchProvider


def _enabled_runtime():
    features = settings.RUNTIME_SETTINGS.features.model_copy(
        update={
            "openai_enabled": True,
            "web_search_enabled": True,
            "standard_research_enabled": True,
        }
    )
    return settings.RUNTIME_SETTINGS.model_copy(update={"features": features})


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_registered_research_sources_are_append_only(tmp_path) -> None:
    assert connection.vendor == "postgresql"
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username="research-source-trigger")
    payload = json.loads(ASHBY_FIXTURE.read_text())
    payload["jobs"][0]["descriptionPlain"] = (
        "Build workflow automation and data integration for operations."
    )
    poll_ashby(user, "research.postgres:source", json.dumps(payload).encode(), tmp_path)
    execute_signal_detection(build_envelope(TaskOutbox.objects.get(command_type="signals.detect")))
    execute_signal_classification(
        build_envelope(TaskOutbox.objects.get(command_type=SIGNALS_CLASSIFY_COMMAND_TYPE))
    )
    execute_company_aggregation(
        build_envelope(TaskOutbox.objects.get(command_type=COMPANIES_AGGREGATE_COMMAND_TYPE))
    )
    with override_settings(RUNTIME_SETTINGS=_enabled_runtime(), MEDIA_ROOT=tmp_path):
        request_standard_research(
            opportunity_id=Opportunity.objects.get().pk,
            actor=user,
        )
        execute_public_research(
            build_envelope(TaskOutbox.objects.get(command_type=RESEARCH_PUBLIC_COMMAND_TYPE)),
            provider=FixtureResearchProvider(),
        )
    source = ResearchSource.objects.get()

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute("DELETE FROM research_researchsource WHERE id = %s", [source.pk])

    assert ResearchSource.objects.filter(pk=source.pk).exists()
