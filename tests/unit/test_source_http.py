from collections.abc import Iterable

import httpcore
import httpx
import pytest
from django.conf import settings

from apps.sources import http as source_http
from apps.sources.http import PinnedNetworkBackend, SafeFetchError, SafeHttpFetcher


def public_resolver(_hostname: str, _port: int) -> tuple[str, ...]:
    return ("93.184.216.34",)


def install_mock_transport(monkeypatch: pytest.MonkeyPatch, handler: object) -> None:
    monkeypatch.setattr(
        source_http,
        "PinnedHTTPTransport",
        lambda _target: httpx.MockTransport(handler),
    )


def test_safe_fetch_streams_allowed_content_and_filters_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept-encoding"] == "identity"
        assert "ftl" in request.headers["user-agent"].casefold()
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/html; charset=UTF-8",
                "ETag": '"version-1"',
                "Set-Cookie": "secret=cookie",
            },
            content=b"<html>Public jobs</html>",
        )

    install_mock_transport(monkeypatch, handler)

    result = SafeHttpFetcher(
        settings.RUNTIME_SETTINGS.fetch,
        resolver=public_resolver,
    ).fetch("https://example.com/jobs")

    assert result.status_code == 200
    assert result.body == b"<html>Public jobs</html>"
    assert result.content_type == "text/html"
    assert result.encoding == "utf-8"
    assert result.headers_filtered == {
        "content-type": "text/html; charset=UTF-8",
        "etag": '"version-1"',
        "content-length": "24",
    }
    assert len(result.body_sha256) == 64


def test_safe_fetch_revalidates_redirect_and_blocks_private_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"Location": "https://127.0.0.1/admin"})

    install_mock_transport(monkeypatch, handler)

    with pytest.raises(SafeFetchError) as error:
        SafeHttpFetcher(
            settings.RUNTIME_SETTINGS.fetch,
            resolver=public_resolver,
        ).fetch("https://example.com/jobs")

    assert error.value.code == "NETWORK_TARGET_BLOCKED"
    assert calls == 1
    assert error.value.redirect_chain == [
        {
            "from": "https://example.com/jobs",
            "to": "https://127.0.0.1/admin",
            "status_code": 302,
        }
    ]


def test_safe_fetch_follows_public_redirect_and_keeps_conditional_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(
            (
                str(request.url),
                request.headers.get("if-none-match", ""),
                request.headers.get("if-modified-since", ""),
            )
        )
        if request.url.path == "/old":
            return httpx.Response(301, headers={"Location": "/jobs"})
        return httpx.Response(304, headers={"ETag": '"version-2"'})

    install_mock_transport(monkeypatch, handler)

    result = SafeHttpFetcher(
        settings.RUNTIME_SETTINGS.fetch,
        resolver=public_resolver,
    ).fetch(
        "https://example.com/old",
        etag='"version-1"',
        last_modified="Wed, 05 Aug 2026 09:00:00 GMT",
    )

    assert result.status_code == 304
    assert len(seen) == 2
    assert all(item[1] == '"version-1"' for item in seen)
    assert all(item[2] == "Wed, 05 Aug 2026 09:00:00 GMT" for item in seen)


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(404, False), (429, True), (503, True)],
)
def test_http_failure_retry_policy_is_bounded_by_status(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    retryable: bool,
) -> None:
    install_mock_transport(
        monkeypatch,
        lambda _request: httpx.Response(status, headers={"Retry-After": "30"}),
    )

    with pytest.raises(SafeFetchError) as error:
        SafeHttpFetcher(
            settings.RUNTIME_SETTINGS.fetch,
            resolver=public_resolver,
        ).fetch("https://example.com/jobs")

    assert error.value.code == "FETCH_HTTP_STATUS"
    assert error.value.retryable is retryable
    assert error.value.headers_filtered == {"retry-after": "30"}


def test_content_type_and_stream_size_policies_are_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_mock_transport(
        monkeypatch,
        lambda _request: httpx.Response(
            200,
            headers={"Content-Type": "image/png"},
            content=b"not-a-job-page",
        ),
    )
    with pytest.raises(SafeFetchError) as content_type_error:
        SafeHttpFetcher(
            settings.RUNTIME_SETTINGS.fetch,
            resolver=public_resolver,
        ).fetch("https://example.com/logo")
    assert content_type_error.value.code == "FETCH_CONTENT_TYPE_BLOCKED"

    policy = settings.RUNTIME_SETTINGS.fetch.model_copy(update={"max_response_bytes": 1024})
    install_mock_transport(
        monkeypatch,
        lambda _request: httpx.Response(
            200,
            headers={"Content-Type": "text/plain"},
            content=b"x" * 1025,
        ),
    )
    with pytest.raises(SafeFetchError) as size_error:
        SafeHttpFetcher(policy, resolver=public_resolver).fetch("https://example.com/large")
    assert size_error.value.code == "FETCH_RESPONSE_TOO_LARGE"


class RecordingBackend:
    def __init__(self) -> None:
        self.hosts: list[str] = []

    def connect_tcp(
        self,
        host: str,
        _port: int,
        *,
        timeout: float | None,
        local_address: str | None,
        socket_options: Iterable[object] | None,
    ) -> object:
        self.hosts.append(host)
        return object()


def test_pinned_network_backend_connects_only_to_prevalidated_address() -> None:
    pinned = PinnedNetworkBackend(
        expected_host="example.com",
        addresses=("93.184.216.34",),
    )
    recorder = RecordingBackend()
    pinned.backend = recorder  # type: ignore[assignment]

    stream = pinned.connect_tcp("example.com", 443)

    assert stream is not None
    assert recorder.hosts == ["93.184.216.34"]
    with pytest.raises(httpcore.ConnectError):
        pinned.connect_tcp("changed.example", 443)
