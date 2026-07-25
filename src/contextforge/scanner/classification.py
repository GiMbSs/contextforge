"""Deterministic provider-independent artifact classification."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Protocol

from contextforge.scanner.models import ArtifactClassification, ArtifactKind
from contextforge.scanner.traversal import TraversalEntry, TraversalEntryType

MAX_CLASSIFICATION_SAMPLE_BYTES = 8_192

_SOURCE_EXTENSIONS = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".css": "css",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".php": "php",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "shell",
    ".sql": "sql",
    ".swift": "swift",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".vue": "vue",
}
_DOCUMENTATION_EXTENSIONS = {
    ".adoc",
    ".md",
    ".mdx",
    ".rst",
    ".txt",
}
_CONFIGURATION_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".ini",
    ".json",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}
_BINARY_EXTENSIONS = {
    ".7z",
    ".a",
    ".avi",
    ".bin",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".mov",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".wasm",
    ".webp",
    ".woff",
    ".woff2",
    ".zip",
}
_MANIFEST_NAMES = {
    "cargo.lock",
    "cargo.toml",
    "composer.json",
    "composer.lock",
    "go.mod",
    "go.sum",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "yarn.lock",
}
_BUILD_NAMES = {
    "build.gradle",
    "build.gradle.kts",
    "cmakelists.txt",
    "dockerfile",
    "justfile",
    "makefile",
    "meson.build",
}
_CONFIGURATION_NAMES = {
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".pre-commit-config.yaml",
    "docker-compose.yaml",
    "docker-compose.yml",
    "tox.ini",
    "tsconfig.json",
}
_SENSITIVE_PATTERNS = (
    ".env",
    ".env.*",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.pem",
    "*credentials*",
    "*private_key*",
    "*secret*",
    "*token*",
    "id_dsa",
    "id_ed25519",
    "id_rsa",
)
_GENERATED_PATTERNS = (
    "*.bundle.css",
    "*.bundle.js",
    "*.generated.*",
    "*.g.cs",
    "*.min.css",
    "*.min.js",
    "bundle.css",
    "bundle.js",
)
_GENERATED_DIRECTORIES = {"build", "dist", "generated", "out", "target"}
_TEST_DIRECTORIES = {"spec", "specs", "test", "tests"}


def _suffix(filename: str) -> str:
    dot = filename.rfind(".")
    return filename[dot:] if dot > 0 else ""


def _is_test(path_parts: tuple[str, ...], filename: str) -> bool:
    stem = filename.rsplit(".", 1)[0]
    return (
        any(part.casefold() in _TEST_DIRECTORIES for part in path_parts[:-1])
        or stem.startswith("test_")
        or stem.endswith(("_test", ".test", ".spec"))
    )


def _matches_any(value: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatchcase(value, pattern) for pattern in patterns)


def _inspect_sample(sample: bytes) -> tuple[bool, str | None, bool, bool]:
    bounded = sample[:MAX_CLASSIFICATION_SAMPLE_BYTES]
    if not bounded:
        return False, None, False, False

    encoding: str
    try:
        if bounded.startswith(b"\xff\xfe"):
            text = bounded.decode("utf-16-le")
            encoding = "utf-16-le"
        elif bounded.startswith(b"\xfe\xff"):
            text = bounded.decode("utf-16-be")
            encoding = "utf-16-be"
        elif bounded.startswith(b"\xef\xbb\xbf"):
            text = bounded.decode("utf-8-sig")
            encoding = "utf-8-sig"
        else:
            if b"\x00" in bounded:
                return True, None, False, False
            text = bounded.decode("utf-8")
            encoding = "utf-8"
    except UnicodeDecodeError:
        return True, None, False, False

    control_count = sum(ord(character) < 32 and character not in "\t\n\r" for character in text)
    if control_count / max(len(text), 1) > 0.10:
        return True, None, False, False

    folded = text.casefold()
    generated = any(marker in folded for marker in ("@generated", "code generated", "do not edit"))
    sensitive = "-----begin" in folded and "private key-----" in folded
    return False, encoding, generated, sensitive


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Immutable artifact classification with non-sensitive evidence."""

    kind: ArtifactKind
    classifications: tuple[ArtifactClassification, ...]
    detected_language: str | None = None
    encoding: str | None = None
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ArtifactKind):
            raise TypeError("kind must be an ArtifactKind")
        classifications = tuple(self.classifications)
        if not classifications:
            raise ValueError("classifications must not be empty")
        if any(
            not isinstance(classification, ArtifactClassification)
            for classification in classifications
        ):
            raise TypeError("classifications must contain ArtifactClassification values")
        if len(set(classifications)) != len(classifications):
            raise ValueError("classifications must not contain duplicates")
        evidence = tuple(self.evidence)
        if any(not item.strip() for item in evidence):
            raise ValueError("classification evidence must not be empty")
        object.__setattr__(
            self,
            "classifications",
            tuple(sorted(classifications, key=lambda item: item.value)),
        )
        object.__setattr__(self, "evidence", tuple(sorted(set(evidence))))


