from __future__ import annotations

import hashlib
import ssl
import time
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urljoin

import httpcore
import httpx

from apps.sources.contracts import SafeFetchResultV1
from apps.sources.policy import (
    Resolver,
    SourcePolicyError,
    ValidatedTarget,
    redact_url,
    system_resolver,
    validate_target,
)
from config.runtime import FetchPolicySettings

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
SocketOption = (
    tuple[int, int, int] | tuple[int, int, bytes | bytearray] | tuple[int, int, None, int]
)
FILTERED_HEADERS = {
    "content-language",
    "content-length",
    "content-type",
    "etag",
    "last-modified",
    "retry-after",
}


class SafeFetchError(RuntimeError):
    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        redirect_chain: list[dict[str, object]] | None = None,
        final_url: str = "",
        elapsed_ms: int | None = None,
        headers_filtered: dict[str, str] | None = None,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retryable = retryable
        self.status_code = status_code
        self.redirect_chain = redirect_chain or []
        self.final_url = final_url
        self.elapsed_ms = elapsed_ms
        self.headers_filtered = headers_filtered or {}


class PinnedNetworkBackend(httpcore.NetworkBackend):
    def __init__(self, *, expected_host: str, addresses: tuple[str, ...]) -> None:
        self.expected_host = expected_host
        self.addresses = addresses
        self.backend = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.NetworkStream:
        if host.casefold().rstrip(".") != self.expected_host:
            raise httpcore.ConnectError("Connection hostname differs from the validated target.")
        last_error: Exception | None = None
        for address in self.addresses:
            try:
                return self.backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except httpcore.NetworkError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise httpcore.ConnectError("No validated address was available.")

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.NetworkStream:
        raise httpcore.UnsupportedProtocol("Unix sockets are prohibited by source policy.")


class CoreResponseStream(httpx.SyncByteStream):
    def __init__(self, stream: Iterable[bytes]) -> None:
        self.stream = stream

    def __iter__(self) -> Iterator[bytes]:
        yield from self.stream

    def close(self) -> None:
        close = getattr(self.stream, "close", None)
        if callable(close):
            close()


class PinnedHTTPTransport(httpx.BaseTransport):
    def __init__(self, target: ValidatedTarget) -> None:
        backend = PinnedNetworkBackend(
            expected_host=target.url.hostname_ascii,
            addresses=target.addresses,
        )
        self.pool = httpcore.ConnectionPool(
            ssl_context=ssl.create_default_context(),
            max_connections=1,
            max_keepalive_connections=0,
            http1=True,
            http2=False,
            retries=0,
            network_backend=backend,
        )

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        core_response = self.pool.handle_request(core_request)
        return httpx.Response(
            status_code=core_response.status,
            headers=core_response.headers,
            stream=CoreResponseStream(cast(Iterable[bytes], core_response.stream)),
            extensions=core_response.extensions,
        )

    def close(self) -> None:
        self.pool.close()


def _filtered_headers(response: httpx.Response) -> dict[str, str]:
    return {
        name.casefold(): value[:1000]
        for name, value in response.headers.items()
        if name.casefold() in FILTERED_HEADERS
    }


def _media_type(value: str) -> str:
    return value.split(";", 1)[0].strip().casefold()


def _encoding(value: str) -> str:
    for part in value.split(";")[1:]:
        name, separator, encoding = part.strip().partition("=")
        if separator and name.casefold() == "charset":
            return encoding.strip("\"'").casefold()[:64]
    return "utf-8"


