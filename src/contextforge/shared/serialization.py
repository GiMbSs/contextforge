"""Versioned deterministic serialization envelopes."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import cast

CURRENT_ENVELOPE_SCHEMA_VERSION = "1.0"
SUPPORTED_ENVELOPE_SCHEMA_MAJOR = 1

type JsonScalar = str | int | float | bool | None
type FrozenJsonValue = JsonScalar | tuple[FrozenJsonValue, ...] | Mapping[str, FrozenJsonValue]


class EnvelopeValidationError(ValueError):
    """Raised when a serialization envelope is malformed."""


class UnsupportedSchemaVersionError(EnvelopeValidationError):
    """Raised when an envelope uses an unsupported schema major version."""


def _schema_major(version: str) -> int:
    if re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version) is None:
        raise EnvelopeValidationError("schema_version must use canonical 'major.minor' form")
    return int(version.split(".", maxsplit=1)[0])


def _object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EnvelopeValidationError(f"Envelope JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _freeze_json(value: object, *, field_name: str) -> FrozenJsonValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EnvelopeValidationError(f"{field_name} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        frozen_items: dict[str, FrozenJsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise EnvelopeValidationError(f"{field_name} object keys must be strings")
            if key in frozen_items:
                raise EnvelopeValidationError(f"{field_name} contains duplicate key {key!r}")
            frozen_items[key] = _freeze_json(item, field_name=field_name)
        return MappingProxyType(dict(sorted(frozen_items.items())))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item, field_name=field_name) for item in value)
    raise EnvelopeValidationError(
        f"{field_name} contains unsupported value of type {type(value).__name__}"
    )


def _thaw_json(value: FrozenJsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _parse_utc_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EnvelopeValidationError("created_at must be a UTC ISO 8601 string ending in 'Z'")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise EnvelopeValidationError("created_at must be a valid UTC ISO 8601 datetime") from error
    return parsed


def _format_utc_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise EnvelopeValidationError("created_at must be timezone-aware")
    if value.utcoffset() != UTC.utcoffset(value):
        raise EnvelopeValidationError("created_at must use UTC")
    normalized = value.astimezone(UTC)
    return normalized.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class SerializationEnvelope:
    """Immutable, versioned envelope for one serialized artifact."""

    schema_name: str
    schema_version: str
    artifact_id: str
    created_at: datetime
    producer_version: str
    payload: object
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.schema_name.strip():
            raise EnvelopeValidationError("schema_name must not be empty")
        if not self.artifact_id.strip():
            raise EnvelopeValidationError("artifact_id must not be empty")
        if not self.producer_version.strip():
            raise EnvelopeValidationError("producer_version must not be empty")

        major = _schema_major(self.schema_version)
        if major != SUPPORTED_ENVELOPE_SCHEMA_MAJOR:
            raise UnsupportedSchemaVersionError(
                f"Unsupported schema major version {major}; "
                f"supported major is {SUPPORTED_ENVELOPE_SCHEMA_MAJOR}"
            )

        formatted_datetime = _format_utc_datetime(self.created_at)
        normalized_datetime = _parse_utc_datetime(formatted_datetime)
        frozen_payload = _freeze_json(self.payload, field_name="payload")
        frozen_metadata = _freeze_json(self.metadata, field_name="metadata")
        if not isinstance(frozen_metadata, Mapping):
            raise EnvelopeValidationError("metadata must be a JSON object")

        object.__setattr__(self, "created_at", normalized_datetime)
        object.__setattr__(self, "payload", frozen_payload)
        object.__setattr__(self, "metadata", frozen_metadata)

    def to_dict(self) -> dict[str, object]:
        """Return a detached serialization-ready representation."""
        return {
            "artifact_id": self.artifact_id,
            "created_at": _format_utc_datetime(self.created_at),
            "metadata": _thaw_json(cast("FrozenJsonValue", self.metadata)),
            "payload": _thaw_json(cast("FrozenJsonValue", self.payload)),
            "producer_version": self.producer_version,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
        }

    def to_json(self) -> str:
        """Serialize the envelope as deterministic compact JSON."""
        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, serialized: str) -> SerializationEnvelope:
        """Deserialize and validate a versioned envelope."""
        try:
            decoded = json.loads(serialized, object_pairs_hook=_object_from_pairs)
        except (json.JSONDecodeError, TypeError) as error:
            raise EnvelopeValidationError("Envelope must be valid JSON") from error

        if not isinstance(decoded, dict):
            raise EnvelopeValidationError("Envelope JSON must be an object")

        expected_fields = {
            "artifact_id",
            "created_at",
            "metadata",
            "payload",
            "producer_version",
            "schema_name",
            "schema_version",
        }
        actual_fields = set(decoded)
        if actual_fields != expected_fields:
            missing = sorted(expected_fields - actual_fields)
            unexpected = sorted(actual_fields - expected_fields)
            raise EnvelopeValidationError(
                f"Envelope fields do not match schema; missing={missing}, unexpected={unexpected}"
            )

        string_fields = ("artifact_id", "producer_version", "schema_name", "schema_version")
        if any(not isinstance(decoded[field], str) for field in string_fields):
            raise EnvelopeValidationError("Envelope identity and version fields must be strings")
        if not isinstance(decoded["metadata"], dict):
            raise EnvelopeValidationError("metadata must be a JSON object")

        return cls(
            schema_name=decoded["schema_name"],
            schema_version=decoded["schema_version"],
            artifact_id=decoded["artifact_id"],
            created_at=_parse_utc_datetime(decoded["created_at"]),
            producer_version=decoded["producer_version"],
            payload=decoded["payload"],
            metadata=decoded["metadata"],
        )
