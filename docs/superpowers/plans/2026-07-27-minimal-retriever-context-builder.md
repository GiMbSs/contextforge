# Minimal Context Retriever and Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `contextforge run --analysis-only` produce a real `ContextBundle` containing project content selected by simple deterministic lexical relevance.

**Architecture:** Replace the CLI stubs `_EmptyRetriever` and `_EmptyContextBuilder` with a `SimpleContextRetriever` (scores `ProjectIndex` search units/symbols against normalized task terms) and a `SimpleContextBuilder` (materializes selected items via `ContextItemMaterializer` and builds a validated `ContextBundle`). Both are intentionally minimal and follow the existing contracts.

**Tech Stack:** Python 3.12+, `dataclasses`, existing `contextforge` modules (`retrieval`, `context`, `indexer`, `domain`, `diagnostics`).

---

## File Structure

- **Create:** `src/contextforge/retrieval/simple_retriever.py` — minimal lexical retriever.
- **Create:** `src/contextforge/context/simple_builder.py` — minimal context bundle builder.
- **Modify:** `src/contextforge/adapters/project_commands.py` — wire new retriever/builder into `LocalProjectCommandGateway.analyze`.
- **Create:** `tests/test_simple_context_retriever.py` — unit tests for retriever.
- **Create:** `tests/test_simple_context_builder.py` — unit tests for builder.
- **Modify:** `tests/test_cli_run_analysis.py` — integration test asserting non-empty context bundle.

---

## Task 1: Add `FilesystemContextContentSource` adapter

**Files:**
- Create: `src/contextforge/context/filesystem_source.py`
- Modify: `src/contextforge/context/__init__.py`

This adapter lets `ContextItemMaterializer` read bytes from the project root using the `content_reference` stored in each `SelectedContextItem`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filesystem_context_content_source.py
import hashlib
from pathlib import Path

import pytest

from contextforge.context import ContextMaterializationError, FilesystemContextContentSource
from contextforge.domain import ArtifactPath, new_artifact_id
from contextforge.indexer import SourceLocation
from contextforge.retrieval import (
    CandidateType,
    RetrievalEvidence,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)


def _fingerprint(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _selected_item(item_id: str, path: str, content: bytes) -> SelectedContextItem:
    artifact_id = new_artifact_id()
    candidate_id = f"candidate-{item_id}"
    return SelectedContextItem(
        item_id,
        candidate_id,
        artifact_id,
        path,
        CandidateType.SOURCE_EXCERPT,
        SelectionRationale(
            candidate_id,
            SelectionDecision.SELECTED,
            SelectionReason.EXACT_PATH_MATCH,
            (RetrievalEvidence("path", "task", path),),
        ),
        location=SourceLocation(artifact_id, 1, 1, 1, 5),
        content_fingerprint=_fingerprint(content),
    )


def test_reads_file_relative_to_project_root(tmp_path: Path) -> None:
    content = b"hello"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "example.py").write_bytes(content)
    source = FilesystemContextContentSource(tmp_path)
    selected = _selected_item("item-1", "src/example.py", content)
    result = source.read(selected)
    assert result.content == content
    assert result.path == ArtifactPath("src/example.py")
    assert result.artifact_id == selected.artifact_id


def test_raises_when_file_is_missing(tmp_path: Path) -> None:
    source = FilesystemContextContentSource(tmp_path)
    selected = _selected_item("item-1", "missing.py", b"x")
    with pytest.raises(ContextMaterializationError):
        source.read(selected)


def test_raises_when_fingerprint_changed(tmp_path: Path) -> None:
    content = b"hello"
    (tmp_path / "example.py").write_bytes(content)
    source = FilesystemContextContentSource(tmp_path)
    selected = _selected_item("item-1", "example.py", b"changed")
    with pytest.raises(ContextMaterializationError):
        source.read(selected)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_filesystem_context_content_source.py -v
