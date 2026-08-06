import json
import logging

from apps.core.logging import SafeJsonFormatter, redact


def test_redacts_assignments_and_url_credentials() -> None:
    message = "password=hunter2 api_key:token postgresql://user:db-pass@postgres/db"  # pragma: allowlist secret  # noqa: E501

    redacted = redact(message)

    assert "hunter2" not in redacted
    assert "token" not in redacted
    assert "db-pass" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_formatter_emits_bounded_json() -> None:
    record = logging.LogRecord("ftl", logging.INFO, __file__, 1, "secret=hidden", (), None)

    payload = json.loads(SafeJsonFormatter().format(record))

    assert payload["event"] == "ftl"
    assert payload["message"] == "secret=[REDACTED]"
    assert payload["request_id"] is None
    assert payload["status"] == "unknown"
    assert "service" in payload


def test_formatter_records_exception_type_without_traceback_text() -> None:
    try:
        raise ValueError("password=hidden")
    except ValueError:
        record = logging.LogRecord(
            "ftl", logging.ERROR, __file__, 1, "safe failure", (), __import__("sys").exc_info()
        )

    payload = json.loads(SafeJsonFormatter().format(record))

    assert payload["exception_type"] == "ValueError"
    assert "hidden" not in json.dumps(payload)
