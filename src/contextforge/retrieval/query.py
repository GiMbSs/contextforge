"""Deterministic task-query normalization without inference."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from contextforge.domain import TaskId, TaskKind, TaskSpecification

TASK_QUERY_NORMALIZER_VERSION = "task-query-v1"

_QUOTED_PATTERN = re.compile(r"`([^`\r\n]+)`|\"([^\"\r\n]+)\"|'([^'\r\n]+)'")
_PATH_PATTERN = re.compile(
    r"(?<![\w.])(?:[^\W/\\]+[/\\])+[^\s,;:(){}\[\]<>\"'`]+",
    re.UNICODE,
)
_FILENAME_PATTERN = re.compile(
    r"(?<![\w.-])[\w.-]+\.[A-Za-z0-9][A-Za-z0-9._-]*(?![\w.-])",
    re.UNICODE,
)
_QUALIFIED_SYMBOL_PATTERN = re.compile(
    r"(?<!\w)[^\W\d]\w*(?:\.[^\W\d]\w*)+(?!\w)",
    re.UNICODE,
)
_IDENTIFIER_PATTERN = re.compile(r"^[^\W\d]\w*(?:\.[^\W\d]\w*)*$", re.UNICODE)
_WORD_PATTERN = re.compile(r"[^\W_]+(?:[_-][^\W_]+)*", re.UNICODE)

_STOP_TERMS = frozenset(
    {
        "a",
        "an",
        "and",
        "as",
        "da",
        "das",
        "de",
        "do",
        "dos",
        "e",
        "em",
        "for",
        "in",
        "o",
        "os",
        "para",
        "por",
        "the",
        "to",
        "um",
        "uma",
    }
)
_OPERATION_ALIASES = {
    "add": "add",
    "adicionar": "add",
    "analyze": "analyze",
    "analisar": "analyze",
    "corrija": "fix",
    "corrigir": "fix",
    "create": "create",
    "criar": "create",
    "crie": "create",
    "document": "document",
    "documentar": "document",
    "explain": "explain",
    "explique": "explain",
    "fix": "fix",
    "modify": "modify",
    "modificar": "modify",
    "refactor": "refactor",
    "refatorar": "refactor",
    "remove": "remove",
    "remover": "remove",
    "rename": "rename",
    "renomear": "rename",
    "renomeie": "rename",
    "test": "test",
    "testar": "test",
}


class QueryTermKind(StrEnum):
    """Kinds of deterministic search signals extracted from a task."""

    PATH = "path"
    FILENAME = "filename"
    SYMBOL = "symbol"
    KEYWORD = "keyword"
    QUOTED_IDENTIFIER = "quoted_identifier"
    OPERATION = "operation"


@dataclass(frozen=True, slots=True)
class QueryTerm:
    """Original task spelling paired with a normalized comparison form."""

    original: str
    normalized: str
    kind: QueryTermKind

    def __post_init__(self) -> None:
        if not self.original.strip():
            raise ValueError("Query term original value must not be empty")
        if not self.normalized.strip():
            raise ValueError("Query term normalized value must not be empty")
        if not isinstance(self.kind, QueryTermKind):
            raise TypeError("kind must be a QueryTermKind")


@dataclass(frozen=True, slots=True)
class NormalizedTaskQuery:
    """Immutable signals derived from one Task Specification."""

    task_id: TaskId
    original_text: str
    normalized_text: str
    terms: tuple[QueryTerm, ...]
    explicit_paths: tuple[str, ...] = ()
    filenames: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    quoted_identifiers: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    operation_hints: tuple[str, ...] = ()
    normalizer_version: str = TASK_QUERY_NORMALIZER_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.task_id, TaskId):
            raise TypeError("task_id must be a TaskId")
        if not self.original_text.strip():
            raise ValueError("original_text must not be empty")
        if not self.normalized_text.strip():
            raise ValueError("normalized_text must not be empty")
        terms = tuple(self.terms)
        if any(not isinstance(term, QueryTerm) for term in terms):
            raise TypeError("terms must contain QueryTerm values")
        for field_name in (
            "explicit_paths",
            "filenames",
            "symbols",
            "quoted_identifiers",
            "keywords",
            "operation_hints",
        ):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} must contain non-empty strings")
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} must not contain duplicates")
            object.__setattr__(self, field_name, values)
        if not self.normalizer_version.strip():
            raise ValueError("normalizer_version must not be empty")
        object.__setattr__(self, "terms", terms)


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _normalize_path(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value.strip()).replace("\\", "/").rstrip(".,;:!?")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _deduplicate(values: list[str], *, normalized: bool = False) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _normalize(value) if normalized else value
        if key not in seen:
            seen.add(key)
            result.append(value)
    return tuple(result)


def _quoted_values(text: str) -> tuple[str, ...]:
    return tuple(
        next(value for value in match.groups() if value is not None)
        for match in _QUOTED_PATTERN.finditer(text)
    )


def _identifier_parts(value: str) -> tuple[str, ...]:
    parts: list[str] = []
    for segment in re.split(r"[._\-\s]+", value):
        start = 0
        for position in range(1, len(segment)):
            if segment[position].isupper() and (
                segment[position - 1].islower() or segment[position - 1].isdigit()
            ):
                parts.append(_normalize(segment[start:position]))
                start = position
        if segment:
            parts.append(_normalize(segment[start:]))
    return tuple(parts)


@dataclass(frozen=True, slots=True)
class TaskQueryNormalizer:
    """Extract conservative, explainable signals from task text."""

    version: str = TASK_QUERY_NORMALIZER_VERSION

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty")

    def normalize(self, task: TaskSpecification) -> NormalizedTaskQuery:
        """Normalize a task while preserving its original instruction exactly."""
        if not isinstance(task, TaskSpecification):
            raise TypeError("task must be a TaskSpecification")
        text = task.task_text
        quoted = _quoted_values(text)
        paths = [_normalize_path(match.group()) for match in _PATH_PATTERN.finditer(text)]
        filenames = [match.group().rstrip(".,;:!?") for match in _FILENAME_PATTERN.finditer(text)]
        symbols = [match.group() for match in _QUALIFIED_SYMBOL_PATTERN.finditer(text)]

        for value in quoted:
            normalized_path = _normalize_path(value)
            if "/" in normalized_path or _FILENAME_PATTERN.fullmatch(normalized_path):
                if "/" in normalized_path:
                    paths.append(normalized_path)
                filename = normalized_path.rsplit("/", 1)[-1]
                if _FILENAME_PATTERN.fullmatch(filename):
                    filenames.append(filename)
            elif _IDENTIFIER_PATTERN.fullmatch(value):
                symbols.append(value)

        metadata = dict(task.metadata)
        for key in ("artifact_reference", "path", "source_path"):
            metadata_value = metadata.get(key)
            if isinstance(metadata_value, str) and metadata_value.strip():
                normalized_path = _normalize_path(metadata_value)
                paths.append(normalized_path)
                filenames.append(normalized_path.rsplit("/", 1)[-1])
        for key in ("symbol", "symbol_reference"):
            metadata_value = metadata.get(key)
            if isinstance(metadata_value, str) and metadata_value.strip():
                symbols.append(metadata_value)

        paths_tuple = _deduplicate(paths, normalized=True)
        filenames_tuple = _deduplicate(filenames, normalized=True)
        symbols_tuple = _deduplicate(symbols, normalized=True)
        quoted_identifiers = _deduplicate(
            [
                value
                for value in quoted
                if _IDENTIFIER_PATTERN.fullmatch(value)
                or "/" in _normalize_path(value)
                or _FILENAME_PATTERN.fullmatch(value)
            ],
            normalized=True,
        )

        word_values = tuple(match.group() for match in _WORD_PATTERN.finditer(text))
        operation_hints: list[str] = []
        if task.task_kind is not TaskKind.UNKNOWN:
            operation_hints.append(task.task_kind.value)
        operation_hints.extend(
            _OPERATION_ALIASES[normalized]
            for word in word_values
            if (normalized := _normalize(word)) in _OPERATION_ALIASES
        )
        operation_hints_tuple = _deduplicate(operation_hints)

        protected_parts = {
            part
            for value in (*paths_tuple, *filenames_tuple, *symbols_tuple)
            for part in _identifier_parts(value)
        }
        keywords: list[str] = []
        for word in word_values:
            keywords.extend(_identifier_parts(word))
        keywords_tuple = _deduplicate(
            [
                keyword
                for keyword in keywords
                if len(keyword) > 1
                and (keyword not in _STOP_TERMS or keyword in protected_parts)
                and keyword not in _OPERATION_ALIASES
            ]
        )

        terms: list[QueryTerm] = []
        terms.extend(QueryTerm(path, _normalize(path), QueryTermKind.PATH) for path in paths_tuple)
        terms.extend(
            QueryTerm(filename, _normalize(filename), QueryTermKind.FILENAME)
            for filename in filenames_tuple
        )
        terms.extend(
            QueryTerm(symbol, _normalize(symbol), QueryTermKind.SYMBOL) for symbol in symbols_tuple
        )
        terms.extend(
            QueryTerm(value, _normalize(value), QueryTermKind.QUOTED_IDENTIFIER)
            for value in quoted_identifiers
        )
        terms.extend(
            QueryTerm(keyword, keyword, QueryTermKind.KEYWORD) for keyword in keywords_tuple
        )
        terms.extend(
            QueryTerm(operation, operation, QueryTermKind.OPERATION)
            for operation in operation_hints_tuple
        )
        normalized_text = " ".join(_normalize(word) for word in word_values)
        return NormalizedTaskQuery(
            task.task_id,
            text,
            normalized_text,
            tuple(terms),
            paths_tuple,
            filenames_tuple,
            symbols_tuple,
            quoted_identifiers,
            keywords_tuple,
            operation_hints_tuple,
            self.version,
        )