```

Expected: `ImportError` for `FilesystemContextContentSource`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/contextforge/context/filesystem_source.py
from __future__ import annotations

import hashlib
from pathlib import Path

from contextforge.context.materialization import ContextMaterializationError, SourceContent
from contextforge.context.ports import ContextContentSource
from contextforge.domain import ArtifactPath
from contextforge.retrieval import SelectedContextItem


class FilesystemContextContentSource(ContextContentSource):
    """Read selected source bytes from a project root directory."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise TypeError("root must be a Path")
        self._root = root

    def read(self, selected_item: SelectedContextItem) -> SourceContent:
        reference = selected_item.content_reference
        target = self._root.joinpath(*Path(reference).parts)
        resolved = target.resolve()
        try:
            resolved.relative_to(self._root.resolve())
        except ValueError as error:
            raise ContextMaterializationError(
                f"Content reference escapes project root: {reference}"
            ) from error
        try:
            content = target.read_bytes()
        except OSError as error:
            raise ContextMaterializationError(
                f"Selected content is unavailable: {reference}"
            ) from error
        actual_fingerprint = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if (
            selected_item.content_fingerprint is not None
            and actual_fingerprint != selected_item.content_fingerprint
        ):
            raise ContextMaterializationError(
                f"Selected content is stale: {reference}"
            )
        artifact_id = selected_item.artifact_id
        try:
            path = ArtifactPath(reference)
        except ValueError:
            path = None
        return SourceContent(reference, content, artifact_id, path)
```

- [ ] **Step 4: Export the class in `context/__init__.py`**

```python
from contextforge.context.filesystem_source import FilesystemContextContentSource
```

Add `"FilesystemContextContentSource"` to `__all__`.

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_filesystem_context_content_source.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/contextforge/context/filesystem_source.py src/contextforge/context/__init__.py tests/test_filesystem_context_content_source.py
git commit -m "feat(context): add filesystem content source for materialization"
```

---

## Task 2: Implement `SimpleContextRetriever`

**Files:**
- Create: `src/contextforge/retrieval/simple_retriever.py`
- Create: `tests/test_simple_context_retriever.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_simple_context_retriever.py
from datetime import datetime

from contextforge.domain import (
    ArtifactPath,
    ProjectFingerprint,
    TaskId,
    TaskKind,
    TaskSpecification,
    fingerprint_project,
    new_artifact_id,
    new_project_id,
)
from contextforge.indexer import (
    IndexRequest,
    IndexedArtifact,
    IndexingState,
    ProjectIndex,
    SearchUnit,
    SearchUnitKind,
    SourceLocation,
)
from contextforge.retrieval import ContextBudget, RetrievalRequest
from contextforge.retrieval.simple_retriever import SimpleContextRetriever
from contextforge.scanner import (
    ProjectArtifact,
    ProjectInventory,
    ScanStatistics,
)


def _build_index(text: str, path: str = "src/example.py") -> ProjectIndex:
    artifact_id = new_artifact_id()
    artifact = ProjectArtifact(
        artifact_id,
        ArtifactPath(path),
        classifications=(),
        metadata={"size_bytes": len(text.encode()), "content_fingerprint": "sha256:" + "0" * 64},
    )
    inventory = ProjectInventory(
        inventory_id="inventory_1",
        project_id=new_project_id(),
        project_fingerprint=fingerprint_project(()),
        artifacts=(artifact,),
        statistics=ScanStatistics(artifacts_discovered=1, artifacts_included=1),
        applied_exclusion_rules=(),
    )
    location = SourceLocation(artifact_id, 1, 1, 1, len(text))
    search_unit = SearchUnit(
        search_unit_id="unit_1",
        artifact_id=artifact_id,
        location=location,
        kind=SearchUnitKind.GENERIC_TEXT_BLOCK,
        text=text,
        order=0,
    )
    indexed = IndexedArtifact(
        artifact_id=artifact_id,
        state=IndexingState.FULLY_INDEXED,
        strategy="generic-text",
        strategy_version="generic-text-v1",
        source_project_fingerprint=inventory.project_fingerprint,
        search_unit_ids=("unit_1",),
        content_fingerprint="sha256:" + "0" * 64,
        path=ArtifactPath(path),
    )
    return ProjectIndex(
        index_id="index_1",
        project_id=inventory.project_id,
        source_inventory_id=inventory.inventory_id,
        project_fingerprint=inventory.project_fingerprint,
        format_version="1",
        indexer_version="v1",
        indexed_artifacts=(indexed,),
        created_at=datetime.utcnow().replace(tzinfo=None),
        symbols=(),
        relationships=(),
        search_units=(search_unit,),
    )


