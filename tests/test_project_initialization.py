"""Tests for safe project initialization orchestration."""

from pathlib import Path

from contextforge.adapters.filesystem import LocalProjectInitialization
from contextforge.application import InitializeProject, ProjectInitialization
from contextforge.project import ProjectRoot, ProjectRootSource


def _root(path: Path) -> ProjectRoot:
    return ProjectRoot(path.resolve(), ProjectRootSource.EXPLICIT)


def test_initialization_creates_only_metadata_by_default(tmp_path: Path) -> None:
    source = tmp_path / "application.py"
    source.write_text("original = True\n", encoding="utf-8")

    result = ProjectInitialization(LocalProjectInitialization()).execute(
        InitializeProject(_root(tmp_path))
    )

    assert result.succeeded
    assert result.metadata_created
    assert result.configuration_file is None
    assert (tmp_path / ".contextforge").is_dir()
    assert source.read_text(encoding="utf-8") == "original = True\n"
    assert set(tmp_path.iterdir()) == {source, tmp_path / ".contextforge"}


def test_initialization_optionally_creates_minimal_valid_config(tmp_path: Path) -> None:
    command = InitializeProject(_root(tmp_path), create_config=True)
    use_case = ProjectInitialization(LocalProjectInitialization())

    result = use_case.execute(command)

    assert result.succeeded
    assert result.metadata_created
    assert result.configuration_created
    assert result.configuration_file == tmp_path / ".contextforge" / "config.toml"
    assert result.configuration_file.read_text(encoding="utf-8") == (
        "# ContextForge project configuration.\n"
    )


def test_repeated_initialization_preserves_existing_configuration(tmp_path: Path) -> None:
    metadata = tmp_path / ".contextforge"
    metadata.mkdir()
    configuration = metadata / "config.toml"
    configuration.write_text('[provider]\nprovider_id = "custom"\n', encoding="utf-8")

    result = ProjectInitialization(LocalProjectInitialization()).execute(
        InitializeProject(_root(tmp_path), create_config=True)
    )

    assert result.succeeded
    assert not result.metadata_created
    assert not result.configuration_created
    assert configuration.read_text(encoding="utf-8") == ('[provider]\nprovider_id = "custom"\n')


def test_initialization_rejects_metadata_file(tmp_path: Path) -> None:
    (tmp_path / ".contextforge").write_text("not a directory", encoding="utf-8")

    result = ProjectInitialization(LocalProjectInitialization()).execute(
        InitializeProject(_root(tmp_path), create_config=True)
    )

    assert not result.succeeded
    assert not result.configuration_created
    assert [str(item.code) for item in result.diagnostics] == ["PROJECT_INIT_METADATA_UNSAFE"]
    assert tuple(tmp_path.iterdir()) == (tmp_path / ".contextforge",)


class _RecordingInitializationPort:
    def __init__(self) -> None:
        self.called = False

    def initialize(
        self,
        project_root: ProjectRoot,
        *,
        create_config: bool,
    ) -> object:
        self.called = True
        raise AssertionError("not reached")


def test_initialization_rejects_another_command_before_using_port(tmp_path: Path) -> None:
    port = _RecordingInitializationPort()
    use_case = ProjectInitialization(port)  # type: ignore[arg-type]

    try:
        use_case.execute(object())  # type: ignore[arg-type]
    except TypeError as error:
        assert str(error) == "command must be an InitializeProject"
    else:
        raise AssertionError("TypeError was not raised")

    assert not port.called
