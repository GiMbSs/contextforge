"""Architecture dependency tests for CF-014 increment I004."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class DependencyRule:
    """One forbidden dependency boundary within the ContextForge package."""

    source_area: str
    forbidden_prefixes: tuple[str, ...]
    description: str


RULES = (
    DependencyRule(
        source_area="domain",
        forbidden_prefixes=(
            "contextforge.adapters",
            "contextforge.application",
            "contextforge.cli",
        ),
        description="domain must not depend on application, CLI, or adapters",
    ),
    DependencyRule(
        source_area="application",
        forbidden_prefixes=("contextforge.adapters", "contextforge.cli"),
        description="application must not depend on concrete adapters or CLI",
    ),
    DependencyRule(
        source_area="cli",
        forbidden_prefixes=(
            "contextforge.context",
            "contextforge.domain",
            "contextforge.indexer",
            "contextforge.patch",
            "contextforge.prompt",
            "contextforge.provider",
            "contextforge.retrieval",
            "contextforge.scanner",
            "contextforge.task",
        ),
        description="CLI must use application interfaces, not capability internals",
    ),
    DependencyRule(
        source_area="provider",
        forbidden_prefixes=(
            "aiohttp",
            "anthropic",
            "contextforge.adapters.providers",
            "httpx",
            "ollama",
            "openai",
            "requests",
            "urllib3",
        ),
        description="provider Core contracts must not depend on HTTP clients or SDKs",
    ),
    DependencyRule(
        source_area="patch",
        forbidden_prefixes=(
            "contextforge.adapters.filesystem",
            "contextforge.filesystem",
            "contextforge.patch.applier",
            "contextforge.patch.application",
        ),
        description="patch validation must not depend on filesystem application",
    ),
)


def _module_name(source_root: Path, source_file: Path) -> str:
    relative = source_file.relative_to(source_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_imports(tree: ast.AST, current_module: str, is_package: bool) -> Iterable[str]:
    current_parts = current_module.split(".")
    package_parts = current_parts if is_package else current_parts[:-1]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parent_count = node.level - 1
                anchor = package_parts[: len(package_parts) - parent_count]
                module_parts = node.module.split(".") if node.module else []
                imported_module = ".".join((*anchor, *module_parts))
            else:
                imported_module = node.module or ""

            if imported_module:
                yield imported_module
            if node.module is None or (node.level == 0 and node.module == "contextforge"):
                for alias in node.names:
                    if alias.name != "*":
                        yield ".".join(part for part in (imported_module, alias.name) if part)


def find_dependency_violations(source_root: Path) -> list[str]:
    """Return deterministic descriptions of forbidden imports beneath ``source_root``."""
    violations: list[str] = []

    for source_file in sorted(source_root.rglob("*.py")):
        relative = source_file.relative_to(source_root)
        if len(relative.parts) < 2 or relative.parts[0] != "contextforge":
            continue

        source_area = relative.parts[1]
        applicable_rules = tuple(rule for rule in RULES if rule.source_area == source_area)
        if not applicable_rules:
            continue

        source = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(relative))
        current_module = _module_name(source_root, source_file)
        imports = sorted(
            set(_resolve_imports(tree, current_module, source_file.name == "__init__.py"))
        )

        for rule in applicable_rules:
            for imported_module in imports:
                if any(
                    imported_module == prefix or imported_module.startswith(f"{prefix}.")
                    for prefix in rule.forbidden_prefixes
                ):
                    violations.append(
                        f"{relative.as_posix()}: imports {imported_module!r}; {rule.description}"
                    )

    return violations


def test_contextforge_respects_architecture_dependency_rules() -> None:
    source_root = Path(__file__).parents[1] / "src"

    assert find_dependency_violations(source_root) == []


@pytest.mark.parametrize(
    ("relative_path", "source", "expected_description"),
    [
        (
            "contextforge/domain/model.py",
            "from contextforge.cli import main\n",
            "domain must not depend on application, CLI, or adapters",
        ),
        (
            "contextforge/domain/entity.py",
            "from contextforge import application\n",
            "domain must not depend on application, CLI, or adapters",
        ),
        (
            "contextforge/application/service.py",
            "from contextforge.adapters.filesystem import LocalFileSystem\n",
            "application must not depend on concrete adapters or CLI",
        ),
        (
            "contextforge/cli/command.py",
            "from contextforge.scanner import scan\n",
            "CLI must use application interfaces, not capability internals",
        ),
        (
            "contextforge/provider/port.py",
            "import httpx\n",
            "provider Core contracts must not depend on HTTP clients or SDKs",
        ),
        (
            "contextforge/patch/validation.py",
            "from .applier import apply_patch\n",
            "patch validation must not depend on filesystem application",
        ),
    ],
)
def test_forbidden_import_is_reported(
    tmp_path: Path,
    relative_path: str,
    source: str,
    expected_description: str,
) -> None:
    source_root = tmp_path / "src"
    source_file = source_root / relative_path
    source_file.parent.mkdir(parents=True)
    source_file.write_text(source, encoding="utf-8")

    violations = find_dependency_violations(source_root)

    assert len(violations) == 1
    assert expected_description in violations[0]
