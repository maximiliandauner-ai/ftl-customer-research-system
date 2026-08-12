import hashlib
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.companies.models import (
    Company,
    CompanyDomain,
    CompanyEnrichmentStatus,
    CompanyFieldObservation,
    CompanyProfileRun,
    CompanyStatus,
    DomainVerificationStatus,
)
from apps.companies.profile_parser import parse_company_profile_page
from apps.companies.services import execute_company_enrichment, schedule_company_enrichment
from apps.companies.tasks import (
    enrich_company_profile_task,
    schedule_company_profile_refresh_task,
)
from apps.operations.commands import COMPANY_PROFILE_ENRICH_COMMAND_TYPE
from apps.operations.contracts import TaskEnvelopeV2
from apps.operations.models import PipelineStatus, TaskOutbox
from apps.operations.outbox import build_envelope
from apps.sources.contracts import SafeFetchResultV1

ROOT_HTML = b"""
<!doctype html><html><head>
<meta property="og:site_name" content="Anyland">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Organization","name":"AI Studio Anyland",
 "alternateName":"Anyland GmbH","url":"https://anyland.de/"}
</script></head><body><main>
<p>Wir sind das AI Studio fuer TV- und Digital-Kampagnen, AI Video,
AI Images und Avatare aus Deutschland.</p>
<p>Our team has 2-10 employees.</p>
<a href="/impressum/">Impressum</a>
</main></body></html>
"""

IMPRINT_HTML = b"""
<!doctype html><html><head><meta property="og:site_name" content="Anyland">
<script type="application/ld+json">
{"@type":"Organization","name":"Anyland","legalName":"Anyland GmbH",
 "description":"Impressum Anyland GmbH with registration, management and legal contact details."}
</script></head><body>
<main><h1>Impressum</h1><p>Anyland GmbH</p><address>Haferwende 1<br>28357 Bremen</address>
<p>Sitz: Bremen<br>Amtsgericht Bremen<br>HRB 37772<br>USt.-ID: DE 351 886 536</p></main>
</body></html>
"""


class CompanyProfileFixtureFetcher:
    def __init__(self, *, identity_mismatch: bool = False) -> None:
        self.identity_mismatch = identity_mismatch
        self.calls: list[str] = []

    def fetch(self, requested_url: str, *, etag: str = "", last_modified: str = ""):
        self.calls.append(requested_url)
        body = IMPRINT_HTML if "impressum" in requested_url else ROOT_HTML
        if self.identity_mismatch:
            body = body.replace(b"Anyland", b"Different Brand")
        return SafeFetchResultV1(
            requested_url=requested_url,
            final_url=requested_url,
            status_code=200,
            retrieved_at_iso=datetime.now(UTC).isoformat(),
            content_type="text/html",
            encoding="utf-8",
            headers_filtered={},
            body=body,
            body_sha256=hashlib.sha256(body).hexdigest(),
            body_size_bytes=len(body),
            elapsed_ms=5,
            redirect_chain=[],
        )


def create_company(*, industry: str = "") -> Company:
    company = Company.objects.create(
        name="Anyland",
        normalized_name="anyland",
        industry_key=industry,
        status=CompanyStatus.PROVISIONAL,
    )
    now = timezone.now()
    CompanyDomain.objects.create(
        company=company,
        hostname_ascii="anyland.de",
        hostname_unicode="anyland.de",
        registrable_domain="anyland.de",
        is_primary=True,
        verification_status=DomainVerificationStatus.UNVERIFIED,
        first_seen_at=now,
        last_seen_at=now,
    )
    return company


def test_profile_parser_extracts_official_identity_and_discovery_links() -> None:
    parsed = parse_company_profile_page(
        page_url="https://anyland.de/",
        body=ROOT_HTML,
        encoding="utf-8",
    )

    assert "Anyland GmbH" in parsed.identity_names
    assert "https://anyland.de/impressum/" in parsed.discovered_urls
    values = {field.field_name: field.value for field in parsed.fields}
    assert values["legal_name"] == "Anyland GmbH"
    assert values["industry_key"] == "creative_ai_production"
    assert values["employee_range"] == "1_10"
    assert values["description"].startswith("Wir sind das AI Studio")


def test_profile_parser_rejects_footer_and_narrative_false_positives() -> None:
    html = b"""
    <html><head>
      <meta property="og:site_name" content="Hostinger">
      <script type="application/ld+json">
      {"@type":"Organization","name":"Hostinger","legalName":"Hosting Hostinger",
       "description":"A web hosting provider and website builder."}
      </script>
    </head><body>
      <p>Headquarters: We launched the first-class cPanel web hosting brand Hosting24.com</p>
      <p>Build websites for your clients with our agency tools.</p>
      <footer>Copyright 2026 Hostinger, Inc.</footer>
    </body></html>
    """

    parsed = parse_company_profile_page(
        page_url="https://www.hostinger.com/about",
        body=html,
        encoding="utf-8",
    )

    values = {field.field_name: field.value for field in parsed.fields}
    assert "legal_name" not in values
    assert "headquarters_city" not in values
    assert values["company_type"] == "company"
    assert values["industry_key"] == "web_hosting_and_cloud"


