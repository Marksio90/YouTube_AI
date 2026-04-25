import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ThumbnailRead(BaseModel):
    id: uuid.UUID
    publication_id: uuid.UUID
    channel_id: uuid.UUID
    ab_group_id: uuid.UUID
    variant_index: int
    status: str
    image_provider: str
    image_url: str | None
    concept_id: str
    headline_text: str
    sub_text: str | None
    layout: str
    color_scheme: dict[str, Any]
    composition: str | None
    visual_elements: list[str]
    ai_image_prompt: str
    predicted_ctr_score: float
    channel_style: str
    impressions: int
    clicks: int
    actual_ctr: float | None
    is_winner: bool
    is_active: bool
    task_id: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Any) -> "ThumbnailRead":
        impressions = row["impressions"] or 0
        clicks = row["clicks"] or 0
        actual_ctr = round(clicks / impressions, 4) if impressions > 0 else None
        return cls(
            id=row["id"],
            publication_id=row["publication_id"],
            channel_id=row["channel_id"],
            ab_group_id=row["ab_group_id"],
            variant_index=row["variant_index"],
            status=row["status"],
            image_provider=row["image_provider"],
            image_url=row["image_url"],
            concept_id=row["concept_id"],
            headline_text=row["headline_text"],
            sub_text=row["sub_text"],
            layout=row["layout"],
            color_scheme=row["color_scheme"] or {},
            composition=row["composition"],
            visual_elements=row["visual_elements"] or [],
            ai_image_prompt=row["ai_image_prompt"],
            predicted_ctr_score=row["predicted_ctr_score"] or 0.0,
            channel_style=row["channel_style"],
            impressions=impressions,
            clicks=clicks,
            actual_ctr=actual_ctr,
            is_winner=row["is_winner"],
            is_active=row["is_active"],
            task_id=row["task_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    model_config = {"from_attributes": True}


class ThumbnailGenerateRequest(BaseModel):
    channel_style: str = Field(
        default="clean_modern",
        pattern="^(clean_modern|bold_contrast|minimal|dark_premium|colorful_pop)$",
    )
    count: int = Field(default=3, ge=1, le=5)


class ABGroupRead(BaseModel):
    ab_group_id: uuid.UUID
    publication_id: uuid.UUID
    variants: list[ThumbnailRead]
    winner: ThumbnailRead | None
    total_impressions: int
    total_clicks: int
    min_impressions_for_significance: int = 500


class SelectWinnerRequest(BaseModel):
    thumbnail_id: uuid.UUID
