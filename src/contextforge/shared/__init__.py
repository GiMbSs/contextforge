"""Shared infrastructure-neutral contracts for ContextForge."""

from contextforge.shared.serialization import (
    CURRENT_ENVELOPE_SCHEMA_VERSION,
    EnvelopeValidationError,
    SerializationEnvelope,
    UnsupportedSchemaVersionError,
)

__all__ = [
    "CURRENT_ENVELOPE_SCHEMA_VERSION",
    "EnvelopeValidationError",
    "SerializationEnvelope",
    "UnsupportedSchemaVersionError",
]