class ArtifactClassifier(Protocol):
    """Port for deterministic artifact classification."""

    def classify(
        self,
        entry: TraversalEntry,
        sample: bytes = b"",
    ) -> ClassificationResult:
        """Classify one discovered entry from bounded deterministic signals."""
        ...


@dataclass(frozen=True, slots=True)
class DeterministicArtifactClassifier:
    """MVP classifier based on stable paths, names, extensions, and samples."""

    sensitive_patterns: tuple[str, ...] = _SENSITIVE_PATTERNS
    generated_patterns: tuple[str, ...] = _GENERATED_PATTERNS

    def classify(
        self,
        entry: TraversalEntry,
        sample: bytes = b"",
    ) -> ClassificationResult:
        """Classify an entry without provider inference or full-content reads."""
        if not isinstance(entry, TraversalEntry):
            raise TypeError("entry must be a TraversalEntry")
        if not isinstance(sample, bytes):
            raise TypeError("sample must be bytes")
        if entry.entry_type is TraversalEntryType.DIRECTORY:
            return ClassificationResult(
                ArtifactKind.DIRECTORY,
                (ArtifactClassification.UNKNOWN,),
                evidence=("entry_type:directory",),
            )

        path_parts = entry.path.parts
        filename = path_parts[-1].casefold()
        extension = _suffix(filename)
        binary_sample, encoding, generated_sample, sensitive_sample = _inspect_sample(sample)
        binary = extension in _BINARY_EXTENSIONS or binary_sample
        generated = (
            any(part.casefold() in _GENERATED_DIRECTORIES for part in path_parts[:-1])
            or _matches_any(filename, self.generated_patterns)
            or generated_sample
        )
        sensitive = _matches_any(filename, self.sensitive_patterns) or sensitive_sample
        language = _SOURCE_EXTENSIONS.get(extension)
        evidence: list[str] = []
        classifications: set[ArtifactClassification] = set()

        if extension:
            evidence.append(f"extension:{extension}")
        if binary:
            evidence.append("bounded_sample:binary" if binary_sample else "extension:binary")
            classifications.add(ArtifactClassification.BINARY)
        if generated:
            evidence.append(
                "bounded_sample:generated" if generated_sample else "path:generated_pattern"
            )
            classifications.add(ArtifactClassification.GENERATED)
        if sensitive:
            evidence.append(
                "bounded_sample:private_key" if sensitive_sample else "filename:sensitive_pattern"
            )
            classifications.add(ArtifactClassification.SENSITIVE)

        is_test = _is_test(path_parts, filename)
        if binary:
            kind = ArtifactKind.BINARY
        elif generated:
            kind = ArtifactKind.GENERATED
        elif is_test:
            kind = ArtifactKind.TEST
            classifications.update((ArtifactClassification.SOURCE, ArtifactClassification.TEST))
            evidence.append("path:test_convention")
        elif filename in _MANIFEST_NAMES:
            kind = ArtifactKind.MANIFEST
            classifications.add(ArtifactClassification.CONFIGURATION)
            evidence.append("filename:manifest")
        elif filename in _BUILD_NAMES:
            kind = ArtifactKind.BUILD
            classifications.add(ArtifactClassification.CONFIGURATION)
            evidence.append("filename:build")
        elif (
            filename in _CONFIGURATION_NAMES
            or extension in _CONFIGURATION_EXTENSIONS
            or filename == ".env"
            or filename.startswith(".env.")
        ):
            kind = ArtifactKind.CONFIGURATION
            classifications.add(ArtifactClassification.CONFIGURATION)
            evidence.append("filename:configuration")
        elif (
            filename.startswith(("readme", "changelog", "license"))
            or extension in _DOCUMENTATION_EXTENSIONS
            or any(part.casefold() in {"doc", "docs"} for part in path_parts[:-1])
        ):
            kind = ArtifactKind.DOCUMENTATION
            classifications.add(ArtifactClassification.DOCUMENTATION)
            evidence.append("path:documentation")
        elif language is not None:
            kind = ArtifactKind.SOURCE
            classifications.add(ArtifactClassification.SOURCE)
            evidence.append(f"language:{language}")
        else:
            kind = ArtifactKind.UNKNOWN
            classifications.add(ArtifactClassification.UNKNOWN)
            evidence.append("classification:unknown")

        return ClassificationResult(
            kind=kind,
            classifications=tuple(classifications),
            detected_language=language,
            encoding=None if binary else encoding,
            evidence=tuple(evidence),
        )
