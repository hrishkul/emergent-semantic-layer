import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

VERTICALS = ("sales", "finance", "inventory", "procurement", "production")


class DebateSpecError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class ModelSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: Literal["open-weight", "closed-weight"]
    heterogeneity: Literal["homogeneous", "heterogeneous"]
    api: Literal["openai-compatible"]
    provider: str | None = None
    model_id: str | None = None


class Debater(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z-]{0,31}$")
    background: str = Field(min_length=1)
    stance: str = Field(min_length=1)


class Materialization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: Literal[1]
    slice: Literal["sales"]
    shared_foundation: Literal[True]


class Participants(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: ModelSlot
    debaters: list[Debater] = Field(min_length=1)
    summarizer_id: Literal["summarizer"]
    judge_id: Literal["judge"]
    persona_heterogeneity: Literal["homogeneous", "heterogeneous"]
    persona_assignment: Literal["manual", "automatic", "unspecified"]
    persona_attributes: list[Literal["background", "stance", "personality"]]


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1, le=4)
    src: list[str] = Field(min_length=1)
    dst: list[str] = Field(min_length=1)
    content: Literal["verbatim", "summarized"]


class Interaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adaptability: Literal["static", "dynamic"]
    structure: Literal[
        "fully_connected",
        "grouped",
        "sparse",
        "chain",
        "ring",
        "star",
        "tree",
        "layered",
        "bipartite",
    ]
    mechanism: Literal["sequential", "simultaneous", "hybrid"]
    syntax: Literal["natural_language"]
    memory: list[Literal["short-term", "long-term", "retrieval", "parametric"]]
    rounds: int = Field(ge=1, le=4)
    edges: list[Edge] = Field(min_length=1)


class Agreement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    debate_authority: Literal["collective", "judge", "hybrid"]
    resolution: Literal[
        "argument_evaluation",
        "majority_vote",
        "weighted_vote",
        "scoring",
        "average",
        "consensus",
    ]
    preserve_cited_dissent: bool


class Promotion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["human", "judge", "collective"]
    policy: Literal["human_required"]


class Budgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_seconds: int = Field(ge=1)
    max_usd: int = Field(ge=1)


class Gates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exception_recall_min: float = Field(ge=0, le=1)
    stability_runs: int = Field(ge=1)
    stability_min: float = Field(ge=0, le=1)


class DebateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    scope: Literal["cross_vertical"]
    materialization: Materialization
    paper: str = Field(min_length=10)
    participants: Participants
    interaction: Interaction
    agreement: Agreement
    promotion: Promotion
    budgets: Budgets
    gates: Gates


def parse_debate_spec(data: bytes) -> DebateSpec:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise DebateSpecError([f"debate spec is not json: {exc.msg}"]) from exc
    try:
        spec = DebateSpec.model_validate(payload)
    except ValidationError as exc:
        raise DebateSpecError([err["msg"] for err in exc.errors()]) from exc
    enforce_framework(spec)
    return spec


def enforce_framework(spec: DebateSpec) -> None:
    """Reject a sales-only panel and the dominant MAD pattern.

    Phase 1 materializes the sales slice. The debate still seats every vertical,
    because the ontology is the settlement of their disagreement. A vote among
    sales-only roles collapses that settlement into a sales star schema.
    """

    errors: list[str] = []
    participants = spec.participants
    interaction = spec.interaction
    if spec.scope != "cross_vertical":
        errors.append("the debate is cross-vertical")
    if spec.materialization.slice != "sales" or not spec.materialization.shared_foundation:
        errors.append("phase 1 materializes sales plus shared foundation")
    if participants.model.family != "open-weight":
        errors.append("model family must be open-weight")
    if participants.model.heterogeneity != "homogeneous":
        errors.append("one model for every role, so a miss is attributable to the protocol")
    if participants.model.provider is not None or participants.model.model_id is not None:
        errors.append("provider and model id stay empty until Phase 1")
    ids = [debater.id for debater in participants.debaters]
    if sorted(ids) != sorted(VERTICALS):
        errors.append(
            "debaters are the five verticals: sales, finance, inventory, procurement, production"
        )
    if participants.persona_heterogeneity != "heterogeneous":
        errors.append("personas must be heterogeneous")
    if participants.persona_assignment != "manual":
        errors.append("personas are assigned manually")
    if "stance" not in participants.persona_attributes:
        errors.append("stance is required; personality traits are not a substitute")
    if "personality" in participants.persona_attributes:
        errors.append("personality traits stay out of this spec")
    if interaction.adaptability != "static":
        errors.append("topology stays static so the token budget is knowable")
    if interaction.structure != "sparse":
        errors.append("structure must be sparse, not fully connected")
    if interaction.mechanism != "hybrid":
        errors.append("round 1 is simultaneous and the critique round follows")
    if set(interaction.memory) != {"short-term", "retrieval"}:
        errors.append("memory is short-term plus retrieval, with no long-term store")
    if interaction.rounds != 2:
        errors.append("two debate rounds")
    contents = {edge.content for edge in interaction.edges}
    if "verbatim" not in contents or "summarized" not in contents:
        errors.append("claims travel verbatim; only the digest is summarized")
    step_one = [edge for edge in interaction.edges if edge.step == 1]
    if not step_one:
        errors.append("step 1 must exist")
    for edge in step_one:
        if set(edge.dst) - {"judge", "summarizer"}:
            errors.append("step 1 does not let debaters read each other")
        if edge.content != "verbatim":
            errors.append("step 1 claims are verbatim")
    claim_sources: set[str] = set()
    critique_sources: set[str] = set()
    saw_claim_broadcast = False
    for edge in interaction.edges:
        if edge.step == 1 and edge.content == "verbatim":
            claim_sources.update(edge.src)
        if edge.step == 2 and edge.src == ["judge"] and edge.content == "verbatim":
            if set(edge.dst) >= set(VERTICALS):
                saw_claim_broadcast = True
        if edge.step == 2 and "judge" in edge.dst and edge.content == "verbatim":
            critique_sources.update(edge.src)
    critique_sources.discard("judge")
    if claim_sources != set(VERTICALS):
        errors.append("round 1 is a claim from every vertical")
    if not saw_claim_broadcast:
        errors.append("round 2 starts from the verbatim claim list, not from a digest")
    if critique_sources != set(VERTICALS):
        errors.append("round 2 is every vertical critiquing the shared claim list")
    if spec.agreement.debate_authority != "judge":
        errors.append("the judge writes the proposal")
    if spec.agreement.resolution != "argument_evaluation":
        errors.append("resolution is argument evaluation, not a vote or a forced consensus")
    if not spec.agreement.preserve_cited_dissent:
        errors.append("cited dissent is kept")
    if spec.promotion.authority != "human" or spec.promotion.policy != "human_required":
        errors.append("a person promotes the proposal")
    if spec.budgets.max_seconds != 900 or spec.budgets.max_usd != 8:
        errors.append("one debate stays under 15 minutes and under $8")
    if (
        spec.gates.exception_recall_min != 0.7
        or spec.gates.stability_runs != 3
        or spec.gates.stability_min != 0.75
    ):
        errors.append("gates are recall 0.70, stability 0.75 across 3 runs")
    if errors:
        raise DebateSpecError(errors)
