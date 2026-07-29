"""Canonical MVP acceptance scenario for ContextForge.

This test demonstrates the complete end-to-end workflow described in
CF-014 I100 using a controlled fixture repository and the local mock
provider. It produces a machine-readable transcript and evidence that
can be included in the release acceptance package.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from contextforge.adapters.filesystem import LocalProjectScanner
from contextforge.adapters.patch_proposals import LocalPatchProposalStorage
from contextforge.adapters.project_commands import LocalProjectCommandGateway
from contextforge.application import (
    ExecuteTask,
    PatchProposalExecutionPipeline,
)
from contextforge.configuration import ScannerConfig
from contextforge.context import (
    ContextBundle,
    ContextCoverage,
    ContextStatistics,
)
from contextforge.diagnostics import DiagnosticCollection
from contextforge.domain import (
    ProjectId,
    RequestedOutput,
    TaskKind,
    TaskSpecification,
    new_context_bundle_id,
    new_retrieval_id,
    new_task_id,
)
from contextforge.indexer import (
    DeterministicProjectIndexer,
    IndexRequest,
    IndexStorage,
    ProjectIndex,
)
from contextforge.patch import PatchSourceState
from contextforge.project import ProjectRoot, ProjectRootSource
from contextforge.provider import (
    MOCK_PROVIDER_ID,
    DeterministicMockProvider,
    InferenceResponse,
    MockProviderScenario,
    ProviderExecutionContext,
    ProviderPort,
)
from contextforge.retrieval import (
    ContextBudget,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatistics,
    RetrievalStatus,
)
from contextforge.scanner import (
    ProjectArtifact,
    ProjectInventory,
    ScanRequest,
)

NOW = datetime(2026, 7, 26, 23, 0, 0, tzinfo=UTC)


@pytest.fixture
def fixture_project(tmp_path: Path) -> Path:
    """Create a small controlled Python project for the acceptance run."""
    project = tmp_path / "acceptance_project"
    project.mkdir()
    source_dir = project / "src"
    source_dir.mkdir()
    (source_dir / "example.py").write_text(
        "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n",
        encoding="utf-8",
    )
    return project


@pytest.fixture
def root(fixture_project: Path) -> ProjectRoot:
    """Return an explicit project root for the fixture."""
    return ProjectRoot(fixture_project.resolve(strict=True), ProjectRootSource.EXPLICIT)


class _EmptyRetriever:
    """Minimal deterministic retriever that returns an empty retrieval result."""

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        return RetrievalResult(
            new_retrieval_id(),
            request.task.task_id,
            request.project_index.index_id,
            request.project_index.project_fingerprint,
            ("acceptance-empty-retriever",),
            (),
            (),
            (),
            request.budget,
            DiagnosticCollection(),
            RetrievalStatistics(),
            RetrievalStatus.COMPLETE,
            NOW,
        )


class _EmptyContextBuilder:
    """Minimal deterministic context builder that returns an empty bundle."""

    def build(
        self,
        retrieval_result: RetrievalResult,
        *,
        project_id: ProjectId,
    ) -> ContextBundle:
        return ContextBundle(
            new_context_bundle_id(),
            retrieval_result.task_id,
            retrieval_result.retrieval_id,
            project_id,
            retrieval_result.project_fingerprint,
            (),
            (),
            (),
            ContextStatistics(),
            ContextCoverage(),
            DiagnosticCollection(),
            "1",
            "acceptance-empty-context-builder",
            NOW,
        )


class _FixtureSource:
    """Read artifact bytes from the fixture project root."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, artifact: ProjectArtifact) -> bytes:
        candidate = self.root.joinpath(*artifact.path.parts).resolve(strict=True)
        candidate.relative_to(self.root)
        return candidate.read_bytes()


class _FixtureSourceStates:
    """Supply an empty source state because the test creates a new file."""

    def load(self, inventory: ProjectInventory) -> PatchSourceState:
        return PatchSourceState()


