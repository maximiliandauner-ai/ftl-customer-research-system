from __future__ import annotations

import re
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.core.logging import reset_log_context, set_log_context

REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
SAFE_REQUEST_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


def _request_id(value: str | None) -> uuid.UUID:
    if value and SAFE_REQUEST_ID.fullmatch(value):
        try:
            return uuid.UUID(value)
        except ValueError:
            pass
    return uuid.uuid4()


class RequestCorrelationMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = _request_id(request.META.get(REQUEST_ID_HEADER))
        request.request_id = request_id  # type: ignore[attr-defined]
        token = set_log_context(request_id=str(request_id))
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = str(request_id)
            return response
        finally:
            reset_log_context(token)
