"""Safe local filesystem adapter for project initialization."""

from __future__ import annotations

from pathlib import Path

from contextforge.application import ProjectInitializationResult
from contextforge.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticCollection,
    DiagnosticLocation,
    DiagnosticSeverity,
)
from contextforge.project import ProjectRoot

_METADATA_DIRECTORY = ".contextforge"
_CONFIGURATION_FILE = "config.toml"
_MINIMAL_CONFIGURATION = "# ContextForge project configuration.\n"


def _failure(
    metadata: Path,
    configuration: Path | None,
    *,
    metadata_created: bool,
    code: str,
    message: str,
) -> ProjectInitializationResult:
    diagnostic = Diagnostic(
        code=DiagnosticCode(code),
        severity=DiagnosticSeverity.ERROR,
        message=message,
        capability="project_initialization",
        location=DiagnosticLocation(str(metadata)),
    )
    return ProjectInitializationResult(
        metadata_directory=metadata,
        configuration_file=configuration,
        metadata_created=metadata_created,
        diagnostics=DiagnosticCollection((diagnostic,)),
    )


def _is_direct_metadata_directory(metadata: Path, root: Path) -> bool:
    try:
        return metadata.is_dir() and metadata.resolve(strict=True).parent == root
    except (OSError, RuntimeError):
        return False


class LocalProjectInitialization:
    """Create local metadata idempotently without overwriting configuration."""

    def initialize(
        self,
        project_root: ProjectRoot,
        *,
        create_config: bool,
    ) -> ProjectInitializationResult:
        """Create `.contextforge` and an optional inert minimal TOML file."""
        if not isinstance(project_root, ProjectRoot):
            raise TypeError("project_root must be a ProjectRoot")
        if type(create_config) is not bool:
            raise TypeError("create_config must be a boolean")

        try:
            root = project_root.path.resolve(strict=True)
        except (OSError, RuntimeError):
            metadata = project_root.path / _METADATA_DIRECTORY
            return _failure(
                metadata,
                None,
                metadata_created=False,
                code="PROJECT_INIT_ROOT_INVALID",
                message="The authorized project root is no longer accessible.",
            )

        metadata = root / _METADATA_DIRECTORY
        configuration = metadata / _CONFIGURATION_FILE if create_config else None
        metadata_created = False

        try:
            metadata.mkdir(mode=0o700)
            metadata_created = True
        except FileExistsError:
            pass
        except OSError:
            return _failure(
                metadata,
                configuration,
                metadata_created=False,
                code="PROJECT_INIT_METADATA_FAILED",
                message="The project metadata directory could not be created.",
            )

        if not _is_direct_metadata_directory(metadata, root):
            return _failure(
                metadata,
                configuration,
                metadata_created=metadata_created,
                code="PROJECT_INIT_METADATA_UNSAFE",
                message="The project metadata path is not a direct local directory.",
            )

        configuration_created = False
        if configuration is not None:
            try:
                with configuration.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(_MINIMAL_CONFIGURATION)
                configuration_created = True
            except FileExistsError:
                if not configuration.is_file():
                    return _failure(
                        metadata,
                        configuration,
                        metadata_created=metadata_created,
                        code="PROJECT_INIT_CONFIG_UNSAFE",
                        message="The project configuration path is not a regular file.",
                    )
            except OSError:
                return _failure(
                    metadata,
                    configuration,
                    metadata_created=metadata_created,
                    code="PROJECT_INIT_CONFIG_FAILED",
                    message="The project configuration file could not be created.",
                )

        return ProjectInitializationResult(
            metadata_directory=metadata,
            configuration_file=configuration,
            metadata_created=metadata_created,
            configuration_created=configuration_created,
        )