@pytest.mark.django_db
def test_company_enrichment_fetches_official_pages_applies_fields_and_provenance(tmp_path) -> None:
    user = User.objects.create_user(username="company-enrichment")
    company = create_company()
    scheduled = schedule_company_enrichment(company, actor=user)
    assert scheduled is not None
    assert scheduled.created is True
    assert scheduled.outbox.command_type == COMPANY_PROFILE_ENRICH_COMMAND_TYPE

    with override_settings(MEDIA_ROOT=tmp_path):
        execute_company_enrichment(
            build_envelope(scheduled.outbox),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=CompanyProfileFixtureFetcher(),
        )

    company.refresh_from_db()
    scheduled.enrichment_run.refresh_from_db()
    scheduled.enrichment_run.pipeline_run.refresh_from_db()
    domain = company.domains.get()
    assert company.legal_name == "Anyland GmbH"
    assert company.company_type == "agency"
    assert company.industry_key == "creative_ai_production"
    assert company.headquarters_city == "Bremen"
    assert company.headquarters_country == "DE"
    assert company.employee_range == "1_10"
    assert company.description.startswith("Wir sind das AI Studio")
    assert company.status == CompanyStatus.ACTIVE
    assert domain.verification_status == DomainVerificationStatus.SOURCE_CONFIRMED
    assert scheduled.enrichment_run.status == CompanyEnrichmentStatus.COMPLETE
    assert scheduled.enrichment_run.sources.count() == 2
    assert CompanyFieldObservation.objects.filter(applied=True).count() == 7
    assert scheduled.enrichment_run.pipeline_run.status == PipelineStatus.COMPLETE


@pytest.mark.django_db
def test_enrichment_does_not_overwrite_a_manual_company_value(tmp_path) -> None:
    company = create_company(industry="manual_industry")
    scheduled = schedule_company_enrichment(company)
    assert scheduled is not None

    with override_settings(MEDIA_ROOT=tmp_path):
        execute_company_enrichment(
            build_envelope(scheduled.outbox),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=CompanyProfileFixtureFetcher(),
        )

    company.refresh_from_db()
    assert company.industry_key == "manual_industry"
    industry_observation = CompanyFieldObservation.objects.filter(field_name="industry_key").get()
    assert industry_observation.value_text == "creative_ai_production"
    assert industry_observation.applied is False


@pytest.mark.django_db
def test_identity_mismatch_fails_without_applying_scraped_fields(tmp_path) -> None:
    company = create_company()
    scheduled = schedule_company_enrichment(company)
    assert scheduled is not None

    with override_settings(MEDIA_ROOT=tmp_path):
        execute_company_enrichment(
            build_envelope(scheduled.outbox),
            policy=settings.RUNTIME_SETTINGS.fetch,
            fetcher=CompanyProfileFixtureFetcher(identity_mismatch=True),
        )

    company.refresh_from_db()
    run = CompanyProfileRun.objects.get(pk=scheduled.enrichment_run.pk)
    assert company.legal_name == ""
    assert run.status == CompanyEnrichmentStatus.FAILED
    assert run.error_code == "COMPANY_IDENTITY_MISMATCH"
    assert CompanyFieldObservation.objects.count() == 0
    assert TaskOutbox.objects.filter(command_type=COMPANY_PROFILE_ENRICH_COMMAND_TYPE).count() == 1


@pytest.mark.django_db
def test_company_profile_backfill_command_queues_eligible_companies(
    capsys: pytest.CaptureFixture[str],
) -> None:
    create_company()

    call_command("backfill_company_profiles", limit=20)

    assert "Eligible companies: 1; newly queued: 1" in capsys.readouterr().out
    assert CompanyProfileRun.objects.count() == 1


def test_company_profile_celery_tasks_delegate_to_services() -> None:
    identifier = uuid4()
    envelope = TaskEnvelopeV2(
        outbox_id=identifier,
        pipeline_run_id=identifier,
        command_type=COMPANY_PROFILE_ENRICH_COMMAND_TYPE,
        object_id=identifier,
        idempotency_key="companies.profile:test:execute",
        requested_by="system",
    )
    with patch("apps.companies.tasks.execute_company_enrichment") as execute:
        enrich_company_profile_task.run(envelope.model_dump(mode="json"))
    with patch(
        "apps.companies.tasks.schedule_due_company_enrichments",
        return_value=(3, 2),
    ) as schedule:
        schedule_company_profile_refresh_task.run()

    execute.assert_called_once()
    assert execute.call_args.kwargs["recover_started"] is False
    schedule.assert_called_once_with(limit=500)
