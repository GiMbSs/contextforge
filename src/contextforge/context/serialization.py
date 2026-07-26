"""Provider-independent Context Bundle serialization."""

from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree

from contextforge.context.models import ContextBundle, ContextItem

CONTEXT_SERIALIZATION_MEDIA_TYPE = "application/vnd.contextforge.context+xml"
CONTEXT_SERIALIZATION_VERSION = "context-bundle-xml-v1"


@dataclass(frozen=True, slots=True)
class SerializedContextBundle:
    """Self-describing serialized bundle ready for a transport adapter."""

    content: str
    media_type: str = CONTEXT_SERIALIZATION_MEDIA_TYPE
    serialization_version: str = CONTEXT_SERIALIZATION_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise TypeError("content must be a string")
        if not self.media_type.strip():
            raise ValueError("media_type must not be empty")
        if not self.serialization_version.strip():
            raise ValueError("serialization_version must not be empty")


@dataclass(frozen=True, slots=True)
class ContextBundleSerializer:
    """Serialize bundle data while preserving untrusted-content boundaries."""

    version: str = CONTEXT_SERIALIZATION_VERSION

    def serialize(self, bundle: ContextBundle) -> SerializedContextBundle:
        """Return deterministic XML-like structured content."""
        if not isinstance(bundle, ContextBundle):
            raise TypeError("bundle must be a ContextBundle")

        root = ElementTree.Element(
            "context_bundle",
            {
                "bundle_id": str(bundle.bundle_id),
                "bundle_version": bundle.bundle_version,
                "serialization_version": self.version,
            },
        )
        _text_element(root, "task_id", str(bundle.task_id))
        _text_element(root, "retrieval_id", str(bundle.retrieval_id))
        _text_element(root, "project_id", str(bundle.project_id))
        _text_element(root, "project_fingerprint", str(bundle.project_fingerprint))
        _text_element(root, "builder_version", bundle.builder_version)
        _text_element(root, "created_at", bundle.created_at.isoformat())

        sections = ElementTree.SubElement(root, "sections")
        items_by_id = {item.context_item_id: item for item in bundle.items}
        for section in bundle.sections:
            section_element = ElementTree.SubElement(
                sections,
                "context_section",
                {
                    "id": section.section_id,
                    "kind": section.kind.value,
                    "order": str(section.order),
                },
            )
            _text_element(section_element, "title", section.title)
            for item_id in section.item_ids:
                _serialize_item(section_element, items_by_id[item_id])

        statistics = ElementTree.SubElement(root, "statistics")
        for field_name in bundle.statistics.__dataclass_fields__:
            _text_element(
                statistics,
                field_name,
                str(getattr(bundle.statistics, field_name)),
            )

        coverage = ElementTree.SubElement(root, "coverage")
        for field_name in (
            "targets",
            "dependencies",
            "interfaces",
            "tests",
            "configuration",
            "constraints",
            "error_locations",
        ):
            _text_element(coverage, field_name, getattr(bundle.coverage, field_name).value)
        missing = ElementTree.SubElement(coverage, "missing_references")
        for reference in bundle.coverage.missing_references:
            _text_element(missing, "reference", reference)

        diagnostics = ElementTree.SubElement(root, "diagnostics")
        for diagnostic in bundle.diagnostics:
            element = ElementTree.SubElement(
                diagnostics,
                "diagnostic",
                {
                    "code": str(diagnostic.code),
                    "severity": diagnostic.severity.value,
                },
            )
            _text_element(element, "message", diagnostic.message)

        serialized = ElementTree.tostring(
            root,
            encoding="unicode",
            short_empty_elements=False,
        )
        return SerializedContextBundle(serialized, serialization_version=self.version)


def _serialize_item(parent: ElementTree.Element, item: ContextItem) -> None:
    selected = item.selected_item
    element = ElementTree.SubElement(
        parent,
        "context_item",
        {
            "candidate_id": selected.candidate_id,
            "id": item.context_item_id,
            "type": selected.candidate_type.value,
        },
    )
    _text_element(element, "path", item.source_path.value if item.source_path else "")
    location = ElementTree.SubElement(element, "location")
    if selected.location is not None:
        for field_name in ("start_line", "start_column", "end_line", "end_column"):
            _text_element(location, field_name, str(getattr(selected.location, field_name)))
    _text_element(element, "source_reference", item.source_reference)
    _text_element(
        element,
        "source_fingerprint",
        item.verified_source_fingerprint or "",
    )
    _text_element(
        element,
        "sensitivity",
        selected.sensitivity_classification,
    )
    rationale = ElementTree.SubElement(
        element,
        "selection_rationale",
        {
            "decision": selected.rationale.decision.value,
            "reason": selected.rationale.primary_reason.value,
        },
    )
    for evidence in selected.rationale.evidence:
        evidence_element = ElementTree.SubElement(
            rationale,
            "evidence",
            {"type": evidence.evidence_type},
        )
        _text_element(evidence_element, "source", evidence.source)
        _text_element(evidence_element, "detail", evidence.detail)
    content = ElementTree.SubElement(element, "content", {"trust": "untrusted"})
    content.text = item.content


def _text_element(
    parent: ElementTree.Element,
    name: str,
    value: str,
) -> ElementTree.Element:
    element = ElementTree.SubElement(parent, name)
    element.text = value
    return element
