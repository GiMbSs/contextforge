"""Performance baselines for CF-014 increment I094.

These tests do not enforce optimization targets. They collect repeatable
latency measurements for core ContextForge operations so that future work can
detect regressions or justify optimizations with data.

Each test runs a warm-up iteration, then measures the operation several times
and reports the median latency. The assertions only verify that the operation
completes successfully and reports a finite, non-negative duration.
"""

from __future__ import annotations

import hashlib
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contextforge.adapters.filesystem import LocalProjectScanner
from contextforge.configuration import ScannerConfig
from contextforge.context import (
    ContextBundle,
    ContextBundleSerializer,
    ContextCoverage,
    ContextItem,
    ContextItemMaterializer,
    ContextSection,
    ContextSectionKind,
    ContextStatistics,
    SourceContent,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ArtifactPath,
    ContentFingerprint,
    FingerprintOrdering,
    ProjectFingerprint,
    fingerprint_project,
    new_artifact_id,
    new_context_bundle_id,
    new_index_id,
    new_inference_request_id,
    new_inference_response_id,
    new_inventory_id,
    new_patch_proposal_id,
    new_project_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.domain.tasks import RequestedOutput, TaskKind, TaskSpecification
from contextforge.indexer import (
    DeterministicProjectIndexer,
    IndexedArtifact,
    IndexingState,
    IndexRequest,
    ProjectIndex,
)
from contextforge.patch import (
    PatchConsistencyEvidence,
    PatchOperation,
    PatchProposalMaterializer,
    PatchSourceArtifact,
    PatchSourceState,
    ProposedChange,
)
from contextforge.project import ProjectRoot, ProjectRootSource
from contextforge.prompt import (
    PromptMeasurer,
    PromptTemplateAssembler,
    analysis_response_contract,
)
from contextforge.retrieval import (
    BudgetSelectionResult,
    BudgetUsage,
    CandidateBudgetEstimate,
    CandidateEligibility,
    CandidateOutcome,
    CandidateType,
    ContextBudget,
    RetrievalCandidate,
    RetrievalEvidence,
    RetrievalRequest,
    RetrievalResultAssembler,
    RetrievalScoringModel,
    SelectedContextItem,
    SelectionDecision,
    SelectionRationale,
    SelectionReason,
)
from contextforge.scanner import (
    ArtifactAvailability,
    ArtifactClassification,
    ArtifactKind,
    ProjectArtifact,
    ProjectInventory,
    ScanRequest,
    ScanStatistics,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)
PROJECT_FINGERPRINT = ProjectFingerprint("project_sha256_" + "a" * 64)
CONTENT_FINGERPRINT = ContentFingerprint("content_sha256_" + "b" * 64)


def _median(samples: list[float]) -> float:
    return float(statistics.median(samples))


def _make_fixture_repository(root: Path, artifact_count: int) -> None:
    """Create a deterministic Python-only fixture repository."""
    for index in range(artifact_count):
        (root / f"module_{index:04d}.py").write_text(
            f"def function_{index}():\n    return {index}\n",
            encoding="utf-8",
        )


def _scan_request(root: Path) -> ScanRequest:
    return ScanRequest(
        new_project_id(),
        ProjectRoot(root.resolve(), ProjectRootSource.EXPLICIT),
        ScannerConfig(
            use_default_exclusions=False,
            exclude_patterns=("__pycache__",),
        ),
    )


def _content_fingerprint(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


@dataclass
class _InMemoryProjectSource:
    """ProjectSource backed by a content mapping."""

    content: dict[str, bytes]

    def read(self, artifact: ProjectArtifact) -> bytes:
        return self.content[artifact.path.value]


def _make_python_artifact(
    project_id: object,
    path: str,
    content: bytes,
) -> ProjectArtifact:
    artifact_id = new_artifact_id()
    return ProjectArtifact(
        artifact_id,
        project_id,
        ArtifactPath(path),
        ArtifactKind.SOURCE,
        (ArtifactClassification.SOURCE,),
        ArtifactAvailability.INCLUDED,
        (
            ("content_fingerprint", _content_fingerprint(content)),
            ("size_bytes", len(content)),
            ("detected_language", "python"),
            ("encoding", "utf-8"),
        ),
    )


def _make_inventory(
    project_id: object,
    artifacts: tuple[ProjectArtifact, ...],
) -> ProjectInventory:
    return ProjectInventory(
        new_inventory_id(),
        project_id,
        fingerprint_project(("baseline",), ordering=FingerprintOrdering.ORDERED),
        artifacts,
        ScanStatistics(
            artifacts_discovered=len(artifacts),
            artifacts_included=len(artifacts),
            total_bytes=sum(dict(artifact.metadata).get("size_bytes", 0) for artifact in artifacts),
        ),
        NOW,
        "scanner-v1",
    )


def _measure(operation: object, *, iterations: int = 5, warmup: int = 1) -> float:
    """Return median elapsed time in seconds for a callable operation."""
    for _ in range(warmup):
        operation()
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        operation()
        end = time.perf_counter()
        samples.append(end - start)
    return _median(samples)


# ---------------------------------------------------------------------------
# Scanner baselines
# ---------------------------------------------------------------------------


def test_baseline_scan_time_by_artifact_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Measure full scan latency as a function of artifact count."""
    counts = (10, 50, 100)
    scanner = LocalProjectScanner()
    results: list[tuple[int, float, int]] = []

    for count in counts:
        root = tmp_path / f"repo_{count}"
        root.mkdir()
        _make_fixture_repository(root, count)
        request = _scan_request(root)
        elapsed = _measure(lambda request=request: scanner.scan(request))
        inventory = scanner.scan(request)
        results.append((count, elapsed, len(inventory.artifacts)))

    with capsys.disabled():
        print("\n[scan time by artifact count]")
        for count, elapsed, discovered in results:
            print(
                f"  artifacts={count:4d}  discovered={discovered:4d}  median_seconds={elapsed:.6f}"
            )

    for count, elapsed, discovered in results:
        assert elapsed >= 0
        assert discovered == count


def test_baseline_incremental_scan_reuse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Measure how much an unchanged re-scan benefits from reuse."""
    root = tmp_path / "incremental_scan"
    root.mkdir()
    _make_fixture_repository(root, 50)
    scanner = LocalProjectScanner()
    request = _scan_request(root)

    first = scanner.scan(request)
    full_elapsed = _measure(lambda: scanner.scan(request))
    incremental_elapsed = _measure(lambda: scanner.scan(request, first))
    second = scanner.scan(request, first)

    with capsys.disabled():
        print("\n[incremental scan reuse]")
        print(f"  full_scan_seconds={full_elapsed:.6f}")
        print(f"  incremental_scan_seconds={incremental_elapsed:.6f}")
        print(f"  artifacts_reused={second.statistics.artifacts_reused}")

    assert full_elapsed >= 0
    assert incremental_elapsed >= 0
    assert second.statistics.artifacts_reused == len(second.artifacts)


# ---------------------------------------------------------------------------
# Indexer baselines
# ---------------------------------------------------------------------------


def test_baseline_python_index_time(capsys: pytest.CaptureFixture[str]) -> None:
    """Measure Python indexing latency as a function of artifact count."""
    counts = (10, 50, 100)
    results: list[tuple[int, float, int]] = []

    for count in counts:
        project_id = new_project_id()
        content = {
            f"module_{index:04d}.py": f"def function_{index}():\n    return {index}\n".encode()
            for index in range(count)
        }
        artifacts = tuple(
            _make_python_artifact(project_id, path, value) for path, value in content.items()
        )
        inventory = _make_inventory(project_id, artifacts)
        source = _InMemoryProjectSource(content)
        indexer = DeterministicProjectIndexer(source, clock=lambda: NOW)
        elapsed = _measure(
            lambda indexer=indexer, inventory=inventory: indexer.index(IndexRequest(inventory))
        )
        index = indexer.index(IndexRequest(inventory))
        results.append((count, elapsed, len(index.indexed_artifacts)))

    with capsys.disabled():
        print("\n[Python index time by artifact count]")
        for count, elapsed, indexed in results:
            print(f"  artifacts={count:4d}  indexed={indexed:4d}  median_seconds={elapsed:.6f}")

    for count, elapsed, indexed in results:
        assert elapsed >= 0
        assert indexed == count


def test_baseline_incremental_index_reuse(capsys: pytest.CaptureFixture[str]) -> None:
    """Measure incremental index update latency when only one artifact changes."""
    project_id = new_project_id()
    original = {
        f"module_{index:04d}.py": f"def function_{index}():\n    return {index}\n".encode()
        for index in range(50)
    }
    artifacts = tuple(
        _make_python_artifact(project_id, path, value) for path, value in original.items()
    )
    inventory = _make_inventory(project_id, artifacts)
    source = _InMemoryProjectSource(original)
    indexer = DeterministicProjectIndexer(source, clock=lambda: NOW)
    previous = indexer.index(IndexRequest(inventory))

    changed = dict(original)
    changed["module_0000.py"] = b"def function_0():\n    return 1\n"
    changed_artifacts = (
        _make_python_artifact(project_id, "module_0000.py", changed["module_0000.py"]),
        *artifacts[1:],
    )
    changed_inventory = _make_inventory(project_id, changed_artifacts)
    changed_source = _InMemoryProjectSource(changed)
    changed_indexer = DeterministicProjectIndexer(changed_source, clock=lambda: NOW)

    full_elapsed = _measure(
        lambda indexer=changed_indexer, inventory=changed_inventory: indexer.index(
            IndexRequest(inventory)
        )
    )
    incremental_elapsed = _measure(
        lambda indexer=changed_indexer, previous=previous, inventory=changed_inventory: (
            indexer.update(previous, IndexRequest(inventory))
        )
    )
    incremental = changed_indexer.update(previous, IndexRequest(changed_inventory))

    with capsys.disabled():
        print("\n[incremental index reuse]")
        print(f"  full_index_seconds={full_elapsed:.6f}")
        print(f"  incremental_index_seconds={incremental_elapsed:.6f}")
        print(f"  artifacts_reused={incremental.measurements.artifacts_reused}")

    assert full_elapsed >= 0
    assert incremental_elapsed >= 0
    assert incremental.measurements.artifacts_reused == len(artifacts) - 1


# ---------------------------------------------------------------------------
# Retrieval baselines
# ---------------------------------------------------------------------------


def _make_dummy_project_index(artifact_count: int) -> ProjectIndex:
    project_id = new_project_id()
    inventory_id = new_inventory_id()
    artifacts = tuple(
        IndexedArtifact(
            new_artifact_id(),
            IndexingState.FULLY_INDEXED,
            "python-ast",
            "1",
            PROJECT_FINGERPRINT,
            content_fingerprint="sha256:" + "a" * 64,
            path=ArtifactPath(f"module_{index:04d}.py"),
        )
        for index in range(artifact_count)
    )
    return ProjectIndex(
        new_index_id(),
        project_id,
        inventory_id,
        PROJECT_FINGERPRINT,
        "1",
        "indexer-v1",
        artifacts,
        NOW,
    )


def _make_candidates(count: int) -> tuple[RetrievalCandidate, ...]:
    return tuple(
        RetrievalCandidate(
            f"candidate_{index:04d}",
            CandidateType.SOURCE_EXCERPT,
            f"artifact:module_{index:04d}.py",
            f"module_{index:04d}.py",
            (RetrievalEvidence("lexical", "task", f"term_{index}"),),
            CandidateEligibility.ELIGIBLE,
            CandidateOutcome.SELECTED,
            100,
            25,
            new_artifact_id(),
            rationale=SelectionRationale(
                f"candidate_{index:04d}",
                SelectionDecision.SELECTED,
                SelectionReason.LEXICAL_CONTENT_MATCH,
                (RetrievalEvidence("lexical", "task", f"term_{index}"),),
                score=0.5,
                rank=index + 1,
            ),
        )
        for index in range(count)
    )


def test_baseline_retrieval_assembly_latency(capsys: pytest.CaptureFixture[str]) -> None:
    """Measure RetrievalResult assembly latency as candidate count grows."""
    counts = (50, 200, 500)
    results: list[tuple[int, float, int]] = []

    for count in counts:
        index = _make_dummy_project_index(count)
        task = TaskSpecification(
            new_task_id(),
            "explain",
            TaskKind.EXPLAIN,
            RequestedOutput.ANALYSIS,
        )
        request = RetrievalRequest(task, index, ContextBudget(max_items=count))
        candidates = _make_candidates(count)
        budget = BudgetSelectionResult(
            candidates,
            tuple(candidate.candidate_id for candidate in candidates),
            BudgetUsage(25 * count, 100 * count, 100 * count, count, count, count),
            object.__new__(object),  # ContextBudgetReservation default
            DiagnosticCollection(),
            False,
        )
        score_result = RetrievalScoringModel().score(candidates)
        assembler = RetrievalResultAssembler()
        estimates = tuple(
            CandidateBudgetEstimate(candidate.candidate_id, 100) for candidate in candidates
        )

        def _assemble(
            assembler: RetrievalResultAssembler = assembler,
            request: RetrievalRequest = request,
            budget: BudgetSelectionResult = budget,
            score_result: object = score_result,
            estimates: tuple[CandidateBudgetEstimate, ...] = estimates,
        ) -> object:
            return assembler.assemble(
                request,
                new_retrieval_id(),
                budget,
                score_result,
                NOW,
                strategy_versions=("test-v1",),
                estimates=estimates,
            )

        elapsed = _measure(_assemble)
        result = _assemble()
        results.append((count, elapsed, len(result.selected_items)))

    with capsys.disabled():
        print("\n[retrieval result assembly latency]")
        for count, elapsed, selected in results:
            print(f"  candidates={count:4d}  selected={selected:4d}  median_seconds={elapsed:.6f}")

    for count, elapsed, selected in results:
        assert elapsed >= 0
        assert selected == count


# ---------------------------------------------------------------------------
# Context assembly baselines
# ---------------------------------------------------------------------------


def _make_selected_items(count: int) -> tuple[SelectedContextItem, ...]:
    return tuple(
        SelectedContextItem(
            f"item_{index:04d}",
            f"candidate_{index:04d}",
            new_artifact_id(),
            f"artifact:module_{index:04d}.py",
            CandidateType.SOURCE_EXCERPT,
            SelectionRationale(
                f"candidate_{index:04d}",
                SelectionDecision.SELECTED,
                SelectionReason.EXPLICIT_PATH_REFERENCE,
                (RetrievalEvidence("explicit", "task", f"module_{index:04d}.py"),),
                score=1.0,
                rank=index + 1,
            ),
            estimated_bytes=100,
            estimated_characters=100,
        )
        for index in range(count)
    )


@dataclass
class _InMemoryContextSource:
    """ContextContentSource backed by a content mapping."""

    content: dict[str, bytes]

    def read(self, selected_item: SelectedContextItem) -> SourceContent:
        return SourceContent(
            selected_item.content_reference,
            self.content[selected_item.content_reference],
            selected_item.artifact_id,
            ArtifactPath(selected_item.content_reference.replace("artifact:", "")),
        )


def test_baseline_context_materialization_latency(capsys: pytest.CaptureFixture[str]) -> None:
    """Measure ContextItem materialization latency as item count grows."""
    counts = (50, 200, 500)
    results: list[tuple[int, float, int]] = []

    for count in counts:
        selected = _make_selected_items(count)
        content = {
            item.content_reference: f"# content for {item.content_reference}\n".encode()
            for item in selected
        }
        source = _InMemoryContextSource(content)
        materializer = ContextItemMaterializer(source)
        elapsed = _measure(
            lambda materializer=materializer, selected=selected: materializer.materialize(selected)
        )
        items = materializer.materialize(selected)
        results.append((count, elapsed, len(items)))

    with capsys.disabled():
        print("\n[context materialization latency]")
        for count, elapsed, materialized in results:
            print(
                f"  items={count:4d}  materialized={materialized:4d}  median_seconds={elapsed:.6f}"
            )

    for count, elapsed, materialized in results:
        assert elapsed >= 0
        assert materialized == count


# ---------------------------------------------------------------------------
# Prompt measurement baselines
# ---------------------------------------------------------------------------


def _make_large_bundle(item_count: int) -> ContextBundle:
    task = TaskSpecification(
        new_task_id(),
        "Refactor modules.",
        TaskKind.MODIFY,
        RequestedOutput.PATCH_PROPOSAL,
    )
    items: list[ContextItem] = []
    selected_ids: list[str] = []
    for index in range(item_count):
        artifact_id = new_artifact_id()
        rationale = SelectionRationale(
            f"candidate_{index:04d}",
            SelectionDecision.SELECTED,
            SelectionReason.EXPLICIT_PATH_REFERENCE,
            (RetrievalEvidence("explicit", "task", f"module_{index:04d}.py"),),
        )
        selected = SelectedContextItem(
            f"item_{index:04d}",
            f"candidate_{index:04d}",
            artifact_id,
            f"artifact:module_{index:04d}.py",
            CandidateType.FULL_ARTIFACT,
            rationale,
        )
        content = f"def function_{index}():\n    return {index}\n"
        item = ContextItem(selected, selected.content_reference, content)
        items.append(item)
        selected_ids.append(selected.context_item_id)

    return ContextBundle(
        new_context_bundle_id(),
        task.task_id,
        new_retrieval_id(),
        new_project_id(),
        fingerprint_project(("project",), ordering=FingerprintOrdering.ORDERED),
        tuple(items),
        tuple(selected_ids),
        (
            ContextSection(
                "section-main",
                ContextSectionKind.EXPLICIT_REFERENCE,
                "Selected context",
                tuple(selected_ids),
                0,
            ),
        ),
        ContextStatistics(
            item_count=len(items),
            artifact_count=len(items),
            character_count=sum(len(item.content) for item in items),
            byte_count=sum(len(item.content.encode()) for item in items),
            line_count=sum(item.content.count("\n") + 1 for item in items),
        ),
        ContextCoverage(),
        DiagnosticCollection(),
        "1",
        "builder-v1",
        NOW,
    )


def test_baseline_prompt_size_computation(capsys: pytest.CaptureFixture[str]) -> None:
    """Measure prompt measurement latency as context item count grows."""
    counts = (50, 200, 500)
    results: list[tuple[int, float, int]] = []

    for count in counts:
        bundle = _make_large_bundle(count)
        assembly = PromptTemplateAssembler().assemble(
            TaskSpecification(
                bundle.task_id,
                "Refactor modules.",
                TaskKind.MODIFY,
                RequestedOutput.PATCH_PROPOSAL,
            ),
            bundle,
            ContextBundleSerializer().serialize(bundle),
            analysis_response_contract(),
        )
        measurer = PromptMeasurer()
        elapsed = _measure(
            lambda measurer=measurer, assembly=assembly, bundle=bundle: measurer.measure(
                assembly, bundle
            )
        )
        measurements = measurer.measure(assembly, bundle)
        results.append((count, elapsed, measurements.context_item_count))

    with capsys.disabled():
        print("\n[prompt size computation latency]")
        for count, elapsed, context_items in results:
            print(
                f"  items={count:4d}  "
                f"context_items={context_items:4d}  "
                f"median_seconds={elapsed:.6f}"
            )

    for count, elapsed, context_items in results:
        assert elapsed >= 0
        assert context_items == count


# ---------------------------------------------------------------------------
# Patch validation baselines
# ---------------------------------------------------------------------------


def _make_changes(count: int) -> tuple[ProposedChange, ...]:
    return tuple(
        ProposedChange(
            f"change_{index:04d}",
            ArtifactPath(f"src/module_{index:04d}.py"),
            PatchOperation.MODIFY,
            "Apply change.",
            patch_payload=f"def function_{index}():\n    return {index}\n",
            expected_old_fingerprint=CONTENT_FINGERPRINT,
        )
        for index in range(count)
    )


def test_baseline_patch_validation_time(capsys: pytest.CaptureFixture[str]) -> None:
    """Measure patch proposal validation latency as change count grows."""
    counts = (10, 50, 100)
    results: list[tuple[int, float, bool]] = []

    for count in counts:
        changes = _make_changes(count)
        source_paths = tuple(f"src/module_{index:04d}.py" for index in range(count))
        source = PatchSourceState(
            tuple(
                PatchSourceArtifact(ArtifactPath(path), CONTENT_FINGERPRINT)
                for path in source_paths
            )
        )
        consistency = PatchConsistencyEvidence(
            tuple(ArtifactPath(path) for path in source_paths),
            PROJECT_FINGERPRINT,
            PROJECT_FINGERPRINT,
        )
        materializer = PatchProposalMaterializer()
        identifiers = (
            new_patch_proposal_id(),
            new_task_id(),
            new_inference_request_id(),
            new_inference_response_id(),
        )

        def validate(
            materializer: PatchProposalMaterializer = materializer,
            identifiers: tuple[str, str, str, str] = identifiers,
            changes: tuple[ProposedChange, ...] = changes,
            source: PatchSourceState = source,
            consistency: PatchConsistencyEvidence = consistency,
        ) -> object:
            return materializer.materialize(
                proposal_id=identifiers[0],
                task_id=identifiers[1],
                request_id=identifiers[2],
                response_id=identifiers[3],
                changes=changes,
                source_state=source,
                consistency=consistency,
                created_at=NOW,
                summary="Apply changes.",
            )

        elapsed = _measure(validate)
        result = validate()
        results.append((count, elapsed, result.is_applicable))

    with capsys.disabled():
        print("\n[patch proposal validation time]")
        for count, elapsed, applicable in results:
            print(f"  changes={count:4d}  applicable={applicable}  median_seconds={elapsed:.6f}")

    for _count, elapsed, applicable in results:
        assert elapsed >= 0
        assert applicable


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_baseline_summary_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Run all baseline dimensions and emit a single summary line."""
    # This test intentionally re-runs lightweight versions to guarantee a
    # complete report is available even when individual tests are filtered.
    project_id = new_project_id()
    content = {
        "module.py": b"def run():\n    return 1\n",
    }
    artifacts = (_make_python_artifact(project_id, "module.py", content["module.py"]),)
    inventory = _make_inventory(project_id, artifacts)
    source = _InMemoryProjectSource(content)
    index = DeterministicProjectIndexer(source, clock=lambda: NOW).index(IndexRequest(inventory))

    with capsys.disabled():
        print("\n[baseline summary]")
        print(f"  index_status={index.status.value}")
        print(f"  indexed_artifacts={len(index.indexed_artifacts)}")
        print(f"  symbols={len(index.symbols)}")
        print(f"  search_units={len(index.search_units)}")

    assert len(index.indexed_artifacts) == 1
