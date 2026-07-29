"""Tests for CF-015-E002 filesystem evaluation suite loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contextforge.adapters.evaluation import (
    EvaluationSuiteLoadError,
    FilesystemEvaluationSuiteLoader,
    fingerprint_fixture_project,
)
from contextforge.domain import ArtifactPath
from contextforge.domain.tasks import RequestedOutput, TaskKind
from contextforge.evaluation import (
    EvaluationCase,
    EvaluationSuite,
    RelevanceJudgment,
    RelevanceLevel,
)
from contextforge.retrieval import ContextBudget


def write_fixture(root: Path, project_id: str = "small-python") -> Path:
    project = root / "projects" / project_id
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.py").write_text("def main():\n    return 42\n", encoding="utf-8")
    return project


def suite_document(root: Path) -> dict[str, object]:
    project = write_fixture(root)
    case = EvaluationCase(
        case_id="direct-path",
        fixture_project_id="small-python",
        fixture_fingerprint=fingerprint_fixture_project(project),
        task_text="Explain the entry point.",
        task_kind=TaskKind.EXPLAIN,
        requested_output=RequestedOutput.ANALYSIS,
        judgments=(
            RelevanceJudgment(ArtifactPath("src/main.py"), RelevanceLevel.REQUIRED, ("main",)),
        ),
        context_budget=ContextBudget(max_estimated_tokens=500),
        tags=("retrieval",),
        expected_evidence=("entry point",),
    )
    return EvaluationSuite("core", "1.0", (case,)).to_dict()


def write_suite(root: Path, document: object, name: str = "core.json") -> Path:
    suites = root / "suites"
    suites.mkdir(exist_ok=True)
    path = suites / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_loads_and_verifies_a_json_suite(tmp_path: Path) -> None:
    document = suite_document(tmp_path)
    write_suite(tmp_path, document)

    suite = FilesystemEvaluationSuiteLoader(tmp_path).load(Path("suites/core.json"))

    assert suite.suite_id == "core"
    assert suite.cases[0].task_text == "Explain the entry point."
    assert suite.cases[0].judgments[0].path == ArtifactPath("src/main.py")


def test_gold_labels_are_not_copied_into_task_context(tmp_path: Path) -> None:
    document = suite_document(tmp_path)
    case = document["cases"][0]  # type: ignore[index]
    case["judgments"][0]["symbols"] = ["gold-only-secret-symbol"]  # type: ignore[index]
    write_suite(tmp_path, document)

    loaded = FilesystemEvaluationSuiteLoader(tmp_path).load(Path("suites/core.json"))

    assert loaded.cases[0].task_text == "Explain the entry point."
    assert "gold-only-secret-symbol" not in loaded.cases[0].task_text


@pytest.mark.parametrize("suite_path", [Path("../outside.json"), Path("/outside.json")])
def test_suite_path_cannot_escape_evaluation_root(tmp_path: Path, suite_path: Path) -> None:
    with pytest.raises(EvaluationSuiteLoadError, match="suite_path"):
        FilesystemEvaluationSuiteLoader(tmp_path).load(suite_path)


def test_symlinked_suite_cannot_escape_evaluation_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = tmp_path / "outside.json"
    try:
        link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"File symlinks are unavailable: {error}")

    with pytest.raises(EvaluationSuiteLoadError, match="within the evaluation root"):
        FilesystemEvaluationSuiteLoader(tmp_path).load(Path("outside.json"))


def test_symlinks_inside_fixture_projects_are_rejected(tmp_path: Path) -> None:
    project = write_fixture(tmp_path)
    link = project / "alias.py"
    try:
        link.symlink_to(project / "src" / "main.py")
    except OSError as error:
        pytest.skip(f"File symlinks are unavailable: {error}")

    with pytest.raises(EvaluationSuiteLoadError, match="symbolic links"):
        fingerprint_fixture_project(project)


def test_fixture_fingerprint_mismatch_identifies_case_and_field(tmp_path: Path) -> None:
    document = suite_document(tmp_path)
    case = document["cases"][0]  # type: ignore[index]
    case["fixture_fingerprint"] = "project_sha256_" + "0" * 64  # type: ignore[index]
    write_suite(tmp_path, document)

    with pytest.raises(
        EvaluationSuiteLoadError,
        match=r"suite\.cases\[0\]\(direct-path\)\.fixture_fingerprint",
    ):
        FilesystemEvaluationSuiteLoader(tmp_path).load(Path("suites/core.json"))


def test_schema_error_identifies_case_and_exact_field(tmp_path: Path) -> None:
    document = suite_document(tmp_path)
    case = document["cases"][0]  # type: ignore[index]
    case["context_budget"]["max_items"] = "many"  # type: ignore[index]
    write_suite(tmp_path, document)

    with pytest.raises(
        EvaluationSuiteLoadError,
        match=r"suite\.cases\[0\]\(direct-path\)\.context_budget\.max_items",
    ):
        FilesystemEvaluationSuiteLoader(tmp_path).load(Path("suites/core.json"))


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    suites = tmp_path / "suites"
    suites.mkdir()
    (suites / "core.json").write_text(
        '{"suite_id":"core","suite_id":"other","suite_version":"1.0","cases":[]}',
        encoding="utf-8",
    )

    with pytest.raises(EvaluationSuiteLoadError, match="duplicate JSON key 'suite_id'"):
        FilesystemEvaluationSuiteLoader(tmp_path).load(Path("suites/core.json"))


def test_fixture_fingerprint_is_content_and_path_sensitive(tmp_path: Path) -> None:
    project = write_fixture(tmp_path)
    initial = fingerprint_fixture_project(project)

    (project / "src" / "main.py").write_text("def main():\n    return 43\n", encoding="utf-8")
    content_changed = fingerprint_fixture_project(project)
    (project / "src" / "main.py").rename(project / "src" / "renamed.py")
    path_changed = fingerprint_fixture_project(project)

    assert len({initial, content_changed, path_changed}) == 3


def test_fixture_fingerprint_normalizes_text_line_endings(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    source = project / "module.py"
    source.write_bytes(b"def run():\n    return 1\n")
    unix = fingerprint_fixture_project(project)

    source.write_bytes(b"def run():\r\n    return 1\r\n")
    windows = fingerprint_fixture_project(project)

    assert windows == unix


def test_versioned_core_suite_loads_with_expanded_cases() -> None:
    root = Path(__file__).parent / "fixtures" / "evaluation"

    suite = FilesystemEvaluationSuiteLoader(root).load(Path("suites/core.json"))

    assert tuple(case.case_id for case in suite.cases) == (
        "budget-pressure",
        "competing-symbols",
        "configuration-implementation",
        "deep-dependency-chain",
        "dependency-closure",
        "direct-path",
        "direct-symbol",
        "homonymous-admin-render",
        "homonymous-public-render",
        "lexical-synonym",
        "test-to-implementation",
        "unsolvable-missing-artifact",
    )