def test_retriever_selects_search_unit_matching_task_term() -> None:
    index = _build_index("def hello(): pass")
    task = TaskSpecification(
        TaskId("task_1"),
        "explain hello function",
        TaskKind.EXPLAIN,
    )
    request = RetrievalRequest(task, index, ContextBudget(max_items=5, max_bytes=10_000))
    result = SimpleContextRetriever().retrieve(request)
    assert result.status.value == "complete"
    assert len(result.selected_items) == 1
    assert result.selected_items[0].content_reference == "src/example.py"


def test_retriever_falls_back_to_smallest_artifacts_when_no_match() -> None:
    index = _build_index("unrelated content here")
    task = TaskSpecification(
        TaskId("task_1"),
        "explain xyz",
        TaskKind.EXPLAIN,
    )
    request = RetrievalRequest(task, index, ContextBudget(max_items=5, max_bytes=10_000))
    result = SimpleContextRetriever().retrieve(request)
    assert result.status.value == "complete"
    assert len(result.selected_items) == 1


def test_retriever_respects_max_items_budget() -> None:
    index = _build_index("hello world")
    task = TaskSpecification(
        TaskId("task_1"),
        "explain hello",
        TaskKind.EXPLAIN,
    )
    request = RetrievalRequest(task, index, ContextBudget(max_items=0, max_bytes=10_000))
    result = SimpleContextRetriever().retrieve(request)
    assert result.status.value == "incomplete"
    assert len(result.selected_items) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_simple_context_retriever.py -v