class SafeHttpFetcher:
    def __init__(
        self,
        policy: FetchPolicySettings,
        *,
        resolver: Resolver = system_resolver,
    ) -> None:
        self.policy = policy
        self.resolver = resolver

    def fetch(
        self,
        requested_url: str,
        *,
        etag: str = "",
        last_modified: str = "",
    ) -> SafeFetchResultV1:
        start = time.monotonic()
        deadline = start + self.policy.total_timeout_seconds
        current_url = requested_url
        redirect_chain: list[dict[str, object]] = []
        visited: set[str] = set()
        original_canonical = ""
        for hop in range(self.policy.max_redirects + 1):
            try:
                target = validate_target(current_url, self.policy, resolver=self.resolver)
            except SourcePolicyError as exc:
                raise SafeFetchError(
                    exc.code,
                    exc.safe_message,
                    redirect_chain=redirect_chain,
                    final_url=current_url,
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                ) from exc
            if not original_canonical:
                original_canonical = target.url.canonical
            if target.url.canonical in visited:
                raise SafeFetchError(
                    "REDIRECT_LOOP",
                    "The source returned a redirect loop.",
                    redirect_chain=redirect_chain,
                    final_url=target.url.canonical,
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                )
            visited.add(target.url.canonical)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SafeFetchError(
                    "FETCH_TOTAL_TIMEOUT",
                    "The source exceeded the total fetch deadline.",
                    retryable=True,
                    redirect_chain=redirect_chain,
                    final_url=target.url.canonical,
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                )
            headers = {
                "Accept": ", ".join(self.policy.allowed_content_types),
                "Accept-Encoding": "identity",
                "User-Agent": self.policy.user_agent,
            }
            if etag:
                headers["If-None-Match"] = etag[:1000]
            if last_modified:
                headers["If-Modified-Since"] = last_modified[:1000]
            timeout = httpx.Timeout(
                connect=min(self.policy.connect_timeout_seconds, remaining),
                read=min(self.policy.read_timeout_seconds, remaining),
                write=min(self.policy.connect_timeout_seconds, remaining),
                pool=min(self.policy.connect_timeout_seconds, remaining),
            )
            try:
                with (
                    PinnedHTTPTransport(target) as transport,
                    httpx.Client(
                        transport=transport,
                        timeout=timeout,
                        follow_redirects=False,
                        trust_env=False,
                        cookies=None,
                    ) as client,
                    client.stream("GET", target.url.canonical, headers=headers) as response,
                ):
                    filtered = _filtered_headers(response)
                    if response.status_code in REDIRECT_STATUSES:
                        location = response.headers.get("location", "").strip()
                        if not location:
                            raise SafeFetchError(
                                "REDIRECT_LOCATION_MISSING",
                                "The source returned a redirect without a location.",
                                status_code=response.status_code,
                                redirect_chain=redirect_chain,
                                final_url=target.url.canonical,
                                elapsed_ms=int((time.monotonic() - start) * 1000),
                                headers_filtered=filtered,
                            )
                        if hop >= self.policy.max_redirects:
                            raise SafeFetchError(
                                "REDIRECT_LIMIT",
                                "The source exceeded the redirect limit.",
                                status_code=response.status_code,
                                redirect_chain=redirect_chain,
                                final_url=target.url.canonical,
                                elapsed_ms=int((time.monotonic() - start) * 1000),
                                headers_filtered=filtered,
                            )
                        next_url = urljoin(target.url.canonical, location)
                        redirect_chain.append(
                            {
                                "from": redact_url(target.url.canonical),
                                "to": redact_url(next_url),
                                "status_code": response.status_code,
                            }
                        )
                        current_url = next_url
                        continue
                    if response.status_code == 304:
                        return SafeFetchResultV1(
                            requested_url=original_canonical,
                            final_url=target.url.canonical,
                            status_code=304,
                            retrieved_at_iso=datetime.now(UTC).isoformat(),
                            content_type="",
                            encoding="",
                            headers_filtered=filtered,
                            body=b"",
                            body_sha256=hashlib.sha256(b"").hexdigest(),
                            body_size_bytes=0,
                            elapsed_ms=int((time.monotonic() - start) * 1000),
                            redirect_chain=redirect_chain,
                            retryable=False,
                        )
                    if not 200 <= response.status_code < 300:
                        retryable = response.status_code == 429 or 500 <= response.status_code < 600
                        raise SafeFetchError(
                            "FETCH_HTTP_STATUS",
                            f"The public source returned HTTP {response.status_code}.",
                            retryable=retryable,
                            status_code=response.status_code,
                            redirect_chain=redirect_chain,
                            final_url=target.url.canonical,
                            elapsed_ms=int((time.monotonic() - start) * 1000),
                            headers_filtered=filtered,
                        )
                    content_type_header = response.headers.get("content-type", "")
                    content_type = _media_type(content_type_header)
                    if content_type not in self.policy.allowed_content_types:
                        raise SafeFetchError(
                            "FETCH_CONTENT_TYPE_BLOCKED",
                            "The source returned an unsupported content type.",
                            status_code=response.status_code,
                            redirect_chain=redirect_chain,
                            final_url=target.url.canonical,
                            elapsed_ms=int((time.monotonic() - start) * 1000),
                            headers_filtered=filtered,
                        )
                    declared_length = response.headers.get("content-length")
                    if (
                        declared_length
                        and declared_length.isdecimal()
                        and int(declared_length) > self.policy.max_response_bytes
                    ):
                        raise SafeFetchError(
                            "FETCH_RESPONSE_TOO_LARGE",
                            "The source exceeded the response byte limit.",
                            status_code=response.status_code,
                            redirect_chain=redirect_chain,
                            final_url=target.url.canonical,
                            elapsed_ms=int((time.monotonic() - start) * 1000),
                            headers_filtered=filtered,
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() > deadline:
                            raise SafeFetchError(
                                "FETCH_TOTAL_TIMEOUT",
                                "The source exceeded the total fetch deadline.",
                                retryable=True,
                                status_code=response.status_code,
                                redirect_chain=redirect_chain,
                                final_url=target.url.canonical,
                                elapsed_ms=int((time.monotonic() - start) * 1000),
                                headers_filtered=filtered,
                            )
                        body.extend(chunk)
                        if len(body) > self.policy.max_response_bytes:
                            raise SafeFetchError(
                                "FETCH_RESPONSE_TOO_LARGE",
                                "The source exceeded the response byte limit.",
                                status_code=response.status_code,
                                redirect_chain=redirect_chain,
                                final_url=target.url.canonical,
                                elapsed_ms=int((time.monotonic() - start) * 1000),
                                headers_filtered=filtered,
                            )
                    body_bytes = bytes(body)
                    if not body_bytes:
                        raise SafeFetchError(
                            "FETCH_EMPTY_BODY",
                            "The source returned an empty document.",
                            status_code=response.status_code,
                            redirect_chain=redirect_chain,
                            final_url=target.url.canonical,
                            elapsed_ms=int((time.monotonic() - start) * 1000),
                            headers_filtered=filtered,
                        )
                    return SafeFetchResultV1(
                        requested_url=original_canonical,
                        final_url=target.url.canonical,
                        status_code=response.status_code,
                        retrieved_at_iso=datetime.now(UTC).isoformat(),
                        content_type=content_type,
                        encoding=_encoding(content_type_header),
                        headers_filtered=filtered,
                        body=body_bytes,
                        body_sha256=hashlib.sha256(body_bytes).hexdigest(),
                        body_size_bytes=len(body_bytes),
                        elapsed_ms=int((time.monotonic() - start) * 1000),
                        redirect_chain=redirect_chain,
                        retryable=False,
                    )
            except SafeFetchError:
                raise
            except (httpcore.TimeoutException, httpx.TimeoutException) as exc:
                raise SafeFetchError(
                    "FETCH_NETWORK_TIMEOUT",
                    "The source did not respond within the network timeout.",
                    retryable=True,
                    redirect_chain=redirect_chain,
                    final_url=target.url.canonical,
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                ) from exc
            except (httpcore.NetworkError, httpx.NetworkError, ssl.SSLError) as exc:
                raise SafeFetchError(
                    "FETCH_NETWORK_ERROR",
                    "The source could not be reached through the validated network path.",
                    retryable=True,
                    redirect_chain=redirect_chain,
                    final_url=target.url.canonical,
                    elapsed_ms=int((time.monotonic() - start) * 1000),
                ) from exc
        raise SafeFetchError(
            "REDIRECT_LIMIT",
            "The source exceeded the redirect limit.",
            redirect_chain=redirect_chain,
            final_url=current_url,
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
