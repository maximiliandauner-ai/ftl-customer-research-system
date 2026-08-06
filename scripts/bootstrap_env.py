from __future__ import annotations

import secrets
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    target = root / ".env"
    if target.exists():
        print(".env already exists; leaving it unchanged.")
        return
    template = (root / ".env.example").read_text(encoding="utf-8")
    replacements = {
        "DJANGO_SECRET_KEY=\n": f"DJANGO_SECRET_KEY={secrets.token_urlsafe(64)}\n",
        "POSTGRES_PASSWORD=\n": f"POSTGRES_PASSWORD={secrets.token_urlsafe(36)}\n",
    }
    rendered = template
    for source, replacement in replacements.items():
        if source not in rendered:
            raise RuntimeError(f"Missing required template entry: {source.strip()}")
        rendered = rendered.replace(source, replacement, 1)
    target.write_text(rendered, encoding="utf-8")
    target.chmod(0o600)
    print("Created .env with local-only generated secrets and mode 0600.")


if __name__ == "__main__":
    main()
