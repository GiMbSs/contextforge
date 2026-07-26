"""Tests for CF-014 increment I031 deterministic task-query normalization."""

from contextforge.domain import (
    RequestedOutput,
    TaskKind,
    TaskSpecification,
    new_task_id,
)
from contextforge.retrieval import QueryTermKind, TaskQueryNormalizer


def make_task(
    text: str,
    kind: TaskKind = TaskKind.UNKNOWN,
    metadata: tuple[tuple[str, object], ...] = (),
) -> TaskSpecification:
    return TaskSpecification(
        new_task_id(),
        text,
        kind,
        RequestedOutput.ANALYSIS,
        metadata=metadata,
    )


def test_original_instruction_is_preserved_exactly() -> None:
    original = "  Explique `ContextBundle`.\r\nNão altere café.py.  "

    query = TaskQueryNormalizer().normalize(make_task(original))

    assert query.original_text == original
    assert query.normalized_text


def test_extracts_explicit_paths_and_filenames_deterministically() -> None:
    task = make_task(
        r"Fix src/contextforge/retrieval/query.py and tests\test_query.py; inspect query.py."
    )

    query = TaskQueryNormalizer().normalize(task)

    assert query.explicit_paths == (
        "src/contextforge/retrieval/query.py",
        "tests/test_query.py",
    )
    assert query.filenames == ("query.py", "test_query.py")
    assert any(term.kind is QueryTermKind.PATH for term in query.terms)


def test_extracts_quoted_and_qualified_symbols_without_rewriting_case() -> None:
    task = make_task("Explain `ContextBundle` and ProjectIndex.find_symbols.")

    query = TaskQueryNormalizer().normalize(task)

    assert query.symbols == ("ProjectIndex.find_symbols", "ContextBundle")
    assert "ContextBundle" in query.quoted_identifiers
    symbol_terms = tuple(term for term in query.terms if term.kind is QueryTermKind.SYMBOL)
    assert tuple(term.normalized for term in symbol_terms) == (
        "projectindex.find_symbols",
        "contextbundle",
    )


def test_unicode_and_identifier_components_become_keywords() -> None:
    task = make_task("Analise CaféService e normalize_user-name com segurança.")

    query = TaskQueryNormalizer().normalize(task)

    assert "café" in query.keywords
    assert "service" in query.keywords
    assert "normalize" in query.keywords
    assert "user" in query.keywords
    assert "segurança" in query.keywords


def test_operation_hints_combine_task_kind_and_explicit_words() -> None:
    task = make_task(
        "Rename the adapter, then explain the change.",
        TaskKind.MODIFY,
    )

    query = TaskQueryNormalizer().normalize(task)

    assert query.operation_hints == ("modify", "rename", "explain")


def test_metadata_references_are_preserved_as_explicit_signals() -> None:
    task = make_task(
        "Update the requested target.",
        metadata=(
            ("artifact_reference", "src/main.py"),
            ("symbol_reference", "Service.run"),
        ),
    )

    query = TaskQueryNormalizer().normalize(task)

    assert query.explicit_paths == ("src/main.py",)
    assert query.filenames == ("main.py",)
    assert query.symbols == ("Service.run",)


def test_repeated_normalization_is_equal_and_deduplicated() -> None:
    task = make_task("Explain `main.py`, main.py, and `main.py`.")
    normalizer = TaskQueryNormalizer()

    first = normalizer.normalize(task)
    second = normalizer.normalize(task)

    assert first == second
    assert first.filenames == ("main.py",)
    assert len(first.terms) == len(
        {(term.original, term.normalized, term.kind) for term in first.terms}
    )
