import pytest
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.test import override_settings

from apps.companies.models import CompanyFieldObservation
from apps.companies.services import execute_company_enrichment, schedule_company_enrichment
from apps.operations.outbox import build_envelope
from tests.unit.test_company_enrichment import CompanyProfileFixtureFetcher, create_company


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
def test_postgres_company_profile_evidence_is_append_only(tmp_path) -> None:
    assert connection.vendor == "postgresql"
    company = create_company()
    scheduled = schedule_company_enrichment(company)
    assert scheduled is not None
    with override_settings(MEDIA_ROOT=tmp_path):
        execute_company_enrichment(
            build_envelope(scheduled.outbox),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=CompanyProfileFixtureFetcher(),
        )
    observation = CompanyFieldObservation.objects.first()
    assert observation is not None

    with (
        pytest.raises(DatabaseError, match="append-only"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "DELETE FROM companies_companyfieldobservation WHERE id = %s",
            [observation.pk],
        )

    assert CompanyFieldObservation.objects.filter(pk=observation.pk).exists()
