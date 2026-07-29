"""Safe JSON evaluation suite loading from one authorized root."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields
from enum import Enum
from pathlib import Path
from typing import NoReturn, cast

from contextforge.domain import (
    ArtifactPath,
    FingerprintOrdering,
    ProjectFingerprint,
    fingerprint_project,
)
from contextforge.domain.tasks import RequestedOutput, TaskKind
from contextforge.evaluation import (
    EvaluationCase,
    EvaluationSuite,
    RelevanceJudgment,
    RelevanceLevel,
)
from contextforge.retrieval import ContextBudget


class EvaluationSuiteLoadError(ValueError):
    """A stable, field-addressed evaluation suite loading failure."""


def _fail(field: str, message: str) -> NoReturn:
    raise EvaluationSuiteLoadError(f"{field}: {message}")


def _object(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _fail(field, "must be an object")
    if any(not isinstance(key, str) for key in value):
        _fail(field, "keys must be strings")
    return value


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        _fail(field, "must be an array")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str):
        _fail(field, "must be a string")
    return value


def _fields(value: Mapping[str, object], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        _fail(
            field,
            f"fields do not match schema; "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}",
        )


def _enum[EnumT: Enum](
    enum_type: type[EnumT],
    value: object,
    field: str,
) -> EnumT:
    serialized = _string(value, field)
    try:
        return enum_type(serialized)
    except ValueError as error:
        _fail(field, f"unsupported value {serialized!r}")
        raise AssertionError from error


def _path(value: object, field: str) -> ArtifactPath:
    try:
        return ArtifactPath(_string(value, field))
    except (TypeError, ValueError) as error:
        _fail(field, str(error))


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{field}[{index}]") for index, item in enumerate(_array(value, field))
    )


def _path_tuple(value: object, field: str) -> tuple[ArtifactPath, ...]:
    return tuple(
        _path(item, f"{field}[{index}]") for index, item in enumerate(_array(value, field))
    )


def _safe_relative(root: Path, relative: Path, field: str, *, must_be_file: bool) -> Path:
    if relative.is_absolute():
        _fail(field, "absolute paths are not allowed")
    if any(part == ".." for part in relative.parts):
        _fail(field, "parent traversal is not allowed")
    try:
        candidate = root.joinpath(relative).resolve(strict=True)
        candidate.relative_to(root)
    except (OSError, ValueError):
        _fail(field, "path does not exist within the evaluation root")
    if must_be_file and not candidate.is_file():
        _fail(field, "must identify a regular file")
    if not must_be_file and not candidate.is_dir():
        _fail(field, "must identify a directory")
    return candidate


def fingerprint_fixture_project(project_root: Path) -> ProjectFingerprint:
    """Fingerprint regular fixture files by canonical path and raw content."""
    if not isinstance(project_root, Path):
        raise TypeError("project_root must be a Path")
    root = project_root.resolve(strict=True)
    if not root.is_dir():
        raise EvaluationSuiteLoadError("fixture_project: must identify a directory")

    components: list[str] = []
    for candidate in sorted(root.rglob("*"), key=lambda path: path.as_posix()):
        if candidate.is_symlink():
            raise EvaluationSuiteLoadError(
                f"fixture_project.{candidate.relative_to(root).as_posix()}: "
                "symbolic links are not allowed"
            )
        if candidate.is_dir():
            continue
        if not candidate.is_file():
            raise EvaluationSuiteLoadError(
                f"fixture_project.{candidate.relative_to(root).as_posix()}: must be a regular file"
            )
        resolved = candidate.resolve(strict=True)
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as error:
            raise EvaluationSuiteLoadError("fixture project path escaped its root") from error
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        components.extend((f"path={relative}", f"content_sha256={digest}"))
    return fingerprint_project(tuple(components), ordering=FingerprintOrdering.ORDERED)


class FilesystemEvaluationSuiteLoader:
    """Load and verify JSON suites below one immutable evaluation root."""

    def __init__(self, evaluation_root: Path) -> None:
        if not isinstance(evaluation_root, Path):
            raise TypeError("evaluation_root must be a Path")
        try:
            root = evaluation_root.resolve(strict=True)
        except OSError as error:
            raise EvaluationSuiteLoadError("evaluation_root: does not exist") from error
        if not root.is_dir():
            raise EvaluationSuiteLoadError("evaluation_root: must be a directory")
        self._root = root

    def fixture_root(self, fixture_project_id: str) -> Path:
        """Resolve one verified fixture project below the evaluation root."""
        if not isinstance(fixture_project_id, str) or not fixture_project_id.strip():
            raise TypeError("fixture_project_id must be a non-empty string")
        return _safe_relative(
            self._root,
            Path("projects", fixture_project_id),
            "fixture_project_id",
            must_be_file=False,
        )

    def load(self, suite_path: Path) -> EvaluationSuite:
        """Load one suite and verify every referenced fixture fingerprint."""
        if not isinstance(suite_path, Path):
            raise TypeError("suite_path must be a Path")
        source = _safe_relative(self._root, suite_path, "suite_path", must_be_file=True)
        try:
            serialized = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise EvaluationSuiteLoadError("suite_path: could not be read as UTF-8") from error
        try:
            decoded = json.loads(serialized, object_pairs_hook=self._reject_duplicate_keys)
        except json.JSONDecodeError as error:
            raise EvaluationSuiteLoadError(
                f"suite: invalid JSON at line {error.lineno}, column {error.colno}"
            ) from error

        suite_data = _object(decoded, "suite")
        _fields(suite_data, {"suite_id", "suite_version", "cases"}, "suite")
        cases = tuple(
            self._parse_case(item, index)
            for index, item in enumerate(_array(suite_data["cases"], "suite.cases"))
        )
        try:
            return EvaluationSuite(
                suite_id=_string(suite_data["suite_id"], "suite.suite_id"),
                suite_version=_string(suite_data["suite_version"], "suite.suite_version"),
                cases=cases,
            )
        except (TypeError, ValueError) as error:
            raise EvaluationSuiteLoadError(f"suite: {error}") from error

    @staticmethod
    def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise EvaluationSuiteLoadError(f"suite: duplicate JSON key {key!r}")
            result[key] = value
        return result

    def _parse_case(self, value: object, index: int) -> EvaluationCase:
        prefix = f"suite.cases[{index}]"
        data = _object(value, prefix)
        expected = {
            "case_id",
            "context_budget",
            "expected_changed_paths",
            "expected_evidence",
            "fixture_fingerprint",
            "fixture_project_id",
            "judgments",
            "requested_output",
            "tags",
            "task_kind",
            "task_text",
        }
        _fields(data, expected, prefix)
        case_id = _string(data["case_id"], f"{prefix}.case_id")
        case_prefix = f"{prefix}({case_id})"
        try:
            fingerprint = ProjectFingerprint.from_string(
                _string(data["fixture_fingerprint"], f"{case_prefix}.fixture_fingerprint")
            )
            case = EvaluationCase(
                case_id=case_id,
                fixture_project_id=_string(
                    data["fixture_project_id"], f"{case_prefix}.fixture_project_id"
                ),
                fixture_fingerprint=fingerprint,
                task_text=_string(data["task_text"], f"{case_prefix}.task_text"),
                task_kind=_enum(TaskKind, data["task_kind"], f"{case_prefix}.task_kind"),
                requested_output=_enum(
                    RequestedOutput,
                    data["requested_output"],
                    f"{case_prefix}.requested_output",
                ),
                judgments=self._parse_judgments(data["judgments"], case_prefix),
                context_budget=self._parse_budget(data["context_budget"], case_prefix),
                tags=_string_tuple(data["tags"], f"{case_prefix}.tags"),
                expected_evidence=_string_tuple(
                    data["expected_evidence"], f"{case_prefix}.expected_evidence"
                ),
                expected_changed_paths=_path_tuple(
                    data["expected_changed_paths"],
                    f"{case_prefix}.expected_changed_paths",
                ),
            )
        except EvaluationSuiteLoadError:
            raise
        except (TypeError, ValueError) as error:
            raise EvaluationSuiteLoadError(f"{case_prefix}: {error}") from error
        self._verify_fixture(case, case_prefix)
        return case

    @staticmethod
    def _parse_judgments(value: object, prefix: str) -> tuple[RelevanceJudgment, ...]:
        judgments: list[RelevanceJudgment] = []
        for index, item in enumerate(_array(value, f"{prefix}.judgments")):
            field = f"{prefix}.judgments[{index}]"
            data = _object(item, field)
            _fields(data, {"path", "relevance", "symbols"}, field)
            judgments.append(
                RelevanceJudgment(
                    path=_path(data["path"], f"{field}.path"),
                    relevance=_enum(
                        RelevanceLevel,
                        data["relevance"],
                        f"{field}.relevance",
                    ),
                    symbols=_string_tuple(data["symbols"], f"{field}.symbols"),
                )
            )
        return tuple(judgments)

    @staticmethod
    def _parse_budget(value: object, prefix: str) -> ContextBudget:
        field = f"{prefix}.context_budget"
        data = _object(value, field)
        expected = {item.name for item in fields(ContextBudget)}
        if not set(data) <= expected:
            _fail(field, f"unexpected fields={sorted(set(data) - expected)}")
        for name, item in data.items():
            if item is not None and type(item) is not int:
                _fail(f"{field}.{name}", "must be an integer or null")
        try:
            budget_values = cast("dict[str, int | None]", dict(data))
            return ContextBudget(**budget_values)
        except (TypeError, ValueError) as error:
            raise EvaluationSuiteLoadError(f"{field}: {error}") from error

    def _verify_fixture(self, case: EvaluationCase, prefix: str) -> None:
        relative = Path("projects", case.fixture_project_id)
        project_root = _safe_relative(
            self._root,
            relative,
            f"{prefix}.fixture_project_id",
            must_be_file=False,
        )
        actual = fingerprint_fixture_project(project_root)
        if actual != case.fixture_fingerprint:
            _fail(
                f"{prefix}.fixture_fingerprint",
                f"does not match fixture project {case.fixture_project_id!r}",
            )
