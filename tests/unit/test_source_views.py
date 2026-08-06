import re

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client

from apps.accounts.models import TeamRoleName
from apps.accounts.services import assign_team_role
from apps.companies.models import Company, CompanyStatus
from apps.sources.models import CandidateStatus, SourceCandidate


def role_user(username: str, role: TeamRoleName) -> User:
    call_command("bootstrap_ftl_platform", verbosity=0)
    user = User.objects.create_user(username=username, password="test-password-123")
    assign_team_role(user=user, role=role, actor=None, reason="test_fixture")
    return user


@pytest.mark.django_db
def test_source_and_company_pages_require_authentication() -> None:
    client = Client()

    assert client.get("/sources/").status_code == 302
    assert client.get("/sources/submit/").status_code == 302
    assert client.get("/companies/").status_code == 302


@pytest.mark.django_db
def test_viewer_can_inspect_sources_and_companies_but_cannot_submit() -> None:
    user = role_user("source-viewer", TeamRoleName.VIEWER)
    company = Company.objects.create(
        name="Visible Company",
        normalized_name="visible company",
        status=CompanyStatus.PROVISIONAL,
    )
    client = Client()
    client.force_login(user)

    sources = client.get("/sources/")
    companies = client.get("/companies/")
    detail = client.get(f"/companies/{company.pk}/")
    forbidden = client.get("/sources/submit/")

    assert sources.status_code == 200
    assert b"Public-source ingestion" in sources.content
    assert companies.status_code == 200
    assert b"Visible Company" in companies.content
    assert detail.status_code == 200
    assert forbidden.status_code == 403


@pytest.mark.django_db
def test_researcher_submission_requires_csrf_and_public_confirmation() -> None:
    user = role_user("source-researcher", TeamRoleName.RESEARCHER)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)

    page = client.get("/sources/submit/")
    token = page.cookies["csrftoken"].value
    idempotency_match = re.search(
        rb'name="idempotency_key" value="([^"]+)"',
        page.content,
    )
    assert idempotency_match is not None
    submission = {
        "requested_url": "https://127.0.0.1/admin",
        "company_name": "Unsafe Example",
        "company_domain": "unsafe.example",
        "idempotency_key": idempotency_match.group(1).decode(),
        "public_source_confirmed": "on",
    }

    assert client.post("/sources/submit/", submission).status_code == 403

    missing_confirmation = submission | {"csrfmiddlewaretoken": token}
    missing_confirmation.pop("public_source_confirmed")
    invalid = client.post("/sources/submit/", missing_confirmation)
    assert invalid.status_code == 400
    assert SourceCandidate.objects.count() == 0

    accepted_form = submission | {"csrfmiddlewaretoken": token}
    response = client.post("/sources/submit/", accepted_form)
    assert response.status_code == 302
    candidate = SourceCandidate.objects.get()
    assert candidate.status == CandidateStatus.UNSAFE
    detail = client.get(response.headers["Location"])
    assert detail.status_code == 200
    assert b"No network command was created" in detail.content


@pytest.mark.django_db
def test_reviewer_cannot_post_source_even_with_a_valid_csrf_session() -> None:
    user = role_user("source-reviewer", TeamRoleName.REVIEWER)
    client = Client()
    client.force_login(user)

    response = client.post(
        "/sources/submit/",
        {
            "requested_url": "https://example.com/jobs",
            "idempotency_key": "sources.manual:reviewer",
            "public_source_confirmed": "on",
        },
    )

    assert response.status_code == 403
    assert SourceCandidate.objects.count() == 0
