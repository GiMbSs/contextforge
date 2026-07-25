"""Safe deterministic local project traversal."""

from __future__ import annotations

import os
from pathlib import Path

from contextforge.configuration import ScannerConfig
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.domain import ArtifactPath, ProjectPath
from contextforge.project import ProjectRoot
from contextforge.scanner.ignore import IgnorePolicy
from contextforge.scanner.models import ScanStatistics
from contextforge.scanner.traversal import (
    TraversalEntry,
    TraversalEntryType,
    TraversalResult,
)


def _diagnostic(
    code: str,
    message: str,
    reference: str,
    severity: DiagnosticSeverity = DiagnosticSeverity.WARNING,
) -> Diagnostic:
    return Diagnostic(
        code=DiagnosticCode(code),
        severity=severity,
        message=message,
        capability="scanner",
        location=DiagnosticLocation(reference),
    )


def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _logical_child(parent: ProjectPath, name: str) -> ArtifactPath:
    return ArtifactPath("/".join((*parent.parts, name)))


class LocalProjectTraversal:
    """Discover local entries without reading their file contents."""

    def traverse(
        self,
        root: ProjectRoot,
        configuration: ScannerConfig,
        ignore_policy: IgnorePolicy,
    ) -> TraversalResult:
        """Traverse an authorized project root safely and deterministically."""
        if not isinstance(root, ProjectRoot):
            raise TypeError("root must be a ProjectRoot")
        if not isinstance(configuration, ScannerConfig):
            raise TypeError("configuration must be a ScannerConfig")
        if not isinstance(ignore_policy, IgnorePolicy):
            raise TypeError("ignore_policy must be an IgnorePolicy")

        try:
            resolved_root = root.path.resolve(strict=True)
        except (OSError, RuntimeError):
            return self._root_failure(
                root,
                "SCAN_ROOT_NOT_FOUND",
                "Project Root does not exist or cannot be resolved.",
            )
        if not resolved_root.is_dir():
            return self._root_failure(
                root,
                "SCAN_ROOT_NOT_DIRECTORY",
                "Project Root is not a directory.",
            )

        entries: list[TraversalEntry] = []
        diagnostics: list[Diagnostic] = []
        directories_visited = 0
        discovered = 0
        included = 0
        excluded = 0
        unreadable = 0
        total_bytes = 0
        is_complete = True
        visited_directories = {resolved_root}
        stack: list[tuple[Path, ProjectPath, int]] = [(resolved_root, ProjectPath(""), 0)]

        while stack:
            physical_directory, logical_directory, depth = stack.pop()
            try:
                directory_entries = sorted(
                    os.scandir(physical_directory),
                    key=lambda entry: entry.name,
                )
            except OSError:
                code = (
                    "SCAN_ROOT_UNREADABLE" if logical_directory.is_root else "SCAN_PATH_UNREADABLE"
                )
                reference = str(root.path) if logical_directory.is_root else logical_directory.value
                severity = (
                    DiagnosticSeverity.ERROR
                    if logical_directory.is_root
                    else DiagnosticSeverity.WARNING
                )
                diagnostics.append(
                    _diagnostic(
                        code,
                        "Directory could not be read.",
                        reference,
                        severity,
                    )
                )
                unreadable += 1
                is_complete = False
                continue

            directories_visited += 1
            child_directories: list[tuple[Path, ProjectPath, int]] = []
            for directory_entry in directory_entries:
                discovered += 1
                try:
                    logical_path = _logical_child(
                        logical_directory,
                        directory_entry.name,
                    )
                    candidate = Path(directory_entry.path)
                    is_symlink = directory_entry.is_symlink()
                except (OSError, ValueError):
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_PATH_UNREADABLE",
                            "Project entry could not be normalized.",
                            directory_entry.name,
                        )
                    )
                    unreadable += 1
                    is_complete = False
                    continue

                child_depth = depth + 1
                if configuration.max_depth is not None and child_depth > configuration.max_depth:
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_MAX_DEPTH_REACHED",
                            "Maximum traversal depth was reached.",
                            logical_path.value,
                            DiagnosticSeverity.INFO,
                        )
                    )
                    excluded += 1
                    continue

                if is_symlink and not configuration.follow_symlinks:
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_SYMLINK_SKIPPED",
                            "Symbolic link was skipped by policy.",
                            logical_path.value,
                            DiagnosticSeverity.INFO,
                        )
                    )
                    excluded += 1
                    continue

                try:
                    resolved = candidate.resolve(strict=True)
                except RuntimeError:
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_CYCLE_DETECTED",
                            "A filesystem cycle was detected.",
                            logical_path.value,
                        )
                    )
                    excluded += 1
                    continue
                except OSError:
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_PATH_UNREADABLE",
                            "Project entry could not be resolved.",
                            logical_path.value,
                        )
                    )
                    unreadable += 1
                    is_complete = False
                    continue

                if not _inside_root(resolved, resolved_root):
                    code = "SCAN_SYMLINK_OUTSIDE_ROOT" if is_symlink else "SCAN_PATH_OUTSIDE_ROOT"
                    diagnostics.append(
                        _diagnostic(
                            code,
                            "Resolved project entry is outside the Project Root.",
                            logical_path.value,
                        )
                    )
                    excluded += 1
                    continue

                try:
                    is_directory = resolved.is_dir()
                    is_file = resolved.is_file()
                    metadata = directory_entry.stat(follow_symlinks=False)
                except OSError:
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_PATH_UNREADABLE",
                            "Project entry metadata could not be read.",
                            logical_path.value,
                        )
                    )
                    unreadable += 1
                    is_complete = False
                    continue

                decision = ignore_policy.evaluate(
                    logical_path,
                    is_directory=is_directory,
                )
                if decision.is_excluded:
                    excluded += 1
                    if not is_directory or ignore_policy.can_prune(decision):
                        continue
                else:
                    entry_type = (
                        TraversalEntryType.DIRECTORY
                        if is_directory
                        else (TraversalEntryType.FILE if is_file else TraversalEntryType.OTHER)
                    )
                    entries.append(
                        TraversalEntry(
                            logical_path,
                            entry_type,
                            metadata.st_size,
                            is_symlink,
                        )
                    )
                    included += 1
                    if is_file:
                        total_bytes += metadata.st_size

                if not is_directory:
                    continue
                if configuration.max_depth is not None and child_depth >= configuration.max_depth:
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_MAX_DEPTH_REACHED",
                            "Maximum traversal depth was reached.",
                            logical_path.value,
                            DiagnosticSeverity.INFO,
                        )
                    )
                    continue
                if resolved in visited_directories:
                    diagnostics.append(
                        _diagnostic(
                            "SCAN_CYCLE_DETECTED",
                            "Directory target was already visited.",
                            logical_path.value,
                        )
                    )
                    continue
                visited_directories.add(resolved)
                child_directories.append((resolved, ProjectPath(logical_path.value), child_depth))

            stack.extend(reversed(child_directories))

        statistics = ScanStatistics(
            directories_visited=directories_visited,
            artifacts_discovered=discovered,
            artifacts_included=included,
            artifacts_excluded=excluded,
            unreadable_paths=unreadable,
            total_bytes=total_bytes,
        )
        return TraversalResult(
            tuple(entries),
            statistics,
            DiagnosticCollection(tuple(diagnostics)),
            is_complete=is_complete,
        )

    @staticmethod
    def _root_failure(
        root: ProjectRoot,
        code: str,
        message: str,
    ) -> TraversalResult:
        diagnostic = _diagnostic(
            code,
            message,
            str(root.path),
            DiagnosticSeverity.ERROR,
        )
        return TraversalResult(
            (),
            ScanStatistics(),
            DiagnosticCollection((diagnostic,)),
            is_complete=False,
        )