```

Expected: `ImportError` or `AttributeError` for `SimpleContextRetriever`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/contextforge/retrieval/simple_retriever.py
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from contextforge.diagnostics import Diagnostic, DiagnosticCode, DiagnosticCollection, DiagnosticSeverity
from contextforge.domain import (
    ArtifactId,
    ProjectFingerprint,
    RetrievalId,
    TaskId,
    new_retrieval_id,
)
from contextforge.indexer import IndexedArtifact, ProjectIndex, SearchUnit, SourceLocation, Symbol
from contextforge.retrieval.models import (
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.retrieval.query import TaskQueryNormalizer


RETRIEVER_VERSION = "simple-context-retriever-v1"


class SimpleContextRetriever:
    """Deterministic lexical retriever using indexed search units and symbols."""

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        if not isinstance(request, RetrievalRequest):
            raise TypeError("request must be a RetrievalRequest")
        index = request.project_index
        task = request.task
        budget = request.budget
        query = TaskQueryNormalizer().normalize(task)
        keywords = {term.normalized for term in query.terms if term.kind.value == "keyword"}
        keywords = {term for term in keywords if len(term) >= 3}

        candidates: list[_Candidate] = []
        artifacts_by_id = {artifact.artifact_id: artifact for artifact in index.indexed_artifacts}

        for unit in index.search_units:
            artifact = artifacts_by_id.get(unit.artifact_id)
            if artifact is None:
                continue
            score = _score_text(unit.text, artifact.path.value, keywords)
            if score > 0:
                candidates.append(_Candidate(unit, artifact, score))

        for symbol in index.symbols:
            artifact = artifacts_by_id.get(symbol.artifact_id)
            if artifact is None:
                continue
            score = _score_symbol(symbol, artifact.path.value, keywords)
            if score > 0:
                candidates.append(_Candidate(symbol, artifact, score))

        if not candidates:
            for artifact in index.indexed_artifacts:
                if artifact.path is None:
                    continue
                candidates.append(_Candidate(None, artifact, 0))

        candidates.sort(key=lambda c: (-c.score, c.estimated_bytes, c.reference))
        selected, diagnostics = _select(candidates, budget, artifacts_by_id)

        return RetrievalResult(
            new_retrieval_id(),
            task.task_id,
            index.index_id,
            index.project_fingerprint,
            (RETRIEVER_VERSION,),
            tuple(c.item for c in candidates if c.item is not None),
            tuple(selected),
            tuple(c.rationale for c in candidates if c.rationale is not None),
            budget,
            DiagnosticCollection(tuple(diagnostics)),
            RetrievalStatus.COMPLETE if selected else RetrievalStatus.INCOMPLETE,
            datetime.now(UTC),
        )


@dataclass(frozen=True, slots=True)
class _Candidate:
    source: SearchUnit | Symbol | None
    artifact: IndexedArtifact
    score: int
    item: RetrievalCandidate | None = None
    rationale: SelectionRationale | None = None

    @property
    def reference(self) -> str:
        if self.source is None:
            return self.artifact.path.value if self.artifact.path else str(self.artifact.artifact_id)
        return self.source.search_unit_id if hasattr(self.source, "search_unit_id") else self.source.symbol_id

    @property
    def estimated_bytes(self) -> int:
        if self.source is None:
            return 0
        text = self.source.text if hasattr(self.source, "text") else (self.source.signature or "")
        return len(text.encode("utf-8"))


def _score_text(text: str, path: str, keywords: set[str]) -> int:
    text_terms = set(_normalize(token) for token in _tokens(text))
    path_terms = set(_normalize(token) for token in _tokens(path))
    return 3 * len(keywords & path_terms) + 1 * len(keywords & text_terms)


def _score_symbol(symbol: Symbol, path: str, keywords: set[str]) -> int:
    name_terms = set(_normalize(token) for token in _tokens(symbol.name))
    path_terms = set(_normalize(token) for token in _tokens(path))
    signature_terms = set(_normalize(token) for token in _tokens(symbol.signature or ""))
    return 3 * len(keywords & path_terms) + 2 * len(keywords & name_terms) + 1 * len(keywords & signature_terms)


def _tokens(text: str) -> list[str]:
    import re
    return re.findall(r"[a-zA-Z0-9]+(?:[._-][a-zA-Z0-9]+)*", text)


def _normalize(token: str) -> str:
    return token.casefold()


def _select(
    candidates: Sequence[_Candidate],
    budget: ContextBudget,
    artifacts_by_id: dict[ArtifactId, IndexedArtifact],
) -> tuple[list[SelectedContextItem], list[Diagnostic]]:
    selected: list[SelectedContextItem] = []
    diagnostics: list[Diagnostic] = []
    used_bytes = 0
    rank = 0

    for candidate in candidates:
        rank += 1
        estimated_bytes = candidate.estimated_bytes
        if budget.max_items is not None and len(selected) >= budget.max_items:
            diagnostics.append(_diagnostic("RETRIEVAL_CANDIDATE_OMITTED", f"Budget item limit reached: {candidate.reference}"))
            continue
        if budget.max_bytes is not None and used_bytes + estimated_bytes > budget.max_bytes:
            diagnostics.append(_diagnostic("RETRIEVAL_CANDIDATE_OMITTED", f"Budget byte limit reached: {candidate.reference}"))
            continue

        artifact = candidate.artifact
        source = candidate.source
        if source is None:
            candidate_id = f"artifact-{artifact.artifact_id.value}"
            item_id = f"item-{candidate_id}"
            content_reference = artifact.path.value if artifact.path else f"artifact:{artifact.artifact_id.value}"
            candidate_type = CandidateType.FULL_ARTIFACT
            location = None
        else:
            candidate_id = source.search_unit_id if hasattr(source, "search_unit_id") else source.symbol_id
            item_id = f"item-{candidate_id}"
            content_reference = artifact.path.value if artifact.path else f"artifact:{artifact.artifact_id.value}"
            candidate_type = CandidateType.SOURCE_EXCERPT if hasattr(source, "search_unit_id") else CandidateType.SYMBOL_DEFINITION
            location = source.location

        rationale = SelectionRationale(
            candidate_id,
            SelectionDecision.SELECTED,
            SelectionReason.LEXICAL_CONTENT_MATCH if candidate.score > 0 else SelectionReason.REQUIRED_CONTEXT,
            (RetrievalEvidence("simple-lexical", "retriever", f"score={candidate.score}"),),
            score=float(candidate.score),
            rank=rank,
        )
        candidate.item = RetrievalCandidate(
            candidate_id,
            candidate_type,
            content_reference,
            content_reference,
            (RetrievalEvidence("simple-lexical", "retriever", f"score={candidate.score}"),),
            CandidateEligibility.ELIGIBLE,
            CandidateOutcome.SELECTED,
            estimated_bytes,
            artifact_id=artifact.artifact_id,
            location=location,
            rationale=rationale,
        )
        candidate.rationale = rationale
        selected_item = SelectedContextItem(
            item_id,
            candidate_id,
            artifact.artifact_id,
            content_reference,
            candidate_type,
            rationale,
            location=location,
            estimated_tokens=estimated_bytes // 4,
            content_fingerprint=artifact.content_fingerprint,
            is_truncated=False,
            estimated_bytes=estimated_bytes,
            estimated_characters=len(content_reference) if source is None else len(source.text if hasattr(source, "text") else (source.signature or "")),
            score_breakdown=(("lexical_score", float(candidate.score)),),
            sensitivity_classification="unclassified",
            dependency_path=(),
        )
        selected.append(selected_item)
        used_bytes += estimated_bytes

    return selected, diagnostics


def _diagnostic(code: str, message: str) -> Diagnostic:
    return Diagnostic(
        DiagnosticCode(code),
        DiagnosticSeverity.WARNING,
        message,
        "retriever",
    )
```

