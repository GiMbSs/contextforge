"""Project identity and immutable project state."""

from __future__ import annotations

from dataclasses import dataclass

from contextforge.domain.fingerprints import ProjectFingerprint
from contextforge.domain.identifiers import ProjectId


@dataclass(frozen=True, slots=True, eq=False)
class ProjectIdentity:
    """Stable identity and human-readable name of a project."""

    project_id: ProjectId
    display_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, ProjectId):
            raise TypeError("project_id must be a ProjectId")
        if not isinstance(self.display_name, str):
            raise TypeError("display_name must be a string")
        if not self.display_name.strip():
            raise ValueError("Project display name must not be empty")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectIdentity):
            return NotImplemented
        return self.project_id == other.project_id

    def __hash__(self) -> int:
        return hash(self.project_id)


@dataclass(frozen=True, slots=True)
class ProjectState:
    """A fingerprinted immutable state of an identified project."""

    identity: ProjectIdentity
    fingerprint: ProjectFingerprint

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ProjectIdentity):
            raise TypeError("identity must be a ProjectIdentity")
        if not isinstance(self.fingerprint, ProjectFingerprint):
            raise TypeError("fingerprint must be a ProjectFingerprint")