class _StructuredPatchProvider:
    """Wrap the mock provider to emit a valid structured patch proposal."""

    def __init__(self, timestamp: datetime) -> None:
        self._provider = DeterministicMockProvider(
            MockProviderScenario.SUCCESSFUL_STRUCTURED_PATCH,
            timestamp,
        )

    def invoke(
        self,
        request: InferenceResponse,
        execution_context: ProviderExecutionContext,
    ) -> InferenceResponse:
        response = self._provider.invoke(request, execution_context)
        changes = [
            {
                "path": "src/generated.py",
                "operation": "create",
                "explanation": "Add the requested module as part of the acceptance scenario.",
                "new_content": "value = 42\n",
            },
        ]
        patch_payload = json.dumps(
            {"changes": changes},
            separators=(",", ":"),
            sort_keys=True,
        )
        content = json.dumps(
            {
                "affected_files": ["src/generated.py"],
                "assumptions": [],
                "changes": changes,
                "patch_format": "structured_changes",
                "patch_payload": patch_payload,
                "response_type": "patch_proposal",
                "summary": "Add generated module for acceptance scenario.",
                "warnings": [],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return replace(response, content=content)


class _PatchProviders:
    def __init__(self, timestamp: datetime) -> None:
        self.provider = _StructuredPatchProvider(timestamp)

    def get(self, provider_id: str) -> ProviderPort | None:
        return cast("ProviderPort", self.provider) if provider_id == "mock-patch" else None


def _fixture_index_storage(root: ProjectRoot) -> IndexStorage:
    """Return an index storage that reuses the gateway's on-demand index."""

    class _OnDemandIndexStorage:
        def __init__(self) -> None:
            self._index: ProjectIndex | None = None

        def load(self, project_id: ProjectId) -> ProjectIndex | None:
            return self._index

        def save(self, project_index: ProjectIndex) -> None:
            self._index = project_index

        def remove(self, index_id: object) -> None:
            del index_id

    return _OnDemandIndexStorage()  # type: ignore[return-value]


def _project_id(root: ProjectRoot) -> ProjectId:
    """Mirror the CLI project identifier derivation."""
    from uuid import NAMESPACE_URL, uuid5

    return ProjectId(f"project_{uuid5(NAMESPACE_URL, root.path.as_uri()).hex}")


def _run_patch_pipeline(root: ProjectRoot) -> tuple[str, str]:
    """Generate, persist, and return a patch proposal id and project fingerprint."""
    scanner = LocalProjectScanner()
    scanner_config = ScannerConfig(exclude_patterns=(".contextforge/",))
    initial_scan = scanner.scan(ScanRequest(_project_id(root), root, scanner_config))
    project_index = DeterministicProjectIndexer(_FixtureSource(root.path)).index(
        IndexRequest(initial_scan)
    )
    storage = LocalPatchProposalStorage(root)
    index_storage = _fixture_index_storage(root)
    index_storage.save(project_index)
    pipeline = PatchProposalExecutionPipeline(
        inventory_storage=_SingleInventoryStorage(initial_scan),
        index_storage=index_storage,
        indexer=DeterministicProjectIndexer(_FixtureSource(root.path)),
        retriever=_EmptyRetriever(),
        context_builder=_EmptyContextBuilder(),
        providers=_PatchProviders(NOW),
        source_states=_FixtureSourceStates(),
        proposal_storage=storage,
        budget=ContextBudget(max_items=5, max_bytes=10_000),
        clock=lambda: NOW,
    )
    task = TaskSpecification(
        new_task_id(),
        "Add a generated module.",
        TaskKind.ADD,
        RequestedOutput.PATCH_PROPOSAL,
    )
    result = pipeline.execute(ExecuteTask(initial_scan.project_id, task, "mock-patch"))
    return str(result.proposal.proposal_id), str(initial_scan.project_fingerprint)


class _SingleInventoryStorage:
    def __init__(self, inventory: ProjectInventory) -> None:
        self.inventory = inventory

    def load(self, inventory_id: object) -> ProjectInventory | None:
        return self.inventory

    def load_latest(self, project_id: ProjectId) -> ProjectInventory | None:
        return self.inventory

    def save(self, inventory: ProjectInventory) -> None:
        del inventory


def _transcript_entry(step: int, command: str, result: object) -> dict[str, object]:
    return {
        "step": step,
        "command": command,
        "result": result,
    }


def test_canonical_mvp_acceptance_scenario(root: Path) -> None:
    """Execute the 13-step canonical MVP acceptance scenario."""
    gateway = LocalProjectCommandGateway()
    transcript: list[dict[str, object]] = []

    # 1. Initialize project.
    init_result = gateway.initialize(root)
    assert init_result.exit_code == 0
    transcript.append(_transcript_entry(1, "init", init_result.data))

    # 2. Scan project.
    scan_result = gateway.scan(root)
    assert scan_result.exit_code == 0
    assert scan_result.data["artifact_count"] >= 1
    initial_fingerprint = str(scan_result.data["project_fingerprint"])
    transcript.append(_transcript_entry(2, "scan", scan_result.data))

    # 3. Build index.
    index_result = gateway.index(root)
    assert index_result.exit_code == 0
    transcript.append(_transcript_entry(3, "index", index_result.data))

    # 4. Submit analysis task.
    analysis_result = gateway.analyze(root, "Explain the project.", MOCK_PROVIDER_ID)
    assert analysis_result.exit_code == 0
    transcript.append(_transcript_entry(4, "run --analysis-only", analysis_result.data))

    # 5. Inspect retrieved context.
    context_result = gateway.inspect_context(root, "show")
    assert context_result.exit_code == 0
    transcript.append(_transcript_entry(5, "context show", context_result.data))

    # 6. Inspect prompt measurements.
    prompt_result = gateway.inspect_prompt(root, "measure")
    assert prompt_result.exit_code == 0
    transcript.append(_transcript_entry(6, "prompt measure", prompt_result.data))

    # 7. Invoke the local provider through the production patch pipeline.
    proposal_result = gateway.propose(
        root,
        "Add a generated module.",
        MOCK_PROVIDER_ID,
    )
    assert proposal_result.exit_code == 0
    proposal_id = str(proposal_result.data["proposal_id"])
    transcript.append(
        _transcript_entry(
            7,
            "run Add a generated module.",
            proposal_result.data,
        )
    )

    # 8. Confirm that provider output became a validated Patch Proposal.
    generated_record = LocalPatchProposalStorage(root).load_record(proposal_id)
    assert generated_record is not None
    assert generated_record["validation"]["state"] == "valid"
    transcript.append(
        _transcript_entry(
            8,
            "patch proposal validation",
            {
                "proposal_id": proposal_id,
                "proposal_fingerprint": generated_record["lifecycle"]["proposal_fingerprint"],
            },
        )
    )

    # 9. Review proposal.
    review_result = gateway.inspect_patch(root, "review", proposal_id=proposal_id)
    assert review_result.exit_code == 0
    review = review_result.data["review"]
    assert isinstance(review, dict)
    assert review.get("operation_counts", {}).get("create") == 1
    transcript.append(_transcript_entry(9, "patch review", review_result.data))

    # 10. Approve exact proposal.
    approve_result = gateway.authorize_patch(
        root,
        "approve",
        proposal_id,
        approval_method="non_interactive",
    )
    assert approve_result.exit_code == 0
    transcript.append(_transcript_entry(10, "patch approve", approve_result.data))

    # 11. Apply proposal safely.
    apply_result = gateway.apply_patch_proposal(root, proposal_id)
    assert apply_result.exit_code == 0
    assert apply_result.data["status"] == "applied"
    transcript.append(_transcript_entry(11, "patch apply", apply_result.data))

    # 12. Verify resulting project fingerprint.
    final_scan = gateway.scan(root)
    assert final_scan.exit_code == 0
    final_fingerprint = str(final_scan.data["project_fingerprint"])
    assert final_fingerprint != initial_fingerprint
    transcript.append(
        _transcript_entry(
            12,
            "verify project fingerprint",
            {
                "final_fingerprint": final_fingerprint,
                "initial_fingerprint": initial_fingerprint,
            },
        )
    )

    # 13. Confirm traceability and diagnostics.
    diagnostics_result = gateway.diagnostics(root)
    assert diagnostics_result.exit_code == 0
    transcript.append(_transcript_entry(13, "diagnostics", diagnostics_result.data))

    # Confirm the generated file exists.
    generated = root.path / "src" / "contextforge_generated.py"
    assert generated.read_text(encoding="utf-8") == "value = 42\n"

    # Persist the acceptance transcript for the release package.
    acceptance_dir = root.path / ".contextforge" / "acceptance"
    acceptance_dir.mkdir(parents=True, exist_ok=True)
    (acceptance_dir / "transcript.json").write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert len(transcript) == 13
