from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load(path: str) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def ports(service: dict[str, Any]) -> list[dict[str, Any]]:
    return service.get("ports", [])


def assert_private_data_services(config: dict[str, Any], label: str) -> None:
    services = config["services"]
    for name in ("postgres", "redis"):
        if ports(services[name]):
            raise AssertionError(f"{label}: {name} must not publish a host port")


def assert_loopback(service: dict[str, Any], label: str) -> None:
    published = ports(service)
    if not published or any(port.get("host_ip") != "127.0.0.1" for port in published):
        raise AssertionError(f"{label} must publish on 127.0.0.1 only")


def volume_targets(service: dict[str, Any]) -> set[str]:
    return {volume.get("target", "") for volume in service.get("volumes", [])}


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: check_compose_policy.py BASE DEV PROD")
    base, development, production = (load(path) for path in sys.argv[1:])
    assert_private_data_services(base, "base")
    assert_private_data_services(production, "production")
    if "/var/lib/postgresql" not in volume_targets(base["services"]["postgres"]):
        raise AssertionError("PostgreSQL 18 volume must target /var/lib/postgresql")
    for name in ("postgres", "redis", "web"):
        assert_loopback(development["services"][name], f"development {name}")
    app_services = ("web", "worker-core", "worker-research", "beat")
    for name in app_services:
        service = production["services"][name]
        if "build" in service:
            raise AssertionError(f"production {name} must use a prebuilt image")
        if not service.get("read_only"):
            raise AssertionError(f"production {name} must use a read-only root filesystem")
        if any(volume.get("type") == "bind" for volume in service.get("volumes", [])):
            raise AssertionError(f"production {name} must not bind-mount source code")
        command = " ".join(str(part) for part in service.get("command", []))
        if "migrate" in command:
            raise AssertionError(f"production {name} must not run migrations")
    print("Base, development, and production Compose policies are valid.")


if __name__ == "__main__":
    main()
