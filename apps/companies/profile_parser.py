from __future__ import annotations

import json
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from apps.companies.contracts import ParsedCompanyFieldV1, ParsedCompanyPageV1
from apps.jobs.connectors.text import normalize_text
from apps.sources.policy import registrable_domain

MAX_JSON_LD_CHARS = 1_000_000
MAX_JSON_NODES = 100_000
PROFILE_PATH_TERMS = (
    "about",
    "agentur",
    "company",
    "imprint",
    "impressum",
    "legal-notice",
    "studio",
    "team",
    "ueber",
    "uber-uns",
    "unternehmen",
    "%c3%bcber",
)
LEGAL_NAME_PATTERN = re.compile(
    r"(?im)^(?P<name>[^\n<>]{2,180}\b(?:gmbh(?:\s*&\s*co\.?\s*kg)?|"
    r"ug\s*\(haftungsbeschr(?:ä|ae)nkt\)|ag|se|kg|ohg|e\.?v\.?|"
    r"limited|ltd\.?|llc|inc\.?|corp(?:oration)?|s\.?a\.?|s\.?r\.?l\.?))\s*$"
)
POSTAL_CITY_PATTERN = re.compile(
    r"(?im)^\s*(?:[A-Z]{1,3}-)?(?P<postal>\d{4,6})\s+(?P<city>[A-ZÄÖÜ][\wÄÖÜäöüß.' -]{1,80})\s*$"
)
REGISTER_CITY_PATTERN = re.compile(
    r"(?im)^\s*(?:sitz|registered\s+office|headquarters|hauptsitz)\s*:\s*"
    r"(?P<city>[^\n:]{2,80})\s*$"
)
INDUSTRY_RULES = (
    (
        "creative_ai_production",
        ("ai video", "ki-video", "kampagnenvideo", "tv-commercial", "ai studio"),
    ),
    ("marketing_and_advertising", ("marketing agency", "marketingagentur", "werbeagentur")),
    ("education_and_learning", ("e-learning", "digital learning", "weiterbildung")),
    ("legal_services", ("law firm", "rechtsanw", "patentanw")),
    ("recruiting_software", ("applicant tracking", "recruiting platform", "recruitment software")),
    ("web_hosting_and_cloud", ("web hosting", "cloud hosting", "hosting provider")),
    ("software", ("software-as-a-service", "saas platform", "softwareunternehmen")),
    ("recruitment", ("recruitment agency", "personalvermittlung", "staffing")),
)


class ProfileHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._drop_depth = 0
        self._json_ld = False
        self._json_parts: list[str] = []
        self.json_scripts: list[str] = []
        self.visible_parts: list[str] = []
        self.links: list[str] = []
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        values = {key.casefold(): value or "" for key, value in attrs}
        if lowered == "script":
            self._drop_depth += 1
            if values.get("type", "").casefold().split(";", 1)[0].strip() == (
                "application/ld+json"
            ):
                self._json_ld = True
                self._json_parts = []
            return
        if lowered in {"style", "svg", "noscript", "iframe", "canvas"}:
            self._drop_depth += 1
            return
        if self._drop_depth:
            return
        if lowered in {
            "address",
            "article",
            "br",
            "dd",
            "div",
            "dt",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "main",
            "p",
            "section",
            "td",
            "th",
            "tr",
        }:
            self.visible_parts.append("\n")
        if lowered == "a" and values.get("href"):
            self.links.append(values["href"])
        if lowered == "meta" and values.get("content"):
            key = values.get("property") or values.get("name")
            if key:
                self.meta[key.casefold()] = normalize_text(values["content"])

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered == "script":
            if self._json_ld:
                value = "".join(self._json_parts)
                if len(value) <= MAX_JSON_LD_CHARS:
                    self.json_scripts.append(value)
                self._json_ld = False
                self._json_parts = []
            if self._drop_depth:
                self._drop_depth -= 1
            return
        if lowered in {"style", "svg", "noscript", "iframe", "canvas"}:
            if self._drop_depth:
                self._drop_depth -= 1
            return
        if not self._drop_depth and lowered in {
            "address",
            "article",
            "div",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "main",
            "p",
            "section",
        }:
            self.visible_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._json_ld:
            self._json_parts.append(data)
        elif not self._drop_depth:
            self.visible_parts.append(data)


