import ast
from pathlib import Path


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_domain_does_not_depend_on_django_or_integrations() -> None:
    root = Path(__file__).resolve().parents[2]
    for path in (root / "domain").rglob("*.py"):
        imported = imports(path)
        assert not any(name == "django" or name.startswith("django.") for name in imported)
        assert not any(
            name == "integrations" or name.startswith("integrations.") for name in imported
        )
