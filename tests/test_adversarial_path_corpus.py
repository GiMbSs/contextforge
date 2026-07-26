"""Data-driven adversarial path hardening corpus."""

import json
from pathlib import Path
from typing import cast

import pytest

from contextforge.adapters.filesystem.patches import _safe_target
from contextforge.domain import ArtifactPath, ProjectFingerprint
from contextforge.patch import (
    PatchConflictValidationError,
    PatchConflictValidator,
    PatchConsistencyEvidence,
    PatchOperation,
    PatchPathValidationError,
    PatchPathValidator,
    ProposedChange,
)

CORPUS_PATH = Path(__file__).parent / "fixtures" / "adversarial_paths.json"
CORPUS = cast("dict[str, list[dict[str, object]]]", json.loads(CORPUS_PATH.read_text("utf-8")))
FINGERPRINT = ProjectFingerprint("project_sha256_" + "a" * 64)


@pytest.mark.parametrize(
    "case",
    CORPUS["lexical_cases"],
    ids=lambda case: str(case["category"]),
)
def test_lexical_adversarial_path_corpus(case: dict[str, object]) -> None:
    path = str(case["path"])
    expected_code = case.get("expected_code")
    if expected_code is None:
        validated = PatchPathValidator().validate(path, PatchOperation.CREATE)
        assert str(validated.source) == case["expected_path"]
        return

    with pytest.raises(PatchPathValidationError) as captured:
        PatchPathValidator().validate(path, PatchOperation.CREATE)

    assert str(captured.value.diagnostics[0].code) == expected_code


@pytest.mark.parametrize(
    "case",
    CORPUS["rename_cycles"],
    ids=lambda case: str(case["category"]),
)
def test_adversarial_rename_cycles_are_rejected_once(case: dict[str, object]) -> None:
    raw_renames = cast("list[list[str]]", case["renames"])
    changes = tuple(
        ProposedChange(
            f"rename-{index}",
            ArtifactPath(source),
            PatchOperation.RENAME,
            "Adversarial rename.",
            destination_path=ArtifactPath(destination),
        )
        for index, (source, destination) in enumerate(raw_renames)
    )
    paths = tuple(
        sorted({ArtifactPath(path) for rename in raw_renames for path in rename})
    )
    evidence = PatchConsistencyEvidence(paths, FINGERPRINT, FINGERPRINT)

    with pytest.raises(PatchConflictValidationError) as captured:
        PatchConflictValidator().validate(changes, evidence)

    codes = tuple(str(item.code) for item in captured.value.diagnostics)
    assert codes.count("PATCH_CONFLICT_RENAME_CYCLE") == 1


@pytest.mark.parametrize(
    "case",
    CORPUS["filesystem_cases"],
    ids=lambda case: str(case["category"]),
)
def test_filesystem_adversarial_path_cannot_escape_through_symlink(
    tmp_path: Path,
    case: dict[str, object],
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Directory symlinks are unavailable: {error}")

    with pytest.raises(OSError, match="outside project root"):
        _safe_target(tmp_path.resolve(), ArtifactPath(str(case["path"])))

    assert not (outside / "escape.txt").exists()