def _json_objects(value: Any) -> Iterable[dict[str, Any]]:
    stack: list[tuple[Any, int]] = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > MAX_JSON_NODES or depth > 40:
            return
        if isinstance(item, dict):
            yield item
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)


def _types(item: dict[str, Any]) -> set[str]:
    value = item.get("@type", ())
    values = value if isinstance(value, list) else [value]
    return {str(entry).casefold() for entry in values}


def _clean(value: Any, *, limit: int = 500) -> str:
    return normalize_text(str(value))[:limit] if value is not None else ""


def _field(
    name: str,
    value: str,
    evidence: str,
    method: str,
    confidence: float,
) -> ParsedCompanyFieldV1 | None:
    clean_value = _clean(value)
    clean_evidence = _clean(evidence, limit=1_000)
    if not clean_value or not clean_evidence:
        return None
    return ParsedCompanyFieldV1(
        field_name=name,  # type: ignore[arg-type]
        value=clean_value,
        evidence_excerpt=clean_evidence,
        extraction_method=method,
        confidence=confidence,
    )


def _country_code(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name") or value.get("@id") or ""
    normalized = _clean(value).casefold()
    mapping = {
        "at": "AT",
        "austria": "AT",
        "österreich": "AT",
        "de": "DE",
        "deutschland": "DE",
        "germany": "DE",
        "ch": "CH",
        "schweiz": "CH",
        "switzerland": "CH",
        "gb": "GB",
        "united kingdom": "GB",
        "uk": "GB",
        "us": "US",
        "usa": "US",
        "united states": "US",
    }
    return mapping.get(normalized, normalized.upper() if len(normalized) == 2 else "")


def _employee_range(minimum: int, maximum: int) -> str:
    upper = max(minimum, maximum)
    if upper <= 10:
        return "1_10"
    if upper <= 50:
        return "11_50"
    if upper <= 200:
        return "51_200"
    if upper <= 1_000:
        return "201_1000"
    return "1001_plus"


def _valid_legal_name(value: str) -> bool:
    clean = _clean(value, limit=181)
    if not clean or len(clean) > 180 or not LEGAL_NAME_PATTERN.fullmatch(clean):
        return False
    if re.search(r"(?i)(?:©|\(c\)|\bcopyright\b|\ball rights reserved\b)", clean):
        return False
    return not re.match(r"^\d{4}\s+", clean)


def _valid_city(value: str) -> bool:
    clean = _clean(value, limit=81).strip(".,")
    if not 2 <= len(clean) <= 80 or len(clean.split()) > 5:
        return False
    if re.search(r"(?:\d|https?://|www\.|\.com\b|[!?;:])", clean, re.IGNORECASE):
        return False
    if re.search(
        r"(?i)\b(?:we|our|launched|built|founded|company|brand|platform|product|team|first-class)\b",
        clean,
    ):
        return False
    return bool(re.fullmatch(r"[A-ZÄÖÜ][\wÄÖÜäöüß.' -]{1,79}", clean))


def _industry_key(value: str) -> tuple[str, str] | None:
    lowered = value.casefold()
    for industry, terms in INDUSTRY_RULES:
        if matched := next((term for term in terms if term in lowered), None):
            return industry, matched
    return None


def _self_described_agency_line(lines: list[str]) -> str:
    for line in lines:
        if not 10 <= len(line) <= 300:
            continue
        match = re.search(r"(?i)\b(?:we\s+(?:are|'re)|wir\s+sind)\b", line)
        if match is None:
            continue
        self_description = re.split(r"[,;.!?]", line[match.start() :], maxsplit=1)[0][:120]
        if re.search(
            r"(?i)\b(?:agency|agentur|(?:ai|creative|digital|production)\s+studio)\b",
            self_description,
        ):
            return line
    return ""


def _structured_fields(item: dict[str, Any]) -> tuple[list[str], list[ParsedCompanyFieldV1]]:
    item_types = _types(item)
    if not item_types.intersection(
        {
            "advertisingagency",
            "corporation",
            "educationalorganization",
            "employmentagency",
            "governmentorganization",
            "localbusiness",
            "ngo",
            "organization",
            "professionalservice",
        }
    ):
        return [], []
    evidence = json.dumps(item, ensure_ascii=False, sort_keys=True)[:1_000]
    identity_names = [
        name
        for raw in (item.get("legalName"), item.get("name"), item.get("alternateName"))
        if (name := _clean(raw))
    ]
    fields: list[ParsedCompanyFieldV1] = []
    legal_name = _clean(item.get("legalName"))
    alternate_name = _clean(item.get("alternateName"))
    if not _valid_legal_name(legal_name):
        legal_name = ""
    if not legal_name and _valid_legal_name(alternate_name):
        legal_name = alternate_name
    if legal_name and (parsed := _field("legal_name", legal_name, evidence, "json_ld", 0.96)):
        fields.append(parsed)
    if "governmentorganization" in item_types:
        company_type = "public_body"
    elif "ngo" in item_types:
        company_type = "nonprofit"
    elif "advertisingagency" in item_types:
        company_type = "agency"
    elif "employmentagency" in item_types:
        company_type = "recruiter"
    else:
        company_type = "company"
    if parsed := _field("company_type", company_type, evidence, "json_ld_type", 0.84):
        fields.append(parsed)
    industry = item.get("industry")
    if isinstance(industry, list):
        industry = industry[0] if industry else ""
    if industry and (mapped_industry := _industry_key(_clean(industry))):
        industry_key, _matched_term = mapped_industry
        if parsed := _field("industry_key", industry_key, evidence, "json_ld", 0.94):
            fields.append(parsed)
    description = _clean(item.get("description"))
    if len(description) >= 40 and (
        parsed := _field("description", description, evidence, "json_ld", 0.93)
    ):
        fields.append(parsed)
    address = item.get("address")
    if isinstance(address, dict):
        city = _clean(address.get("addressLocality"))
        country = _country_code(address.get("addressCountry"))
        if _valid_city(city) and (
            parsed := _field("headquarters_city", city, evidence, "json_ld", 0.90)
        ):
            fields.append(parsed)
        if country and (
            parsed := _field("headquarters_country", country, evidence, "json_ld", 0.90)
        ):
            fields.append(parsed)
    employees = item.get("numberOfEmployees")
    if isinstance(employees, dict):
        try:
            minimum = int(employees.get("minValue") or employees.get("value") or 0)
            maximum = int(employees.get("maxValue") or employees.get("value") or minimum)
        except (TypeError, ValueError):
            pass
        else:
            if maximum > 0 and (
                parsed := _field(
                    "employee_range",
                    _employee_range(minimum, maximum),
                    evidence,
                    "json_ld",
                    0.94,
                )
            ):
                fields.append(parsed)
    return identity_names, fields


def _page_links(base_url: str, values: list[str]) -> tuple[str, ...]:
    base_host = (urlsplit(base_url).hostname or "").casefold()
    base_domain = registrable_domain(base_host)
    ranked: list[tuple[int, str]] = []
    for value in values:
        absolute = urljoin(base_url, value)
        parsed = urlsplit(absolute)
        if parsed.scheme != "https" or registrable_domain((parsed.hostname or "").casefold()) != (
            base_domain
        ):
            continue
        path = parsed.path.casefold()
        matches = [term for term in PROFILE_PATH_TERMS if term in path]
        if not matches:
            continue
        priority = 0 if any(term in path for term in ("impressum", "imprint", "legal")) else 1
        clean = parsed._replace(fragment="").geturl()
        ranked.append((priority, clean))
    return tuple(url for _priority, url in sorted(set(ranked))[:20])


def _visible_fields(text: str, lines: list[str]) -> tuple[list[str], list[ParsedCompanyFieldV1]]:
    fields: list[ParsedCompanyFieldV1] = []
    identity_names: list[str] = []
    legal_match = LEGAL_NAME_PATTERN.search(text)
    if legal_match and _valid_legal_name(legal_match.group("name")):
        legal_name = _clean(legal_match.group("name"))
        identity_names.append(legal_name)
        if parsed := _field("legal_name", legal_name, legal_name, "official_legal_text", 0.99):
            fields.append(parsed)
        if parsed := _field("company_type", "company", legal_name, "legal_form", 0.86):
            fields.append(parsed)
    city_match = REGISTER_CITY_PATTERN.search(text)
    postal_match = POSTAL_CITY_PATTERN.search(text)
    if city_match or postal_match:
        selected = city_match or postal_match
        assert selected is not None
        city = _clean(selected.group("city")).rstrip(".,")
        excerpt_start = max(0, selected.start() - 80)
        excerpt = text[excerpt_start : selected.end() + 120]
        if _valid_city(city):
            if parsed := _field("headquarters_city", city, excerpt, "official_address", 0.96):
                fields.append(parsed)
            german_legal = bool(
                re.search(r"(?i)\b(amtsgericht|handelsregister|ust\.?-?id|hrb)\b", text)
            )
            if german_legal and (
                parsed := _field("headquarters_country", "DE", excerpt, "official_register", 0.96)
            ):
                fields.append(parsed)
    employee_pattern = re.compile(
        r"(?i)\b(?P<min>\d{1,6})\s*(?:-|\u2013|bis|to)\s*(?P<max>\d{1,6})\s*"
        r"(?:beschäftigte|employees|mitarbeiter(?:innen)?|people|team\s+members)\b"
    )
    if match := employee_pattern.search(text):
        value = _employee_range(int(match.group("min")), int(match.group("max")))
        if parsed := _field(
            "employee_range", value, match.group(0), "explicit_employee_count", 0.94
        ):
            fields.append(parsed)
    if mapped_industry := _industry_key(text):
        industry, matched = mapped_industry
        evidence_line = next((line for line in lines if matched in line.casefold()), "")
        if evidence_line and (
            parsed := _field(
                "industry_key",
                industry,
                evidence_line[:1_000],
                "official_site_keywords",
                0.78,
            )
        ):
            fields.append(parsed)
    if (evidence_line := _self_described_agency_line(lines)) and (
        parsed := _field("company_type", "agency", evidence_line, "official_site_type", 0.90)
    ):
        fields.append(parsed)
    description_line = next(
        (
            line
            for line in lines
            if 60 <= len(line) <= 500
            and re.search(r"(?i)^(?:we are|we're|wir sind|our company|unser unternehmen)\b", line)
            and not re.search(r"(?i)\b(cookie|privacy|datenschutz|bewerb|apply)\b", line)
        ),
        "",
    )
    if description_line and (
        parsed := _field(
            "description",
            description_line,
            description_line,
            "official_about_text",
            0.86,
        )
    ):
        fields.append(parsed)
    return identity_names, fields


def parse_company_profile_page(*, page_url: str, body: bytes, encoding: str) -> ParsedCompanyPageV1:
    try:
        html = body.decode(encoding or "utf-8", errors="strict")
    except (LookupError, UnicodeDecodeError) as exc:
        raise ValueError("The company profile page encoding is invalid.") from exc
    parser = ProfileHtmlParser()
    parser.feed(html)
    parser.close()
    text = normalize_text("".join(parser.visible_parts))
    lines = [line for line in text.splitlines() if line]
    identity_names: list[str] = []
    fields: list[ParsedCompanyFieldV1] = []
    warnings: list[str] = []
    for script in parser.json_scripts:
        try:
            decoded = json.loads(script)
        except json.JSONDecodeError:
            warnings.append("An invalid JSON-LD block was ignored.")
            continue
        for item in _json_objects(decoded):
            names, structured = _structured_fields(item)
            identity_names.extend(names)
            fields.extend(structured)
    visible_names, visible = _visible_fields(text, lines)
    identity_names.extend(visible_names)
    fields.extend(visible)
    site_name = parser.meta.get("og:site_name", "")
    if site_name:
        identity_names.append(site_name)
    meta_description = parser.meta.get("og:description") or parser.meta.get("description", "")
    if (
        60 <= len(meta_description) <= 500
        and not re.search(
            r"(?i)(?:\[…\]|\[&hellip;\]|cookie|privacy|datenschutz)", meta_description
        )
        and not any(field.field_name == "description" for field in fields)
        and (
            parsed := _field(
                "description",
                meta_description,
                meta_description,
                "meta_description",
                0.72,
            )
        )
    ):
        fields.append(parsed)
    return ParsedCompanyPageV1(
        identity_names=tuple(dict.fromkeys(identity_names))[:30],
        fields=tuple(fields)[:50],
        discovered_urls=_page_links(page_url, parser.links)[:50],
        warnings=tuple(dict.fromkeys(warnings))[:30],
    )
