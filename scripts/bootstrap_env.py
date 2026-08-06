from __future__ import annotations

import argparse
import base64
import secrets
from pathlib import Path


def _contact_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


def create_environment(*, target: Path, template_path: Path) -> bool:
    if target.exists():
        return False
    template = template_path.read_text(encoding="utf-8")
    replacements = {
        "DJANGO_SECRET_KEY=\n": f"DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n",
        "POSTGRES_PASSWORD=\n": f"POSTGRES_PASSWORD={secrets.token_urlsafe(36)}\n",
        "CONTACT_ROUTE_ENCRYPTION_KEY=\n": (f"CONTACT_ROUTE_ENCRYPTION_KEY={_contact_key()}\n"),
        "CONTACT_ROUTE_HMAC_KEY=\n": f"CONTACT_ROUTE_HMAC_KEY={_contact_key()}\n",
    }
    rendered = template
    for source, replacement in replacements.items():
        if source not in rendered:
            raise RuntimeError(f"Missing required template entry: {source.strip()}")
        rendered = rendered.replace(source, replacement, 1)
    target.write_text(rendered, encoding="utf-8")
    target.chmod(0o600)
    return True


def fill_missing_contact_keys(*, target: Path) -> int:
    if not target.exists():
        raise RuntimeError(".env does not exist; run make bootstrap first.")
    rendered = target.read_text(encoding="utf-8")
    changed = 0
    for name in ("CONTACT_ROUTE_ENCRYPTION_KEY", "CONTACT_ROUTE_HMAC_KEY"):
        empty_entry = f"{name}=\n"
        if empty_entry in rendered:
            rendered = rendered.replace(empty_entry, f"{name}={_contact_key()}\n", 1)
            changed += 1
        elif not any(line.startswith(f"{name}=") for line in rendered.splitlines()):
            raise RuntimeError(f"Missing required .env entry: {name}")
    if changed:
        target.write_text(rendered, encoding="utf-8")
    target.chmod(0o600)
    return changed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fill-missing-contact-keys", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    target = root / ".env"
    if args.fill_missing_contact_keys:
        changed = fill_missing_contact_keys(target=target)
        print(f"Generated {changed} missing contact key(s); .env mode is 0600.")
        return
    if create_environment(target=target, template_path=root / ".env.example"):
        print("Created .env with local-only generated secrets and mode 0600.")
    else:
        print(".env already exists; leaving it unchanged.")


if __name__ == "__main__":
    main()
