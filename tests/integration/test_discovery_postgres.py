from datetime import UTC, datetime

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction

from apps.discovery.models import SearchDefinition

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_postgres_enforces_one_active_definition_version() -> None:
    call_command("bootstrap_ftl_platform", verbosity=0)
    active = SearchDefinition.objects.get(definition_key="ftl-capability-demand", active=True)

    with pytest.raises(IntegrityError), transaction.atomic():
        SearchDefinition.objects.create(
            definition_key=active.definition_key,
            version=active.version + 1,
            name="Conflicting active version",
            query_template="jobs",
            language="en",
            positive_terms=["automation"],
            active=True,
            max_candidates=10,
            lookback_days=7,
            payload_sha256="f" * 64,
            created_at=datetime.now(UTC),
        )
