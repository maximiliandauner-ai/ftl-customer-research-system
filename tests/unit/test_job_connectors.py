from pathlib import Path

import pytest

from apps.jobs.connectors import ConnectorError, parse_source
from apps.sources.models import ProviderType, SourceEndpoint

FIXTURES = Path(__file__).parents[1] / "fixtures" / "connectors"


def endpoint(url: str, provider: str = ProviderType.UNKNOWN) -> SourceEndpoint:
    return SourceEndpoint(base_url_canonical=url, provider_type=provider)


@pytest.mark.parametrize(
    ("fixture", "url", "content_type", "expected_connector", "expected_title"),
    [
        (
            "personio.xml",
            "https://acme.jobs.personio.de/xml",
            "application/xml",
            "personio",
            "Senior Video Producer",
        ),
        (
            "greenhouse.json",
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true",
            "application/json",
            "greenhouse",
            "Content Marketing Lead",
        ),
        (
            "lever.json",
            "https://api.lever.co/v0/postings/acme?mode=json",
            "application/json",
            "lever",
            "Creative Operations Manager",
        ),
        (
            "ashby.json",
            "https://api.ashbyhq.com/posting-api/job-board/acme",
            "application/json",
            "ashby",
            "Director of Brand",
        ),
        (
            "json_ld.html",
            "https://acme.example/jobs/story-42",
            "text/html",
            "json_ld",
            "Head of Storytelling",
        ),
        (
            "generic.html",
            "https://acme.example/careers/motion",
            "text/html",
            "generic_html",
            "Senior Motion Designer",
        ),
    ],
)
def test_connector_fixture_normalizes_to_one_strict_posting(
    fixture: str,
    url: str,
    content_type: str,
    expected_connector: str,
    expected_title: str,
) -> None:
    result = parse_source(
        endpoint(url),
        (FIXTURES / fixture).read_bytes(),
        content_type=content_type,
        encoding="utf-8",
    )

    assert result.connector_key == expected_connector
    assert result.connector_version == "1.0.0"
    assert len(result.postings) == 1
    assert result.postings[0].title == expected_title
    assert result.postings[0].external_id
    assert result.postings[0].canonical_url.startswith("https://")


def test_untrusted_html_is_plaintext_and_scripts_are_dropped() -> None:
    greenhouse = parse_source(
        endpoint("https://boards-api.greenhouse.io/v1/boards/acme/jobs"),
        (FIXTURES / "greenhouse.json").read_bytes(),
        content_type="application/json",
        encoding="utf-8",
    ).postings[0]
    json_ld = parse_source(
        endpoint("https://acme.example/jobs/story-42"),
        (FIXTURES / "json_ld.html").read_bytes(),
        content_type="text/html",
        encoding="utf-8",
    ).postings[0]
    generic = parse_source(
        endpoint("https://acme.example/careers/motion"),
        (FIXTURES / "generic.html").read_bytes(),
        content_type="text/html",
        encoding="utf-8",
    ).postings[0]

    assert "alert" not in greenhouse.description_text
    assert "<" not in greenhouse.description_text
    assert "steal" not in json_ld.description_text
    assert "trackingMarker" not in generic.description_text


def test_personio_single_job_html_uses_embedded_json_ld_instead_of_xml_feed() -> None:
    result = parse_source(
        endpoint("https://acme.jobs.personio.de/job/42?language=de"),
        (FIXTURES / "json_ld.html").read_bytes(),
        content_type="text/html; charset=utf-8",
        encoding="utf-8",
    )

    assert result.connector_key == "json_ld"
    assert result.postings[0].title == "Head of Storytelling"


def test_personio_rejects_dtd_and_entities() -> None:
    hostile = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><workzag-jobs><position><id>1</id><name>&xxe;</name></position></workzag-jobs>'

    with pytest.raises(ConnectorError, match="safe valid XML") as error:
        parse_source(
            endpoint("https://acme.jobs.personio.de/xml"),
            hostile,
            content_type="application/xml",
            encoding="utf-8",
        )

    assert error.value.code == "PERSONIO_INVALID_XML"


def test_known_provider_schema_failure_does_not_fall_back_to_generic() -> None:
    with pytest.raises(ConnectorError) as error:
        parse_source(
            endpoint(
                "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
                ProviderType.GREENHOUSE,
            ),
            b"<html><h1>Looks like a job but is an error page</h1></html>",
            content_type="text/html",
            encoding="utf-8",
        )

    assert error.value.code == "CONNECTOR_INVALID_JSON"
