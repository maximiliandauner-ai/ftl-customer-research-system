from __future__ import annotations

import stat
from base64 import urlsafe_b64decode
from pathlib import Path

import pytest

from scripts.bootstrap_env import create_environment, fill_missing_contact_keys


def _decode_key(value: str) -> bytes:
    return urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def test_create_environment_generates_separate_protected_contact_keys(tmp_path: Path) -> None:
    template = tmp_path / ".env.example"
    target = tmp_path / ".env"
    template.write_text(
        "DJANGO_SECRET_KEY=\n"
        "POSTGRES_PASSWORD=\n"
        "CONTACT_ROUTE_ENCRYPTION_KEY=\n"
        "CONTACT_ROUTE_HMAC_KEY=\n",
        encoding="utf-8",
    )

    assert create_environment(target=target, template_path=template) is True
    assert create_environment(target=target, template_path=template) is False
    values = _values(target)

    encryption_key = _decode_key(values["CONTACT_ROUTE_ENCRYPTION_KEY"])
    hmac_key = _decode_key(values["CONTACT_ROUTE_HMAC_KEY"])
    assert len(encryption_key) == 32
    assert len(hmac_key) == 32
    assert encryption_key != hmac_key
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_fill_missing_contact_keys_never_overwrites_an_existing_key(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    retained = "A" * 43
    target.write_text(
        f"CONTACT_ROUTE_ENCRYPTION_KEY={retained}\nCONTACT_ROUTE_HMAC_KEY=\n",
        encoding="utf-8",
    )

    assert fill_missing_contact_keys(target=target) == 1
    values = _values(target)
    assert values["CONTACT_ROUTE_ENCRYPTION_KEY"] == retained
    assert len(_decode_key(values["CONTACT_ROUTE_HMAC_KEY"])) == 32
    assert fill_missing_contact_keys(target=target) == 0


def test_fill_missing_contact_keys_requires_existing_entries(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    target.write_text("CONTACT_ROUTE_ENCRYPTION_KEY=present\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="CONTACT_ROUTE_HMAC_KEY"):
        fill_missing_contact_keys(target=target)
