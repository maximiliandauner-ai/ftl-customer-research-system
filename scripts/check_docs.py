from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    missing: list[str] = []
    for document in sorted(root.rglob("*.md")):
        if ".git" in document.parts:
            continue
        for raw_target in LINK.findall(document.read_text(encoding="utf-8")):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = unquote(target.split("#", 1)[0])
            if not path_part:
                continue
            resolved = (document.parent / path_part).resolve()
            if not resolved.exists():
                missing.append(f"{document.relative_to(root)} -> {target}")
    if missing:
        raise SystemExit("Unresolved Markdown links:\n" + "\n".join(missing))
    print("All local Markdown links resolve.")


if __name__ == "__main__":
    main()
