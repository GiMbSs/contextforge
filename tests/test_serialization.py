"""Tests for versioned envelopes from CF-014 increment I008."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from contextforge.shared import (
    CURRENT_ENVELOPE_SCHEMA_VERSION,
    EnvelopeValidationError,
    SerializationEnvelope,
    UnsupportedSchemaVersionError,
)

CREATED_AT = datetime(2026, 7, 25, 12, 30, 45, 123456, tzinfo=UTC)


def make_envelope(
    *,
    schema_version: str = CURRENT_ENVELOPE_SCHEMA_VERSION,
    payload: object = None,
    metadata: dict[str, object] | None = None,
    created_at: datetime = CREATED_AT,
) -> SerializationEnvelope:
    return SerializationEnvelope(
        schema_name="contextforge.test-artifact",
        schema_version=schema_version,
        artifact_id="project_0123456789abcdef0123456789abcdef",
        created_at=created_at,
        producer_version="0.1.0",
        payload={"message": "Olá, ContextForge 👋"} if payload is None else payload,
        metadata={"source": "test"} if metadata is None else metadata,
    )


def test_current_version_round_trips() -> None:
    envelope = make_envelope()

    restored = SerializationEnvelope.from_json(envelope.to_json())

    assert restored == envelope
    assert restored.schema_version == CURRENT_ENVELOPE_SCHEMA_VERSION
    assert restored.created_at == CREATED_AT


def test_serialization_is_deterministic_for_mapping_order() -> None:
    first = make_envelope(
        payload={"zeta": 2, "alpha": {"second": 2, "first": 1}},
        metadata={"zeta": False, "alpha": True},
    )
    second = make_envelope(
        payload={"alpha": {"first": 1, "second": 2}, "zeta": 2},
        metadata={"alpha": True, "zeta": False},
    )

    assert first == second
    assert first.to_json() == second.to_json()


def test_unicode_is_preserved_without_ascii_escaping() -> None:
    serialized = make_envelope().to_json()

    assert "Olá, ContextForge 👋" in serialized
    assert "\\u00e1" not in serialized


def test_datetime_uses_utc_iso_8601() -> None:
    serialized = make_envelope().to_dict()

    assert serialized["created_at"] == "2026-07-25T12:30:45.123456Z"


@pytest.mark.parametrize(
    "created_at",
    (
        datetime(2026, 7, 25, 12, 30),
        datetime(2026, 7, 25, 12, 30, tzinfo=timezone(timedelta(hours=-3))),
    ),
)
def test_non_utc_datetime_is_rejected(created_at: datetime) -> None:
    with pytest.raises(EnvelopeValidationError, match=r"timezone-aware|use UTC"):
        make_envelope(created_at=created_at)


def test_unsupported_major_version_is_rejected_clearly() -> None:
    with pytest.raises(UnsupportedSchemaVersionError, match="Unsupported schema major version 2"):
        make_envelope(schema_version="2.0")


@pytest.mark.parametrize("schema_version", ("", "0", "1", "01.0", "1.00", "v1.0", "1.0.0"))
def test_malformed_schema_version_is_rejected(schema_version: str) -> None:
    with pytest.raises(EnvelopeValidationError, match=r"major.minor"):
        make_envelope(schema_version=schema_version)


@pytest.mark.parametrize(
    "serialized",
    (
        "",
        "[]",
        '{"schema_name":"missing-fields"}',
        (
            '{"artifact_id":"id","created_at":"2026-07-25T12:30:45+00:00",'
            '"metadata":{},"payload":{},"producer_version":"0.1.0",'
            '"schema_name":"test","schema_version":"1.0"}'
        ),
        (
            '{"artifact_id":"id","created_at":"2026-07-25T12:30:45Z",'
            '"metadata":[],"payload":{},"producer_version":"0.1.0",'
            '"schema_name":"test","schema_version":"1.0"}'
        ),
        (
            '{"artifact_id":"first","artifact_id":"duplicate",'
            '"created_at":"2026-07-25T12:30:45Z","metadata":{},"payload":{},'
            '"producer_version":"0.1.0","schema_name":"test","schema_version":"1.0"}'
        ),
    ),
)
def test_malformed_envelope_is_rejected(serialized: str) -> None:
    with pytest.raises(EnvelopeValidationError):
        SerializationEnvelope.from_json(serialized)


@pytest.mark.parametrize(
    "payload",
    (
        {"unsupported": {1, 2}},
        {"non_finite": float("inf")},
        {"non_string_key": {1: "value"}},
    ),
)
def test_non_json_payload_is_rejected(payload: object) -> None:
    with pytest.raises(EnvelopeValidationError):
        make_envelope(payload=payload)


def test_nested_payload_and_metadata_are_immutable() -> None:
    envelope = make_envelope(
        payload={"items": [{"name": "one"}]},
        metadata={"labels": ["stable"]},
    )

    payload = envelope.payload
    metadata = envelope.metadata

    with pytest.raises(TypeError):
        payload["new"] = "value"
    with pytest.raises(TypeError):
        metadata["new"] = "value"


def test_to_dict_returns_detached_mutable_data() -> None:
    envelope = make_envelope(payload={"items": ["one"]})

    serialized = envelope.to_dict()
    serialized["payload"]["items"].append("two")

    assert envelope.to_dict()["payload"] == {"items": ["one"]}
