"""Filesystem persistence for rendered evaluation reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from contextforge.evaluation import EvaluationExecutionResult
from contextforge.evaluation.reporting import (
    render_evaluation_json,
    render_evaluation_markdown,
)


@dataclass(frozen=True, slots=True)
class EvaluationReportPaths:
    """Paths written for one evaluation report."""

    json_path: Path
    markdown_path: Path


@dataclass(slots=True)
class FilesystemEvaluationReportWriter:
    """Atomically persist reports below one authorized output root."""

    output_root: Path

    def __post_init__(self) -> None:
        if not isinstance(self.output_root, Path):
            raise TypeError("output_root must be a Path")
        self.output_root = self.output_root.resolve(strict=True)
        if not self.output_root.is_dir():
            raise ValueError("output_root must be a directory")

    def write(
        self,
        result: EvaluationExecutionResult,
        report_name: str,
    ) -> EvaluationReportPaths:
        """Write JSON and Markdown siblings without permitting path traversal."""
        if not isinstance(report_name, str) or not report_name.strip():
            raise TypeError("report_name must be a non-empty string")
        if Path(report_name).name != report_name or report_name in {".", ".."}:
            raise ValueError("report_name must be a filename stem")
        json_path = self.output_root / f"{report_name}.json"
        markdown_path = self.output_root / f"{report_name}.md"
        self._replace(json_path, render_evaluation_json(result) + "\n")
        self._replace(markdown_path, render_evaluation_markdown(result))
        return EvaluationReportPaths(json_path, markdown_path)

    @staticmethod
    def _replace(destination: Path, content: str) -> None:
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(destination)
