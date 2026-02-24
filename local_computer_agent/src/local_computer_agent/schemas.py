from __future__ import annotations

from typing import Literal, Optional, Tuple

from pydantic import BaseModel, Field


class AgentAction(BaseModel):
    action_type: Literal["click", "type", "drag", "scroll", "wait"]
    coordinates: Optional[Tuple[int, int]] = Field(
        default=None,
        description="Screen coordinates in absolute pixels (x, y). Required for click/drag.",
    )
    payload: Optional[str] = Field(
        default=None,
        description="Text to type, key combo (e.g. 'ctrl+s'), or scroll amount.",
    )
    expected_outcome: str = Field(
        description="Natural language description, e.g. 'A login success message appears'."
    )
    critical: bool = Field(
        default=False,
        description=(
            "If true, always trigger Tier 2 verification in addition to Tier 1, "
            "suitable for irreversible/high-impact actions."
        ),
    )


class Tier1Result(BaseModel):
    changed: bool
    hamming_distance: int
    status: Literal["passed", "no_change", "unexpected_change"]


class Tier2Result(BaseModel):
    success: bool
    reasoning: str


