from typing import Any, Literal

from pydantic import BaseModel, Field, constr


ProtocolOutputType = Literal["ANSWER", "QUESTION", "TOOL_CALL", "GAP"]


class RuntimeAskRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
    mode: str = "default"
    context: dict[str, Any] = Field(default_factory=dict)


class RuntimeAskResponse(BaseModel):
    session_id: str
    type: ProtocolOutputType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeFrameRequest(BaseModel):
    input: constr(strip_whitespace=True, min_length=1)
    session_id: str | None = None
    mode: str = "default"
    context: dict[str, Any] = Field(default_factory=dict)


class RuntimeSIMAFrame(BaseModel):
    risk: float = 0.0
    uncertainty: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    ambiguity_score: float = 0.0


class RuntimeRetrievedCoreChunk(BaseModel):
    chunk_id: str
    section: str
    title: str
    text: str
    relevance: float = 0.0


class RuntimeRetrievalMetadata(BaseModel):
    returned_chunks: int
    total_characters: int
    truncated: bool
    max_chunks: int
    max_chunk_characters: int
    max_total_characters: int


class RuntimeFrameResponse(BaseModel):
    packet_version: Literal["boris-context/1.0"]
    frame_id: str
    session_id: str
    input: str
    runtime_mode: Literal["context_provider"]
    llm_called: Literal[False]
    bois_frame: dict[str, Any] = Field(default_factory=dict)
    sima: RuntimeSIMAFrame
    boris_context: dict[str, Any] = Field(default_factory=dict)
    retrieved_core: list[RuntimeRetrievedCoreChunk] = Field(default_factory=list)
    retrieval_metadata: RuntimeRetrievalMetadata
    answer_instructions: list[str] = Field(default_factory=list)


class RuntimeErrorResponse(BaseModel):
    error: str
    detail: str
    session_id: str | None = None


class RuntimeResetRequest(BaseModel):
    session_id: constr(strip_whitespace=True, min_length=1)


class RuntimeResetResponse(BaseModel):
    session_id: str
    reset: bool


class RuntimeSessionResponse(BaseModel):
    session_id: str
    exists: bool


class HealthResponse(BaseModel):
    status: str
    service: str
    api: str