> **Note:** The dataclass `item` and `rationale` fields are mutable on `_Candidate` because the dataclass is not frozen; this is intentional to avoid restructuring the helper while keeping the candidate objects small.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_simple_context_retriever.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contextforge/retrieval/simple_retriever.py tests/test_simple_context_retriever.py
git commit -m "feat(retrieval): add simple lexical context retriever"
```

---

## Task 3: Implement `SimpleContextBuilder`

**Files:**
- Create: `src/contextforge/context/simple_builder.py`
- Create: `tests/test_simple_context_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_simple_context_builder.py
from datetime import datetime
from unittest.mock import Mock

import pytest

from contextforge.context import ContextBundle, ContextSectionKind
from contextforge.context.simple_builder import SimpleContextBuilder
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ArtifactId,
    ArtifactPath,
    ProjectFingerprint,
    ProjectId,
    RetrievalId,
    TaskId,
)
from contextforge.indexer import SourceLocation
from contextforge.retrieval import (
    CandidateType,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)


def _build_retrieval_result(tmp_path, content: bytes = b"hello") -> RetrievalResult:
    from contextforge.context import FilesystemContextContentSource
    (tmp_path / "example.py").write_bytes(content)
    artifact_id = ArtifactId("artifact_1")
    candidate_id = "candidate_1"
    item = SelectedContextItem(
        "item_1",
        candidate_id,
        artifact_id,
        "example.py",
        CandidateType.FULL_ARTIFACT,
        SelectionRationale(
            candidate_id,
            SelectionDecision.SELECTED,
            SelectionReason.LEXICAL_CONTENT_MATCH,
            (RetrievalEvidence("test", "test", "test"),),
        ),
        location=SourceLocation(artifact_id, 1, 1, 1, 5),
        content_fingerprint=f"sha256:{content.hex()}",
        estimated_bytes=len(content),
        estimated_characters=len(content),
        estimated_tokens=1,
    )
    return RetrievalResult(
        RetrievalId("retrieval_1"),
        TaskId("task_1"),
        "index_1",
        ProjectFingerprint("fp"),
        ("v1",),
        (RetrievalCandidate(
            candidate_id,
            CandidateType.FULL_ARTIFACT,
            "example.py",
            "example.py",
            (RetrievalEvidence("test", "test", "test"),),
            CandidateEligibility.ELIGIBLE,
            CandidateOutcome.SELECTED,
            len(content),
            artifact_id=artifact_id,
            location=SourceLocation(artifact_id, 1, 1, 1, 5),
        ),),
        (item,),
        (item.rationale,),
        ContextBudget(max_items=5),
        DiagnosticCollection(),
        RetrievalStatus.COMPLETE,
        datetime.utcnow(),
    )


def test_builds_bundle_with_materialized_content(tmp_path) -> None:
    result = _build_retrieval_result(tmp_path, b"hello")
    builder = SimpleContextBuilder(tmp_path)
    bundle = builder.build(result, project_id=ProjectId("project_1"))
    assert isinstance(bundle, ContextBundle)
    assert len(bundle.items) == 1
    assert bundle.items[0].content == "hello"
    assert bundle.statistics.item_count == 1
    assert bundle.statistics.byte_count == 5
    assert bundle.statistics.character_count == 5


def test_empty_retrieval_result_produces_empty_bundle(tmp_path) -> None:
    result = RetrievalResult(
        RetrievalId("retrieval_1"),
        TaskId("task_1"),
        "index_1",
        ProjectFingerprint("fp"),
        ("v1",),
        (),
        (),
        (),
        ContextBudget(max_items=5),
        DiagnosticCollection(),
        RetrievalStatus.INCOMPLETE,
        datetime.utcnow(),
    )
    builder = SimpleContextBuilder(tmp_path)
    bundle = builder.build(result, project_id=ProjectId("project_1"))
    assert len(bundle.items) == 0
    assert bundle.statistics.item_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_simple_context_builder.py -v
