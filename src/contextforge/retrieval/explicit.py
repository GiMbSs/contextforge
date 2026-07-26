"""Deterministic resolution of explicit task references."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.indexer import IndexedArtifact, ProjectIndex, Symbol
from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    RetrievalCandidate,
    RetrievalEvidence,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.retrieval.query import NormalizedTaskQuery

EXPLICIT_REFERENCE_STRATEGY_VERSION = "explicit-reference-v1"
_FILE_EXTENSIONS = frozenset(
    {
        "c",
        "cc",
        "cfg",
        "cpp",
        "cs",
        "css",
        "go",
        "h",
        "hpp",
        "html",
        "ini",
        "java",
        "js",
        "json",
        "jsx",
        "md",
        "py",
        "rb",
        "rs",
        "sh",
        "sql",
        "toml",
        "ts",
        "tsx",
        "txt",
        "xml",
        "yaml",
        "yml",
    }
)


class ExplicitReferenceKind(StrEnum):
    """Kinds of task references resolved directly against the index."""

    PATH = "path"
    FILENAME = "filename"
    SYMBOL = "symbol"


class ExplicitResolutionState(StrEnum):
    """Observable outcome of resolving one explicit reference."""

    EXACT = "exact"
    UNIQUE_NORMALIZED = "unique_normalized"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class ExplicitReferenceResolution:
    """Resolution trace for one reference from the normalized task."""

    reference: str
    kind: ExplicitReferenceKind
    state: ExplicitResolutionState
    candidate_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.reference.strip():
            raise ValueError("reference must not be empty")
        if not isinstance(self.kind, ExplicitReferenceKind):
            raise TypeError("kind must be an ExplicitReferenceKind")
        if not isinstance(self.state, ExplicitResolutionState):
            raise TypeError("state must be an ExplicitResolutionState")
        candidate_ids = tuple(self.candidate_ids)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate_ids must not contain duplicates")
        if any(
            not value or any(character.isspace() for character in value) for value in candidate_ids
        ):
            raise ValueError("candidate_ids must contain non-empty identifiers")
        if self.state is ExplicitResolutionState.NOT_FOUND and candidate_ids:
            raise ValueError("a not-found resolution cannot contain candidates")
        if self.state is not ExplicitResolutionState.NOT_FOUND and not candidate_ids:
            raise ValueError("a resolved reference must contain candidates")
        object.__setattr__(self, "candidate_ids", candidate_ids)


@dataclass(frozen=True, slots=True)
class ExplicitReferenceResult:
    """Candidates, traces, and diagnostics produced by explicit resolution."""

    candidates: tuple[RetrievalCandidate, ...]
    resolutions: tuple[ExplicitReferenceResolution, ...]
    diagnostics: DiagnosticCollection
    strategy_version: str = EXPLICIT_REFERENCE_STRATEGY_VERSION

    def __post_init__(self) -> None:
        candidates = tuple(self.candidates)
        resolutions = tuple(self.resolutions)
        if any(not isinstance(candidate, RetrievalCandidate) for candidate in candidates):
            raise TypeError("candidates must contain RetrievalCandidate values")
        if any(
            not isinstance(resolution, ExplicitReferenceResolution) for resolution in resolutions
        ):
            raise TypeError("resolutions must contain ExplicitReferenceResolution values")
        candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate identifiers must be unique")
        if not isinstance(self.diagnostics, DiagnosticCollection):
            raise TypeError("diagnostics must be a DiagnosticCollection")
        if not self.strategy_version.strip():
            raise ValueError("strategy_version must not be empty")
        object.__setattr__(self, "candidates", candidates)
        object.__setattr__(self, "resolutions", resolutions)


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\\", "/").casefold()


def _looks_like_filename(value: str) -> bool:
    return value.rpartition(".")[2].casefold() in _FILE_EXTENSIONS


def _candidate_id(kind: ExplicitReferenceKind, entity_id: str) -> str:
    digest = hashlib.sha256(f"{kind.value}\0{entity_id}".encode()).hexdigest()[:20]
    return f"explicit_{kind.value}_{digest}"


def _diagnostic(
    code: str,
    reference: str,
    kind: ExplicitReferenceKind,
    message: str,
) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        message,
        "context-retriever",
        DiagnosticLocation(reference),
        metadata=(("reference_kind", kind.value),),
    )


def _artifact_candidate(
    artifact: IndexedArtifact,
    reference: str,
    kind: ExplicitReferenceKind,
    *,
    ambiguous: bool,
) -> RetrievalCandidate:
    candidate_id = _candidate_id(kind, str(artifact.artifact_id))
    reason = (
        SelectionReason.DEFERRED_AMBIGUITY
        if ambiguous
        else (
            SelectionReason.EXACT_PATH_MATCH
            if kind is ExplicitReferenceKind.PATH
            else SelectionReason.EXPLICIT_PATH_REFERENCE
        )
    )
    evidence = RetrievalEvidence(
        f"explicit-{kind.value}-reference",
        EXPLICIT_REFERENCE_STRATEGY_VERSION,
        f"{reference} -> {artifact.path or artifact.artifact_id}",
        1.0,
    )
    rationale = SelectionRationale(
        candidate_id,
        SelectionDecision.DEFERRED if ambiguous else SelectionDecision.SELECTED,
        reason,
        (evidence,),
        score=1.0,
        explanation=(
            "Explicit reference is ambiguous."
            if ambiguous
            else "Explicit reference resolved directly."
        ),
    )
    return RetrievalCandidate(
        candidate_id,
        CandidateType.FULL_ARTIFACT,
        artifact.path.value if artifact.path is not None else str(artifact.artifact_id),
        f"artifact:{artifact.artifact_id}",
        (evidence,),
        CandidateEligibility.ELIGIBLE,
        CandidateOutcome.DEFERRED if ambiguous else CandidateOutcome.SELECTED,
        0,
        artifact_id=artifact.artifact_id,
        rationale=rationale,
    )


def _symbol_candidate(
    symbol: Symbol,
    reference: str,
    *,
    ambiguous: bool,
) -> RetrievalCandidate:
    candidate_id = _candidate_id(ExplicitReferenceKind.SYMBOL, symbol.symbol_id)
    reason = SelectionReason.DEFERRED_AMBIGUITY if ambiguous else SelectionReason.EXACT_SYMBOL_MATCH
    evidence = RetrievalEvidence(
        "explicit-symbol-reference",
        EXPLICIT_REFERENCE_STRATEGY_VERSION,
        f"{reference} -> {symbol.qualified_name or symbol.name}",
        1.0,
    )
    rationale = SelectionRationale(
        candidate_id,
        SelectionDecision.DEFERRED if ambiguous else SelectionDecision.SELECTED,
        reason,
        (evidence,),
        score=1.0,
        explanation=(
            "Explicit symbol reference is ambiguous."
            if ambiguous
            else "Explicit symbol reference resolved directly."
        ),
    )
    return RetrievalCandidate(
        candidate_id,
        CandidateType.SYMBOL_DEFINITION,
        symbol.qualified_name or symbol.name,
        f"symbol:{symbol.symbol_id}",
        (evidence,),
        CandidateEligibility.ELIGIBLE,
        CandidateOutcome.DEFERRED if ambiguous else CandidateOutcome.SELECTED,
        0,
        artifact_id=symbol.artifact_id,
        location=symbol.location,
        rationale=rationale,
    )


@dataclass(frozen=True, slots=True)
class ExplicitReferenceStrategy:
    """Resolve only direct path, filename, and symbol references."""

    version: str = EXPLICIT_REFERENCE_STRATEGY_VERSION

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty")

    def resolve(
        self,
        query: NormalizedTaskQuery,
        project_index: ProjectIndex,
    ) -> ExplicitReferenceResult:
        """Resolve explicit query signals without inference or index mutation."""
        if not isinstance(query, NormalizedTaskQuery):
            raise TypeError("query must be a NormalizedTaskQuery")
        if not isinstance(project_index, ProjectIndex):
            raise TypeError("project_index must be a ProjectIndex")

        candidates: dict[str, RetrievalCandidate] = {}
        resolutions: list[ExplicitReferenceResolution] = []
        diagnostics: list[Diagnostic] = []

        for reference in query.explicit_paths:
            exact = tuple(
                artifact
                for artifact in project_index.indexed_artifacts
                if artifact.path is not None and artifact.path.value == reference
            )
            matches = exact or tuple(
                artifact
                for artifact in project_index.indexed_artifacts
                if artifact.path is not None
                and _normalized(artifact.path.value) == _normalized(reference)
            )
            self._record_artifacts(
                reference,
                ExplicitReferenceKind.PATH,
                matches,
                candidates,
                resolutions,
                diagnostics,
                exact=bool(exact),
            )

        path_filenames = {_normalized(path.rsplit("/", 1)[-1]) for path in query.explicit_paths}
        for reference in query.filenames:
            if _normalized(reference) in path_filenames:
                continue
            matches = tuple(
                artifact
                for artifact in project_index.indexed_artifacts
                if artifact.path is not None
                and _normalized(artifact.path.parts[-1]) == _normalized(reference)
            )
            self._record_artifacts(
                reference,
                ExplicitReferenceKind.FILENAME,
                matches,
                candidates,
                resolutions,
                diagnostics,
                exact=True,
            )

        path_values = {_normalized(path) for path in query.explicit_paths} | path_filenames
        for reference in query.symbols:
            if _normalized(reference) in path_values or (
                reference in query.filenames and _looks_like_filename(reference)
            ):
                continue
            symbol_matches = tuple(
                symbol
                for symbol in project_index.symbols
                if _normalized(symbol.name) == _normalized(reference)
                or (
                    symbol.qualified_name is not None
                    and _normalized(symbol.qualified_name) == _normalized(reference)
                )
            )
            ambiguous = len(symbol_matches) > 1
            resolved = tuple(
                _symbol_candidate(symbol, reference, ambiguous=ambiguous)
                for symbol in symbol_matches
            )
            for candidate in resolved:
                candidates.setdefault(candidate.candidate_id, candidate)
            self._record_resolution(
                reference,
                ExplicitReferenceKind.SYMBOL,
                tuple(candidate.candidate_id for candidate in resolved),
                resolutions,
                diagnostics,
                exact=any(
                    symbol.name == reference or symbol.qualified_name == reference
                    for symbol in symbol_matches
                ),
            )

        return ExplicitReferenceResult(
            tuple(candidates.values()),
            tuple(resolutions),
            DiagnosticCollection(tuple(diagnostics)),
            self.version,
        )

    @staticmethod
    def _record_artifacts(
        reference: str,
        kind: ExplicitReferenceKind,
        matches: tuple[IndexedArtifact, ...],
        candidates: dict[str, RetrievalCandidate],
        resolutions: list[ExplicitReferenceResolution],
        diagnostics: list[Diagnostic],
        *,
        exact: bool,
    ) -> None:
        ambiguous = len(matches) > 1
        resolved = tuple(
            _artifact_candidate(artifact, reference, kind, ambiguous=ambiguous)
            for artifact in matches
        )
        for candidate in resolved:
            candidates.setdefault(candidate.candidate_id, candidate)
        ExplicitReferenceStrategy._record_resolution(
            reference,
            kind,
            tuple(candidate.candidate_id for candidate in resolved),
            resolutions,
            diagnostics,
            exact=exact,
        )

    @staticmethod
    def _record_resolution(
        reference: str,
        kind: ExplicitReferenceKind,
        candidate_ids: tuple[str, ...],
        resolutions: list[ExplicitReferenceResolution],
        diagnostics: list[Diagnostic],
        *,
        exact: bool,
    ) -> None:
        if not candidate_ids:
            state = ExplicitResolutionState.NOT_FOUND
            diagnostics.append(
                _diagnostic(
                    "RETRIEVAL_REFERENCE_NOT_FOUND",
                    reference,
                    kind,
                    f"Explicit {kind.value} reference could not be resolved: {reference}",
                )
            )
        elif len(candidate_ids) > 1:
            state = ExplicitResolutionState.AMBIGUOUS
            diagnostics.append(
                _diagnostic(
                    "RETRIEVAL_REFERENCE_AMBIGUOUS",
                    reference,
                    kind,
                    f"Explicit {kind.value} reference is ambiguous: {reference}",
                )
            )
        else:
            state = (
                ExplicitResolutionState.EXACT
                if exact
                else ExplicitResolutionState.UNIQUE_NORMALIZED
            )
        resolutions.append(ExplicitReferenceResolution(reference, kind, state, candidate_ids))
