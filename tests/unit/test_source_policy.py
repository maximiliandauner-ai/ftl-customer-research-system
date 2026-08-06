import pytest
from django.conf import settings

from apps.sources.policy import (
    SourcePolicyError,
    canonicalize_url,
    normalize_hostname,
    redact_url,
    registrable_domain,
    validate_target,
)


def public_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def test_canonicalization_preserves_functional_query_and_removes_tracking() -> None:
    canonical = canonicalize_url(
        "HTTPS://Example.COM?b=2&utm_source=test&a=1#fragment",
        settings.RUNTIME_SETTINGS.fetch,
    )

    assert canonical.canonical == "https://example.com/?b=2&a=1"
    assert canonical.hostname_ascii == "example.com"
    assert len(canonical.sha256) == 64


def test_idna_and_registrable_domain_are_deterministic_offline() -> None:
    ascii_host, unicode_host = normalize_hostname("Bücher.Example")

    assert ascii_host == "xn--bcher-kva.example"
    assert unicode_host == "bücher.example"
    assert registrable_domain("careers.example.co.uk") == "example.co.uk"


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://example.com/", "URL_SCHEME_BLOCKED"),
        ("https://alice:opaque@example.com/", "URL_USERINFO_BLOCKED"),  # pragma: allowlist secret
        ("https://example.com:8443/", "URL_PORT_BLOCKED"),
        ("https://localhost/", "URL_HOST_BLOCKED"),
        ("https://metadata.google.internal/", "URL_HOST_BLOCKED"),
    ],
)
def test_url_syntax_policy_rejects_unsafe_targets(url: str, code: str) -> None:
    with pytest.raises(SourcePolicyError) as error:
        canonicalize_url(url, settings.RUNTIME_SETTINGS.fetch)

    assert error.value.code == code


@pytest.mark.parametrize(
    ("url", "resolved"),
    [
        ("https://127.0.0.1/", ("127.0.0.1",)),
        ("https://[::1]/", ("::1",)),
        ("https://decimal-ip.example/", ("2130706433",)),
        ("https://octal-ip.example/", ("0177.0.0.1",)),
        ("https://hex-ip.example/", ("0x7f000001",)),
        ("https://cgnat.example/", ("100.64.0.1",)),
        ("https://metadata.example/", ("169.254.169.254",)),
        ("https://multicast.example/", ("224.0.0.1",)),
        ("https://reserved.example/", ("192.0.2.1",)),
    ],
)
def test_all_non_public_address_forms_are_rejected(
    url: str,
    resolved: tuple[str, ...],
) -> None:
    def resolver(_hostname: str, _port: int) -> tuple[str, ...]:
        return resolved

    with pytest.raises(SourcePolicyError) as error:
        validate_target(url, settings.RUNTIME_SETTINGS.fetch, resolver=resolver)

    assert error.value.code in {
        "NETWORK_TARGET_BLOCKED",
        "DNS_ADDRESS_INVALID",
        "URL_HOST_BLOCKED",
    }


def test_mixed_public_and_private_dns_answers_fail_closed() -> None:
    def mixed_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
        return ("93.184.216.34", "10.0.0.4")

    with pytest.raises(SourcePolicyError) as error:
        validate_target(
            "https://example.com/",
            settings.RUNTIME_SETTINGS.fetch,
            resolver=mixed_resolver,
        )

    assert error.value.code == "NETWORK_TARGET_BLOCKED"


def test_custom_deny_cidr_is_enforced_even_for_global_address() -> None:
    policy = settings.RUNTIME_SETTINGS.fetch.model_copy(
        update={"denied_cidrs": ("93.184.216.0/24",)}
    )

    with pytest.raises(SourcePolicyError) as error:
        validate_target("https://example.com/", policy, resolver=public_resolver)

    assert error.value.code == "NETWORK_TARGET_BLOCKED"


def test_valid_target_deduplicates_addresses_and_redacts_secrets() -> None:
    target = validate_target(
        "https://example.com/jobs?signature=private&role=ai",
        settings.RUNTIME_SETTINGS.fetch,
        resolver=lambda _host, _port: ("93.184.216.34", "93.184.216.34"),
    )

    assert target.addresses == ("93.184.216.34",)
    assert target.url.canonical.endswith("?signature=private&role=ai")
    redacted = redact_url(target.url.canonical)
    assert "private" not in redacted
    assert "%5Bredacted%5D" in redacted
