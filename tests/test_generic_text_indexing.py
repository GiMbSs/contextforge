"""Tests for CF-014 increment I023 generic text indexing."""

from contextforge.domain import ArtifactPath, new_artifact_id, new_project_id
from contextforge.indexer import GenericTextIndexConfig, GenericTextIndexer
from contextforge.scanner import (
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
)


def make_artifact(path: str = "notes.txt") -> ProjectArtifact:
    return ProjectArtifact(
        new_artifact_id(),
        new_project_id(),
        ArtifactPath(path),
        ArtifactKind.DOCUMENTATION,
        (ArtifactClassification.DOCUMENTATION,),
    )


def test_short_text_produces_deterministic_line_units() -> None:
    artifact = make_artifact()
    indexer = GenericTextIndexer()
    content = b"first line\nsecond line\n"

    first = indexer.index_artifact(artifact, content)
    second = indexer.index_artifact(artifact, content)

    assert tuple(unit.text for unit in first.search_units) == ("first line", "second line")
    assert first == second
    assert first.diagnostics.diagnostics == ()


def test_long_text_is_divided_by_configured_utf8_byte_limit() -> None:
    artifact = make_artifact()
    indexer = GenericTextIndexer(GenericTextIndexConfig(max_search_unit_bytes=8))

    result = indexer.index_artifact(artifact, b"abcdefghijklmnopqrst")

    assert tuple(unit.text for unit in result.search_units) == ("abcdefgh", "ijklmnop", "qrst")
    assert all(len(unit.text.encode("utf-8")) <= 8 for unit in result.search_units)
    assert tuple(unit.location.start_column for unit in result.search_units) == (1, 9, 17)
    assert tuple(unit.location.end_column for unit in result.search_units) == (8, 16, 20)


def test_unicode_is_never_split_inside_a_utf8_sequence() -> None:
    artifact = make_artifact()
    indexer = GenericTextIndexer(GenericTextIndexConfig(max_search_unit_bytes=5))

    result = indexer.index_artifact(artifact, "áéíóú".encode())

    assert tuple(unit.text for unit in result.search_units) == ("áé", "íó", "ú")
    assert "".join(unit.text for unit in result.search_units) == "áéíóú"
    assert all(len(unit.text.encode()) <= 5 for unit in result.search_units)


def test_empty_file_produces_no_search_units() -> None:
    result = GenericTextIndexer().index_artifact(make_artifact(), b"")

    assert result.search_units == ()
    assert result.indexed_bytes == 0
    assert not result.truncated


def test_large_line_preserves_exact_line_and_column_ranges() -> None:
    artifact = make_artifact()
    indexer = GenericTextIndexer(GenericTextIndexConfig(max_search_unit_bytes=4))

    result = indexer.index_artifact(artifact, b"ab\nabcdefghij\n")

    assert tuple(unit.text for unit in result.search_units) == ("ab", "abcd", "efgh", "ij")
    assert tuple(
        (
            unit.location.start_line,
            unit.location.start_column,
            unit.location.end_line,
            unit.location.end_column,
        )
        for unit in result.search_units
    ) == ((1, 1, 1, 2), (2, 1, 2, 4), (2, 5, 2, 8), (2, 9, 2, 10))


def test_unsupported_encoding_produces_diagnostic_without_units() -> None:
    result = GenericTextIndexer().index_artifact(
        make_artifact("legacy.txt"),
        b"\xff\xfeinvalid",
    )

    assert result.search_units == ()
    assert {str(item.code) for item in result.diagnostics} == {"INDEX_UNSUPPORTED_ENCODING"}
    assert result.diagnostics.diagnostics[0].location is not None
    assert result.diagnostics.diagnostics[0].location.reference == "legacy.txt"


def test_content_limit_uses_valid_utf8_prefix_and_reports_truncation() -> None:
    artifact = make_artifact()
    indexer = GenericTextIndexer(
        GenericTextIndexConfig(
            max_content_bytes=5,
            max_search_unit_bytes=8,
        )
    )

    result = indexer.index_artifact(artifact, "áéí".encode())

    assert tuple(unit.text for unit in result.search_units) == ("áé",)
    assert result.indexed_bytes == 4
    assert result.truncated
    assert {str(item.code) for item in result.diagnostics} == {"INDEX_CONTENT_LIMIT_REACHED"}
