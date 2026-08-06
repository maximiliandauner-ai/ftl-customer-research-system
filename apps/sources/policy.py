from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import tldextract

from config.runtime import FetchPolicySettings

TRACKING_QUERY_NAMES = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
}
SENSITIVE_QUERY_MARKERS = ("token", "secret", "password", "signature", "api_key", "apikey")
LOCAL_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".home", ".lan")
HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_offline_extract = tldextract.TLDExtract(
    suffix_list_urls=(),
    include_psl_private_domains=True,
)


class SourcePolicyError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True)
class CanonicalURL:
    original_redacted: str
    canonical: str
    sha256: str
    hostname_ascii: str
    hostname_unicode: str
    port: int
    scheme: str


@dataclass(frozen=True)
class ValidatedTarget:
    url: CanonicalURL
    addresses: tuple[str, ...]


Resolver = Callable[[str, int], Sequence[str]]


def normalize_company_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def normalize_hostname(value: str) -> tuple[str, str]:
    candidate = value.strip().rstrip(".")
    if "://" in candidate:
        split = urlsplit(candidate)
        candidate = split.hostname or ""
    candidate = candidate.strip("[]").rstrip(".")
    if not candidate:
        raise SourcePolicyError("URL_HOST_MISSING", "A valid public hostname is required.")
    try:
        ip = ipaddress.ip_address(candidate)
    except ValueError:
        try:
            hostname_ascii = candidate.encode("idna").decode("ascii").lower()
        except UnicodeError as exc:
            raise SourcePolicyError(
                "URL_HOST_INVALID",
                "The hostname could not be normalized safely.",
            ) from exc
        if len(hostname_ascii) > 253 or any(
            not HOST_LABEL_RE.fullmatch(label) for label in hostname_ascii.split(".")
        ):
            raise SourcePolicyError("URL_HOST_INVALID", "The hostname is malformed.") from None
        return hostname_ascii, candidate.lower()
    return ip.compressed, ip.compressed


def registrable_domain(hostname_ascii: str) -> str:
    try:
        return ipaddress.ip_address(hostname_ascii).compressed
    except ValueError:
        extracted = _offline_extract(hostname_ascii)
        return extracted.top_domain_under_public_suffix or hostname_ascii


def _redact_query(query: str) -> str:
    redacted: list[tuple[str, str]] = []
    for name, value in parse_qsl(query, keep_blank_values=True):
        if any(marker in name.casefold() for marker in SENSITIVE_QUERY_MARKERS):
            redacted.append((name, "[redacted]"))
        else:
            redacted.append((name, value))
    return urlencode(redacted, doseq=True)


def redact_url(value: str) -> str:
    try:
        split = urlsplit(value.strip())
        hostname = split.hostname
        if not split.scheme or not hostname:
            return "[invalid-url]"
        host_ascii, _host_unicode = normalize_hostname(hostname)
        port = split.port
        default_port = 443 if split.scheme.casefold() == "https" else 80
        host_display = f"[{host_ascii}]" if ":" in host_ascii else host_ascii
        netloc = host_display if port in (None, default_port) else f"{host_display}:{port}"
        return urlunsplit(
            (
                split.scheme.casefold(),
                netloc,
                split.path or "/",
                _redact_query(split.query),
                "",
            )
        )
    except (SourcePolicyError, ValueError):
        return "[invalid-url]"


def canonicalize_url(value: str, policy: FetchPolicySettings) -> CanonicalURL:
    if len(value) > 4096:
        raise SourcePolicyError("URL_TOO_LONG", "The URL exceeds the 4,096 character limit.")
    try:
        split = urlsplit(value.strip())
        port = split.port
    except ValueError as exc:
        raise SourcePolicyError("URL_INVALID", "The URL is malformed.") from exc
    scheme = split.scheme.casefold()
    allowed_schemes = {"https", "http"} if policy.allow_http else {"https"}
    if scheme not in allowed_schemes:
        raise SourcePolicyError(
            "URL_SCHEME_BLOCKED",
            "Only public HTTPS URLs are allowed by the active source policy.",
        )
    if split.username is not None or split.password is not None:
        raise SourcePolicyError(
            "URL_USERINFO_BLOCKED", "URLs containing credentials are prohibited."
        )
    if not split.hostname:
        raise SourcePolicyError("URL_HOST_MISSING", "The URL must include a public hostname.")
    hostname_ascii, hostname_unicode = normalize_hostname(split.hostname)
    expected_port = 443 if scheme == "https" else 80
    if port not in (None, expected_port):
        raise SourcePolicyError("URL_PORT_BLOCKED", "The URL uses a prohibited network port.")
    lowered_denied = {host.casefold().rstrip(".") for host in policy.denied_hostnames}
    if (
        hostname_ascii in lowered_denied
        or hostname_ascii.endswith(LOCAL_HOST_SUFFIXES)
        or hostname_ascii.startswith("metadata.")
    ):
        raise SourcePolicyError("URL_HOST_BLOCKED", "The hostname is blocked by source policy.")
    host_display = f"[{hostname_ascii}]" if ":" in hostname_ascii else hostname_ascii
    query_items = [
        (name, item)
        for name, item in parse_qsl(split.query, keep_blank_values=True)
        if not name.casefold().startswith("utm_") and name.casefold() not in TRACKING_QUERY_NAMES
    ]
    canonical = urlunsplit(
        (
            scheme,
            host_display,
            split.path or "/",
            urlencode(query_items, doseq=True),
            "",
        )
    )
    return CanonicalURL(
        original_redacted=redact_url(value),
        canonical=canonical,
        sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        hostname_ascii=hostname_ascii,
        hostname_unicode=hostname_unicode,
        port=expected_port,
        scheme=scheme,
    )


def system_resolver(hostname: str, port: int) -> tuple[str, ...]:
    try:
        answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SourcePolicyError(
            "DNS_RESOLUTION_FAILED",
            "The hostname could not be resolved by the controlled resolver.",
        ) from exc
    return tuple(str(answer[4][0]) for answer in answers)


def _denied_networks(
    values: Iterable[str],
) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for value in values:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError as exc:
            raise SourcePolicyError(
                "FETCH_POLICY_INVALID",
                "A configured source-policy network is invalid.",
            ) from exc
    return tuple(networks)


def validate_target(
    value: str,
    policy: FetchPolicySettings,
    *,
    resolver: Resolver = system_resolver,
) -> ValidatedTarget:
    canonical = canonicalize_url(value, policy)
    try:
        literal_ip = ipaddress.ip_address(canonical.hostname_ascii)
    except ValueError:
        resolved = resolver(canonical.hostname_ascii, canonical.port)
    else:
        resolved = (literal_ip.compressed,)
    if not resolved:
        raise SourcePolicyError("DNS_EMPTY", "The hostname did not resolve to an address.")
    denied_networks = _denied_networks(policy.denied_cidrs)
    addresses: set[str] = set()
    for raw_address in resolved:
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise SourcePolicyError(
                "DNS_ADDRESS_INVALID",
                "The resolver returned an invalid address.",
            ) from exc
        prohibited_address = (
            not address.is_global
            or address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )
        if prohibited_address or any(address in network for network in denied_networks):
            raise SourcePolicyError(
                "NETWORK_TARGET_BLOCKED",
                "The target resolves to a prohibited network address.",
            )
        addresses.add(address.compressed)
    return ValidatedTarget(url=canonical, addresses=tuple(sorted(addresses)))
