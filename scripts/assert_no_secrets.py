from __future__ import annotations

import json
import sys


def main() -> None:
    report = json.load(sys.stdin)
    results = report.get("results", {})
    findings = [
        f"{path}:{item['line_number']}" for path, items in results.items() for item in items
    ]
    if findings:
        raise SystemExit("Potential secrets detected:\n" + "\n".join(findings))
    print("No potential secrets detected in implementation files.")


if __name__ == "__main__":
    main()