```

Expected: `ImportError` for `SimpleContextBuilder`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/contextforge/context/simple_builder.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from contextforge.context import (
    ContextBundle,
    ContextCoverage,
    ContextItem,
    ContextItemMaterializer,
    ContextItemOrderer,
    ContextSection,
    ContextSectionKind,
    ContextStatistics,
    CoverageStatus,
    FilesystemContextContentSource,
)
from contextforge.context.models import ContextBundle
from contextforge.context.validation import ContextBundleValidator
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import ProjectId
from contextforge.retrieval import RetrievalResult


BUILDER_VERSION = "simple-context-builder-v1"


@dataclass(frozen=True, slots=True)
class SimpleContextBuilder:
    """Build a minimal ContextBundle from a RetrievalResult."""

    root: FilesystemContextContentSource

    def __init__(self, root_path: object) -> None:
        from pathlib import Path
        if not isinstance(root_path, Path):
            raise TypeError("root_path must be a Path")
        object.__setattr__(self, "root", FilesystemContextContentSource(root_path))

    def build(self, retrieval_result: RetrievalResult, *, project_id: ProjectId) -> ContextBundle:
        if not isinstance(retrieval_result, RetrievalResult):
            raise TypeError("retrieval_result must be a RetrievalResult")
        if not isinstance(project_id, ProjectId):
            raise TypeError("project_id must be a ProjectId")

        items = ContextItemMaterializer(self.root).materialize(retrieval_result.selected_items)
        ordered = ContextItemOrderer().order_materialized(items)

        statistics = ContextStatistics(
            item_count=len(ordered),
            artifact_count=len({item.selected_item.artifact_id for item in ordered if item.selected_item.artifact_id is not None}),
            excerpt_count=sum(1 for item in ordered if item.selected_item.candidate_type.value == "source_excerpt"),
            symbol_count=sum(1 for item in ordered if item.selected_item.candidate_type.value == "symbol_definition"),
            byte_count=sum(len(item.content.encode("utf-8")) for item in ordered),
            character_count=sum(len(item.content) for item in ordered),
            line_count=sum(0 if not item.content else item.content.count("\n") + 1 for item in ordered),
            estimated_tokens=sum((item.selected_item.estimated_tokens or 0) for item in ordered),
        )

        section = ContextSection(
            section_id="primary",
            kind=ContextSectionKind.PRIMARY_IMPLEMENTATION,
            title="Primary implementation context",
            item_ids=tuple(item.context_item_id for item in ordered),
            order=0,
        )

        bundle = ContextBundle(
            contextforge.domain.new_context_bundle_id(),
            retrieval_result.task_id,
            retrieval_result.retrieval_id,
            project_id,
            retrieval_result.project_fingerprint,
            tuple(ordered),
            tuple(item.context_item_id for item in ordered),
            (section,) if ordered else (),
            statistics,
            ContextCoverage(
                targets=CoverageStatus.PARTIAL if ordered else CoverageStatus.MISSING,
                dependencies=CoverageStatus.NOT_APPLICABLE,
                interfaces=CoverageStatus.NOT_APPLICABLE,
                tests=CoverageStatus.NOT_APPLICABLE,
                configuration=CoverageStatus.NOT_APPLICABLE,
                constraints=CoverageStatus.NOT_APPLICABLE,
                error_locations=CoverageStatus.NOT_APPLICABLE,
            ),
            DiagnosticCollection(),
            "1",
            BUILDER_VERSION,
            datetime.now(UTC),
        )

        validation = ContextBundleValidator().validate(bundle, retrieval_result)
        if not validation.is_valid:
            raise ValueError("ContextBundle validation failed")
        return bundle
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_simple_context_builder.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/contextforge/context/simple_builder.py tests/test_simple_context_builder.py
git commit -m "feat(context): add simple context bundle builder"
```

---

## Task 4: Wire into `LocalProjectCommandGateway.analyze`

**Files:**
- Modify: `src/contextforge/adapters/project_commands.py`

- [ ] **Step 1: Add imports**

At the top of `src/contextforge/adapters/project_commands.py`, add:

