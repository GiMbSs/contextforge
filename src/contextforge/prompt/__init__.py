"""Prompt Builder and inference request contracts."""

from contextforge.prompt.analysis import (
    ANALYSIS_RESPONSE_CONTRACT_ID,
    ANALYSIS_RESPONSE_CONTRACT_VERSION,
    AnalysisFinding,
    AnalysisResponse,
    AnalysisResponseStatus,
    analysis_response_contract,
)
from contextforge.prompt.assembly import (
    CONTEXT_USAGE_RULES,
    PROMPT_TEMPLATE_ID,
    PROMPT_TEMPLATE_VERSION,
    SYSTEM_OPERATING_RULES,
    PromptTemplateAssembler,
    PromptTemplateAssembly,
)
from contextforge.prompt.models import (
    DeliveryRequirements,
    InferenceRequest,
    PromptMeasurements,
    PromptMessage,
    PromptRole,
    PromptTrust,
    ResponseContract,
    ResponseFormat,
)
from contextforge.prompt.patch import (
    PATCH_RESPONSE_CONTRACT_ID,
    PATCH_RESPONSE_CONTRACT_VERSION,
    PatchPayloadFormat,
    PatchResponseEnvelope,
    ProposedChangeOperation,
    ProposedFileChange,
    patch_response_contract,
)

__all__ = [
    "ANALYSIS_RESPONSE_CONTRACT_ID",
    "ANALYSIS_RESPONSE_CONTRACT_VERSION",
    "CONTEXT_USAGE_RULES",
    "PATCH_RESPONSE_CONTRACT_ID",
    "PATCH_RESPONSE_CONTRACT_VERSION",
    "PROMPT_TEMPLATE_ID",
    "PROMPT_TEMPLATE_VERSION",
    "SYSTEM_OPERATING_RULES",
    "AnalysisFinding",
    "AnalysisResponse",
    "AnalysisResponseStatus",
    "DeliveryRequirements",
    "InferenceRequest",
    "PatchPayloadFormat",
    "PatchResponseEnvelope",
    "PromptMeasurements",
    "PromptMessage",
    "PromptRole",
    "PromptTemplateAssembler",
    "PromptTemplateAssembly",
    "PromptTrust",
    "ProposedChangeOperation",
    "ProposedFileChange",
    "ResponseContract",
    "ResponseFormat",
    "analysis_response_contract",
    "patch_response_contract",
]
