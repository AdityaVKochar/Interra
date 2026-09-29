from typing import Protocol
from ..models import Model, State, ToolSpec
from pydantic import Field, JsonValue


class PlanningContext(Model):
    state: State
    input: dict[str, JsonValue]
    tools: list[ToolSpec]
    results: dict[str, JsonValue] = Field(default_factory=dict)
    calls: dict[str, JsonValue] = Field(default_factory=dict)
    clarification: dict[str, JsonValue] = Field(default_factory=dict)


class ReasoningProvider(Protocol):
    async def plan(self, context: PlanningContext) -> dict | str: ...
