from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnnouncementDigest(BaseModel):
    """Validated structure for one campus announcement."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    announcement_type: Literal[
        "deadline",
        "schedule_change",
        "required_action",
        "general_update",
    ]

    summary_title: str = Field(max_length=80)

    required_action: str = "Not specified"

    date_or_deadline: str = "Not specified"

    urgency_level: Literal["HIGH", "MEDIUM", "LOW"]

    ranking_reason: str

    confidence_score: float = Field(ge=0.0, le=1.0)

    source_url: str = ""