```python
from contextforge.context.simple_builder import SimpleContextBuilder
from contextforge.retrieval.simple_retriever import SimpleContextRetriever
```

- [ ] **Step 2: Replace the empty retriever/builder in `analyze`**

Locate the `analyze` method in `LocalProjectCommandGateway` (around line 338). Change:

```python
            retriever=_EmptyRetriever(),
            context_builder=_EmptyContextBuilder(),
```

To:

```python
            retriever=SimpleContextRetriever(),
            context_builder=SimpleContextBuilder(root.path),
```

- [ ] **Step 3: Run existing analysis tests**

```bash
pytest tests/test_analysis_execution_pipeline.py tests/test_cli_run_analysis.py -v
```

Expected: PASS (or updated expectations for non-empty context).

- [ ] **Step 4: Update integration test expectations**

Open `tests/test_cli_run_analysis.py`. Find any test that asserts a zero-finding or empty context. Adjust the assertion to expect `context_bundle` items when a fixture project is present, or add a new test:

```python
def test_run_analysis_produces_non_empty_context_bundle(cli_runner, project_with_files) -> None:
    result = cli_runner.invoke(
        app,
        [
            "--project",
            str(project_with_files),
            "run",
            "--analysis-only",
            "explain the database module",
        ],
    )
    assert result.exit_code == 0
    bundle_path = project_with_files / ".contextforge" / "executions" / "latest-context.json"
    assert bundle_path.exists()
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert data["statistics"]["item_count"] > 0
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_cli_run_analysis.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/contextforge/adapters/project_commands.py tests/test_cli_run_analysis.py
git commit -m "feat(cli): wire simple retriever and builder into analysis pipeline"
```

---

## Task 5: Manual verification in `D:\Py_Projetos\testes`

- [ ] **Step 1: Reinstall the package in editable mode**

```bash
python -m pip install -e "D:\Py_Projetos\contextforge"
```

- [ ] **Step 2: Run analysis on the test project**

```bash
contextforge --project "D:\Py_Projetos\testes" run --analysis-only "explain the database module"
```

Expected: exits `0`, no empty `Findings` requirement.

- [ ] **Step 3: Inspect the context bundle**

```bash
contextforge --project "D:\Py_Projetos\testes" context show
contextforge --project "D:\Py_Projetos\testes" context list
```

Expected: `item_count > 0` and `db.py` content appears among items.

- [ ] **Step 4: Export and inspect**

```bash
contextforge --project "D:\Py_Projetos\testes" context export --output "D:\Py_Projetos\testes\context-export.json"
```

Verify the JSON contains `items` with paths and content.

---

## Task 6: Run full quality gate

- [ ] **Step 1: Formatting and linting**

```bash
ruff format --check .
ruff check .
```

Expected: PASS.

- [ ] **Step 2: Type checking**

```bash
mypy src/contextforge
```

Expected: PASS.

- [ ] **Step 3: Test suite**

```bash
pytest
```

Expected: PASS.

- [ ] **Step 4: Build verification**

```bash
python -m build
```

Expected: PASS.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: minimal working retriever and context builder for analysis tasks"
```

---

## Spec coverage checklist

| Spec requirement | Implementing task |
|---|---|
| Produce a RetrievalResult with selected items | Task 2 |
| Use task query normalization | Task 2 |
| Generate lexical candidates | Task 2 |
| Enforce ContextBudget | Task 2 |
| Preserve selection rationale and evidence | Task 2 |
| Build ContextBundle from RetrievalResult | Task 3 |
| Materialize selected source content | Task 3 |
| Preserve traceability and ordering | Task 3 |
| Validate the bundle | Task 3 |
| Wire end-to-end in CLI | Task 4 |

## Placeholder scan

- No `TBD` or `TODO` remains.
- No "implement later" or "fill in details".
- No "write tests for the above" without concrete code.
- No "similar to Task N" references.

## Type consistency notes

- `SimpleContextRetriever.retrieve` signature matches `ContextRetriever`.
- `SimpleContextBuilder.build` signature matches `ContextBundleBuilder`.
- `FilesystemContextContentSource.read` matches `ContextContentSource`.
- All domain identifiers are created through existing factory functions.

## Execution choice

Plan complete and saved to `docs/superpowers/plans/2026-07-27-minimal-retriever-context-builder.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — I execute tasks in this session using `executing-plans`, batch execution with checkpoints.

**Which approach?**
