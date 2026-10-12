from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator

from .enums import (
    ActionType, AgendaMode, AgendaStatus, Authority, ConceptRelation,
    EvidenceType, FreshnessClass, SourceType,
)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    as_of: Optional[datetime] = None
    conversation_id: Optional[str] = None
    user_context: Dict[str, Any] = Field(default_factory=dict)


class ConceptExpansion(BaseModel):
    term: str
    relation: ConceptRelation
    weight: float = Field(ge=0.0, le=1.0)
    source: str = "model"


class Concept(BaseModel):
    concept_id: str
    surface_form: str
    canonical: str
    concept_type: str
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    expansions: List[ConceptExpansion] = Field(default_factory=list)


class Action(BaseModel):
    action_id: str
    action: ActionType
    targets: List[str] = Field(default_factory=list)
    metric: Optional[str] = None
    qualifiers: Dict[str, Any] = Field(default_factory=dict)


class EvidenceRequirement(BaseModel):
    requirement_id: str
    description: str
    evidence_types: List[EvidenceType] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)
    freshness: Optional[str] = None
    minimum_authority: Optional[Authority] = None
    required: bool = True


class Agenda(BaseModel):
    agenda_id: str
    objective: str
    mode: AgendaMode
    depends_on: List[str] = Field(default_factory=list)
    concepts: List[Concept] = Field(default_factory=list)
    actions: List[Action] = Field(default_factory=list)
    evidence_requirements: List[EvidenceRequirement] = Field(default_factory=list)


class AgendaGraph(BaseModel):
    original_query: str
    agendas: List[Agenda]

    @model_validator(mode="after")
    def validate_dependencies(self):
        ids = {a.agenda_id for a in self.agendas}
        if len(ids) != len(self.agendas):
            raise ValueError("agenda_id values must be unique")
        for agenda in self.agendas:
            unknown = set(agenda.depends_on) - ids
            if unknown:
                raise ValueError(f"{agenda.agenda_id} depends on unknown agendas: {sorted(unknown)}")
            if agenda.agenda_id in agenda.depends_on:
                raise ValueError(f"{agenda.agenda_id} cannot depend on itself")
        return self


class SourceDescriptor(BaseModel):
    source_id: str
    source_type: SourceType
    name: str
    description: str
    authority: Authority
    freshness_class: FreshnessClass
    expected_latency_ms: Optional[int] = Field(default=None, ge=0)
    enabled: bool = True
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RetrievalCandidate(BaseModel):
    source_id: str
    source_type: SourceType
    reason: str
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    recency: float = Field(default=0.0, ge=0.0, le=1.0)
    authority: float = Field(default=0.0, ge=0.0, le=1.0)
    expected_latency_ms: Optional[int] = Field(default=None, ge=0)
    metadata_locator: Dict[str, Any] = Field(default_factory=dict)


class UQLTask(BaseModel):
    task_id: str
    agenda_id: str
    operation: ActionType
    purpose: str
    source_id: str
    source_type: SourceType
    depends_on: List[str] = Field(default_factory=list)
    metadata_query: Dict[str, Any] = Field(default_factory=dict)
    retrieval_query: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=50, ge=1)
    required: bool = True


class RetrievalPlan(BaseModel):
    plan_id: str
    query: str
    tasks: List[UQLTask]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Provenance(BaseModel):
    source_id: str
    source_type: SourceType
    locator: Dict[str, Any]
    observation_time: Optional[datetime] = None
    publication_time: Optional[datetime] = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)


class Evidence(BaseModel):
    evidence_id: str
    agenda_id: str
    evidence_type: EvidenceType
    claim: str
    content: Any
    authority: Authority
    provenance: Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    derived_from: List[str] = Field(default_factory=list)


class AgendaState(BaseModel):
    agenda_id: str
    status: AgendaStatus = AgendaStatus.PENDING
    evidence_ids: List[str] = Field(default_factory=list)
    satisfied_requirements: List[str] = Field(default_factory=list)
    missing_requirements: List[str] = Field(default_factory=list)
    attempts: int = Field(default=0, ge=0)
    last_error: Optional[str] = None


class ResearchState(BaseModel):
    request: QueryRequest
    graph: AgendaGraph
    plan: Optional[RetrievalPlan] = None
    agenda_states: Dict[str, AgendaState] = Field(default_factory=dict)
    evidence: List[Evidence] = Field(default_factory=list)
