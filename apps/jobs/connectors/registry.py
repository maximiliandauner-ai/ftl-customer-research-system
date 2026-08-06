from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from typing import Any, Literal, cast
from urllib.parse import urlparse

from defusedxml import ElementTree as DefusedElementTree
from pydantic import ValidationError

from apps.jobs.connectors.text import classify_section, html_to_text, normalize_text
from apps.jobs.contracts import (
    ConnectorParseResultV1,
    ParsedLocationV1,
    ParsedPostingV1,
    ParsedSectionV1,
)
from apps.sources.models import ProviderType, SourceEndpoint

CONNECTOR_VERSIONS = {
    "personio": "1.0.0",
    "greenhouse": "1.0.0",
    "lever": "1.0.0",
    "ashby": "1.0.0",
    "json_ld": "1.0.0",
    "generic_html": "1.0.0",
}
MAX_JSON_DEPTH = 40
MAX_JSON_NODES = 100_000


class ConnectorError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


def _text(value: Any) -> str:
    return normalize_text(str(value)) if value is not None else ""


def _html_text(value: Any) -> str:
    return html_to_text(str(value)) if value is not None else ""


def _json_loads(body: bytes, encoding: str) -> Any:
    try:
        value = json.loads(body.decode(encoding or "utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConnectorError("CONNECTOR_INVALID_JSON", "The source is not valid JSON.") from exc
    node_count = 0

    def inspect(item: Any, depth: int) -> None:
        nonlocal node_count
        if depth > MAX_JSON_DEPTH:
            raise ConnectorError("CONNECTOR_JSON_TOO_DEEP", "The JSON nesting limit was exceeded.")
        node_count += 1
        if node_count > MAX_JSON_NODES:
            raise ConnectorError("CONNECTOR_JSON_TOO_LARGE", "The JSON item limit was exceeded.")
        if isinstance(item, dict):
            for key, child in item.items():
                if len(str(key)) > 500:
                    raise ConnectorError("CONNECTOR_JSON_KEY_TOO_LONG", "A JSON key is too long.")
                inspect(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                inspect(child, depth + 1)
        elif isinstance(item, str) and len(item) > 1_000_000:
            raise ConnectorError("CONNECTOR_JSON_TEXT_TOO_LONG", "A JSON field is too long.")

    inspect(value, 0)
    return value


def _location(
    display: Any,
    *,
    remote: bool = False,
    workplace: str = "unknown",
    city: Any = "",
    region: Any = "",
    country: Any = "",
    postal: Any = "",
) -> ParsedLocationV1 | None:
    label = _text(display)
    if not label and remote:
        label = "Remote"
    if not label:
        return None
    country_text = _text(country)
    if len(country_text) != 2:
        country_text = ""
    normalized_workplace: Literal["onsite", "hybrid", "remote", "unknown"] = (
        cast(Literal["onsite", "hybrid", "remote"], workplace)
        if workplace in {"onsite", "hybrid", "remote"}
        else "unknown"
    )
    return ParsedLocationV1(
        display_text=label,
        city=_text(city),
        region=_text(region),
        country=country_text,
        postal_code=_text(postal),
        remote=remote,
        workplace_type=normalized_workplace,
    )


def _section(heading: Any, value: Any) -> ParsedSectionV1 | None:
    text = _html_text(value)
    if not text:
        return None
    heading_text = _text(heading) or "Description"
    return ParsedSectionV1(
        heading=heading_text,
        text=text,
        kind=classify_section(heading_text),
    )


def _validated(
    connector_key: str,
    postings: Iterable[ParsedPostingV1],
    warnings: Iterable[str] = (),
) -> ConnectorParseResultV1:
    try:
        return ConnectorParseResultV1(
            connector_key=connector_key,  # type: ignore[arg-type]
            connector_version=CONNECTOR_VERSIONS[connector_key],
            collection_complete=connector_key in {"personio", "greenhouse", "lever", "ashby"},
            postings=tuple(postings),
            warnings=tuple(warnings),
        )
    except ValidationError as exc:
        raise ConnectorError(
            "CONNECTOR_OUTPUT_INVALID", "The connector output failed its strict schema."
        ) from exc


def _xml_child(element: Any, name: str) -> Any | None:
    for child in list(element):
        if str(child.tag).split("}")[-1] == name:
            return child
    return None


def _xml_text(element: Any, name: str) -> str:
    child = _xml_child(element, name)
    return _text(child.text if child is not None else "")


def _parse_personio(endpoint: SourceEndpoint, body: bytes, encoding: str) -> ConnectorParseResultV1:
    try:
        root = DefusedElementTree.fromstring(
            body,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except Exception as exc:
        raise ConnectorError(
            "PERSONIO_INVALID_XML", "The Personio feed is not safe valid XML."
        ) from exc
    positions = [item for item in root.iter() if str(item.tag).split("}")[-1] == "position"]
    postings: list[ParsedPostingV1] = []
    tenant = urlparse(endpoint.base_url_canonical).hostname or ""
    for position in positions:
        external_id = _xml_text(position, "id")
        title = _xml_text(position, "name")
        if not external_id or not title:
            raise ConnectorError("PERSONIO_REQUIRED_FIELD", "A Personio job lacks its ID or name.")
        sections: list[ParsedSectionV1] = []
        descriptions = _xml_child(position, "jobDescriptions")
        if descriptions is not None:
            for item in list(descriptions):
                parsed = _section(_xml_text(item, "name"), _xml_text(item, "value"))
                if parsed is not None:
                    sections.append(parsed)
        description = "\n\n".join(section.text for section in sections)
        location = _location(_xml_text(position, "office"))
        canonical_url = f"https://{tenant}/job/{external_id}"
        postings.append(
            ParsedPostingV1(
                external_id=external_id,
                title=title,
                canonical_url=canonical_url,
                apply_url=canonical_url,
                department=_xml_text(position, "department"),
                team=_xml_text(position, "recruitingCategory"),
                employment_type=_xml_text(position, "employmentType"),
                published_at=_xml_text(position, "createdAt"),
                description_text=description,
                sections=tuple(sections),
                locations=(location,) if location else (),
            )
        )
    return _validated("personio", postings)


def _parse_greenhouse(
    endpoint: SourceEndpoint, body: bytes, encoding: str
) -> ConnectorParseResultV1:
    data = _json_loads(body, encoding)
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ConnectorError("GREENHOUSE_SCHEMA", "The Greenhouse jobs collection is missing.")
    postings: list[ParsedPostingV1] = []
    for item in data["jobs"]:
        if not isinstance(item, dict):
            raise ConnectorError("GREENHOUSE_SCHEMA", "A Greenhouse job is not an object.")
        location_data: dict[str, Any] = (
            item["location"] if isinstance(item.get("location"), dict) else {}
        )
        location = _location(location_data.get("name"))
        departments: list[Any] = (
            item["departments"] if isinstance(item.get("departments"), list) else []
        )
        title = _text(item.get("title"))
        external_id = _text(item.get("id"))
        url = _text(item.get("absolute_url"))
        if not title or not external_id or not url:
            raise ConnectorError(
                "GREENHOUSE_REQUIRED_FIELD", "A Greenhouse job lacks required identity fields."
            )
        description = _html_text(item.get("content"))
        sections = (_section("Description", item.get("content")),) if description else ()
        postings.append(
            ParsedPostingV1(
                external_id=external_id,
                title=title,
                canonical_url=url,
                apply_url=url,
                department=_text(departments[0].get("name"))
                if departments and isinstance(departments[0], dict)
                else "",
                language=_text(item.get("language")),
                published_at=_text(item.get("updated_at")),
                description_text=description,
                sections=tuple(section for section in sections if section is not None),
                locations=(location,) if location else (),
            )
        )
    return _validated("greenhouse", postings)


def _parse_lever(endpoint: SourceEndpoint, body: bytes, encoding: str) -> ConnectorParseResultV1:
    data = _json_loads(body, encoding)
    if not isinstance(data, list):
        raise ConnectorError("LEVER_SCHEMA", "The Lever postings collection is missing.")
    postings: list[ParsedPostingV1] = []
    for item in data:
        if not isinstance(item, dict):
            raise ConnectorError("LEVER_SCHEMA", "A Lever posting is not an object.")
        categories: dict[str, Any] = (
            item["categories"] if isinstance(item.get("categories"), dict) else {}
        )
        external_id = _text(item.get("id"))
        title = _text(item.get("text"))
        canonical_url = _text(item.get("hostedUrl"))
        if not external_id or not title or not canonical_url:
            raise ConnectorError(
                "LEVER_REQUIRED_FIELD", "A Lever posting lacks required identity fields."
            )
        descriptions = [_text(item.get("descriptionPlain"))]
        lists: list[Any] = item["lists"] if isinstance(item.get("lists"), list) else []
        sections: list[ParsedSectionV1] = []
        for section_data in lists:
            if isinstance(section_data, dict):
                parsed = _section(section_data.get("text"), section_data.get("content"))
                if parsed is not None:
                    sections.append(parsed)
                    descriptions.append(parsed.text)
        additional = _html_text(item.get("additional"))
        if additional:
            descriptions.append(additional)
        location = _location(categories.get("location"))
        postings.append(
            ParsedPostingV1(
                external_id=external_id,
                title=title,
                canonical_url=canonical_url,
                apply_url=_text(item.get("applyUrl")),
                department=_text(categories.get("department")),
                team=_text(categories.get("team")),
                employment_type=_text(categories.get("commitment")),
                description_text="\n\n".join(value for value in descriptions if value),
                sections=tuple(sections),
                locations=(location,) if location else (),
            )
        )
    return _validated("lever", postings)


def _parse_ashby(endpoint: SourceEndpoint, body: bytes, encoding: str) -> ConnectorParseResultV1:
    data = _json_loads(body, encoding)
    if (
        not isinstance(data, dict)
        or data.get("apiVersion") != "1"
        or not isinstance(data.get("jobs"), list)
    ):
        raise ConnectorError("ASHBY_SCHEMA", "The Ashby v1 jobs collection is missing.")
    postings: list[ParsedPostingV1] = []
    for item in data["jobs"]:
        if not isinstance(item, dict):
            raise ConnectorError("ASHBY_SCHEMA", "An Ashby job is not an object.")
        canonical_url = _text(item.get("jobUrl"))
        external_id = canonical_url.rstrip("/").rsplit("/", 1)[-1] if canonical_url else ""
        title = _text(item.get("title"))
        if not external_id or not title or not canonical_url:
            raise ConnectorError(
                "ASHBY_REQUIRED_FIELD", "An Ashby job lacks required identity fields."
            )
        workplace = _text(item.get("workplaceType")).lower().replace("on-site", "onsite")
        remote = bool(item.get("isRemote")) or workplace == "remote"
        locations: list[ParsedLocationV1] = []
        primary_location = _location(item.get("location"), remote=remote, workplace=workplace)
        if primary_location:
            locations.append(primary_location)
        for other in (
            item.get("secondaryLocations", [])
            if isinstance(item.get("secondaryLocations"), list)
            else []
        ):
            if isinstance(other, dict):
                parsed = _location(other.get("location"), remote=remote, workplace=workplace)
            else:
                parsed = _location(other, remote=remote, workplace=workplace)
            if parsed:
                locations.append(parsed)
        description = _text(item.get("descriptionPlain")) or _html_text(item.get("descriptionHtml"))
        section = _section("Description", item.get("descriptionHtml") or description)
        postings.append(
            ParsedPostingV1(
                external_id=external_id,
                title=title,
                canonical_url=canonical_url,
                apply_url=_text(item.get("applyUrl")),
                department=_text(item.get("department")),
                team=_text(item.get("team")),
                employment_type=_text(item.get("employmentType")),
                published_at=_text(item.get("publishedAt")),
                is_open=bool(item.get("isListed", True)),
                description_text=description,
                sections=(section,) if section else (),
                locations=tuple(locations),
            )
        )
    return _validated("ashby", postings)


class JsonLdScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.capture = False
        self.current: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        values = {key.lower(): (value or "") for key, value in attrs}
        if values.get("type", "").lower().split(";", 1)[0].strip() == "application/ld+json":
            self.capture = True
            self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.capture:
            self.scripts.append("".join(self.current))
            self.capture = False
            self.current = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.current.append(data)


def _walk_jsonld(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _walk_jsonld(item)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        type_values = types if isinstance(types, list) else [types]
        if any(str(item).casefold() == "jobposting" for item in type_values):
            yield value
        if "@graph" in value:
            yield from _walk_jsonld(value["@graph"])


def _jsonld_location(value: Any) -> ParsedLocationV1 | None:
    if not isinstance(value, dict):
        return _location(value)
    address: dict[str, Any] = value["address"] if isinstance(value.get("address"), dict) else {}
    parts = [
        _text(address.get("addressLocality")),
        _text(address.get("addressRegion")),
        _text(address.get("addressCountry")),
    ]
    display = ", ".join(part for part in parts if part) or _text(value.get("name"))
    return _location(
        display,
        city=address.get("addressLocality"),
        region=address.get("addressRegion"),
        country=address.get("addressCountry"),
        postal=address.get("postalCode"),
    )


def _parse_json_ld(endpoint: SourceEndpoint, body: bytes, encoding: str) -> ConnectorParseResultV1:
    try:
        html = body.decode(encoding or "utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ConnectorError("JSONLD_ENCODING", "The job page encoding is invalid.") from exc
    parser = JsonLdScriptParser()
    parser.feed(html)
    jobs: list[dict[str, Any]] = []
    for script in parser.scripts:
        try:
            decoded = json.loads(script)
        except json.JSONDecodeError:
            continue
        jobs.extend(_walk_jsonld(decoded))
    postings: list[ParsedPostingV1] = []
    for item in jobs:
        identifier = item.get("identifier")
        if isinstance(identifier, dict):
            external_id = _text(identifier.get("value") or identifier.get("@id"))
        else:
            external_id = _text(identifier)
        canonical_url = _text(item.get("url")) or endpoint.base_url_canonical
        if not external_id:
            external_id = hashlib.sha256(canonical_url.encode()).hexdigest()[:32]
        title = _text(item.get("title"))
        if not title:
            raise ConnectorError("JSONLD_REQUIRED_FIELD", "A JSON-LD job lacks a title.")
        organization: dict[str, Any] = (
            item["hiringOrganization"] if isinstance(item.get("hiringOrganization"), dict) else {}
        )
        location_values = item.get("jobLocation", [])
        if not isinstance(location_values, list):
            location_values = [location_values]
        locations = [location for value in location_values if (location := _jsonld_location(value))]
        remote = _text(item.get("jobLocationType")).casefold() == "telecommute"
        if remote and not any(location.remote for location in locations):
            locations.append(
                ParsedLocationV1(display_text="Remote", remote=True, workplace_type="remote")
            )
        description = _html_text(item.get("description"))
        section = _section("Description", item.get("description"))
        employment = item.get("employmentType", "")
        if isinstance(employment, list):
            employment = ", ".join(_text(value) for value in employment)
        postings.append(
            ParsedPostingV1(
                external_id=external_id,
                title=title,
                canonical_url=canonical_url,
                apply_url=canonical_url,
                company_name=_text(organization.get("name")),
                company_url=_text(organization.get("sameAs")),
                employment_type=_text(employment),
                published_at=_text(item.get("datePosted")),
                valid_through=_text(item.get("validThrough")),
                description_text=description,
                sections=(section,) if section else (),
                locations=tuple(locations),
            )
        )
    if not postings:
        raise ConnectorError("JSONLD_NO_JOBS", "The page contains no valid JobPosting JSON-LD.")
    return _validated("json_ld", postings)


class GenericJobParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta_title = ""
        self.in_h1 = False
        self.h1_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if tag.lower() == "h1" and not self.title:
            self.in_h1 = True
        if tag.lower() == "meta" and values.get("property", "").lower() == "og:title":
            self.meta_title = _text(values.get("content"))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "h1" and self.in_h1:
            self.title = _text("".join(self.h1_parts))
            self.in_h1 = False

    def handle_data(self, data: str) -> None:
        if self.in_h1:
            self.h1_parts.append(data)


def _parse_generic(endpoint: SourceEndpoint, body: bytes, encoding: str) -> ConnectorParseResultV1:
    try:
        html = body.decode(encoding or "utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ConnectorError("GENERIC_ENCODING", "The job page encoding is invalid.") from exc
    parser = GenericJobParser()
    parser.feed(html)
    title = parser.title or parser.meta_title
    description = html_to_text(html)
    if not title or len(description) < 200:
        raise ConnectorError(
            "GENERIC_NOT_CONFIDENT", "The generic page lacks a reliable title or job description."
        )
    external_id = hashlib.sha256(endpoint.base_url_canonical.encode()).hexdigest()[:32]
    posting = ParsedPostingV1(
        external_id=external_id,
        title=title,
        canonical_url=endpoint.base_url_canonical,
        apply_url=endpoint.base_url_canonical,
        description_text=description,
        sections=(ParsedSectionV1(heading="Job page", text=description, kind="description"),),
    )
    return _validated("generic_html", (posting,), ("Parsed by conservative generic HTML rules.",))


def _detect(endpoint: SourceEndpoint, body: bytes, content_type: str) -> str:
    explicit_map: dict[str, str] = {
        ProviderType.PERSONIO: "personio",
        ProviderType.GREENHOUSE: "greenhouse",
        ProviderType.LEVER: "lever",
        ProviderType.ASHBY: "ashby",
        ProviderType.JSON_LD: "json_ld",
        ProviderType.GENERIC_WEB: "generic_html",
    }
    explicit = explicit_map.get(endpoint.provider_type)
    if explicit:
        return explicit
    host = (urlparse(endpoint.base_url_canonical).hostname or "").casefold()
    if host.endswith(".jobs.personio.de") or host == "jobs.personio.de":
        return "personio"
    if host == "boards-api.greenhouse.io":
        return "greenhouse"
    if host == "api.lever.co":
        return "lever"
    if host == "api.ashbyhq.com":
        return "ashby"
    leading = body.lstrip()[:100].lower()
    if "xml" in content_type or leading.startswith(b"<?xml"):
        return "personio"
    if "json" in content_type or leading.startswith((b"{", b"[")):
        data = _json_loads(body, "utf-8")
        if isinstance(data, dict) and data.get("apiVersion") == "1" and "jobs" in data:
            return "ashby"
        if isinstance(data, dict) and "jobs" in data:
            return "greenhouse"
        if isinstance(data, list):
            return "lever"
        raise ConnectorError(
            "CONNECTOR_JSON_UNSUPPORTED", "The JSON source is not a supported job feed."
        )
    if "html" in content_type or b"<html" in leading:
        sample = body[:1_000_000].lower()
        return "json_ld" if re.search(rb"application/ld\+json", sample) else "generic_html"
    raise ConnectorError(
        "CONNECTOR_UNSUPPORTED", "The source content has no supported job connector."
    )


def parse_source(
    endpoint: SourceEndpoint,
    body: bytes,
    *,
    content_type: str,
    encoding: str,
) -> ConnectorParseResultV1:
    connector = _detect(endpoint, body, content_type)
    parsers = {
        "personio": _parse_personio,
        "greenhouse": _parse_greenhouse,
        "lever": _parse_lever,
        "ashby": _parse_ashby,
        "json_ld": _parse_json_ld,
        "generic_html": _parse_generic,
    }
    return parsers[connector](endpoint, body, encoding)
