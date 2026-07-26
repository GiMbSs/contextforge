"""Tests for application command and query contracts."""

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from contextforge.application import (
    ApplyPatchProposal,
    ApprovePatchProposal,
    BuildProjectIndex,
    CheckProviderHealth,
    ExecuteTask,
    GetContextBundle,
    GetEffectiveConfiguration,
    GetPatchProposal,
    GetProjectStatus,
    GetPromptPreview,
    InitializeProject,
    ListProviders,
    RejectPatchProposal,
    ScanProject,
)
from contextforge.domain import (
    RequestedOutput,
    TaskKind,
    TaskSpecification,
    new_approval_id,
    new_context_bundle_id,
    new_inventory_id,
    new_patch_proposal_id,
    new_project_id,
    new_task_id,
)
from contextforge.patch import ApprovalMethod
from contextforge.project import ProjectRoot, ProjectRootSource


def _root(tmp_path: Path) -> ProjectRoot:
    return ProjectRoot(tmp_path.resolve(), ProjectRootSource.EXPLICIT)


def _task() -> TaskSpecification:
    return TaskSpecification(
        task_id=new_task_id(),
        task_text="Explain the project",
        task_kind=TaskKind.EXPLAIN,
        requested_output=RequestedOutput.ANALYSIS,
    )


def test_all_application_commands_are_typed_and_immutable(tmp_path: Path) -> None:
    project_id = new_project_id()
    proposal_id = new_patch_proposal_id()
    commands = (
        InitializeProject(_root(tmp_path), create_config=True),
        ScanProject(project_id, _root(tmp_path)),
        BuildProjectIndex(project_id, new_inventory_id()),
        ExecuteTask(project_id, _task(), "local"),
        ApprovePatchProposal(
            proposal_id,
            ApprovalMethod.INTERACTIVE,
            acknowledged_warnings=("second", "first"),
        ),
        RejectPatchProposal(proposal_id, "Does not match the request"),
        ApplyPatchProposal(proposal_id, new_approval_id()),
    )

    assert commands[4].acknowledged_warnings == ("first", "second")
    with pytest.raises(FrozenInstanceError):
        commands[0].create_config = False  # type: ignore[misc]


def test_all_application_queries_are_typed_and_immutable(tmp_path: Path) -> None:
    proposal_id = new_patch_proposal_id()
    queries = (
        GetProjectStatus(new_project_id()),
        GetContextBundle(new_context_bundle_id()),
        GetPromptPreview(new_task_id()),
        ListProviders(),
        CheckProviderHealth("local"),
        GetPatchProposal(proposal_id),
        GetEffectiveConfiguration(_root(tmp_path)),
    )

    assert len(queries) == 7
    with pytest.raises(FrozenInstanceError):
        queries[4].provider_id = "other"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: CheckProviderHealth(" "), "provider_id must not be empty"),
        (
            lambda: RejectPatchProposal(new_patch_proposal_id(), ""),
            "reason must not be empty",
        ),
        (
            lambda: ApprovePatchProposal(
                new_patch_proposal_id(),
                ApprovalMethod.API,
                acknowledged_warnings=("same", "same"),
            ),
            "acknowledged_warnings must not contain duplicates",
        ),
    ],
)
def test_application_messages_reject_ambiguous_values(factory: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()  # type: ignore[operator]


def test_application_messages_reject_wrong_identity_types() -> None:
    with pytest.raises(TypeError, match="project_id must be a ProjectId"):
        GetProjectStatus(new_task_id())  # type: ignore[arg-type]
