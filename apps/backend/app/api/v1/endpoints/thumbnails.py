"""
Thumbnail API — generation, A/B variant management, scoring.

Routes:
  POST /publications/{id}/thumbnails/generate   enqueue thumbnail generation
  GET  /publications/{id}/thumbnails            list variants
  GET  /thumbnails/{id}                         single thumbnail
  GET  /thumbnails/ab-groups/{ab_group_id}      full A/B group with scoring
  POST /thumbnails/{id}/impression              record impression (A/B tracking)
  POST /thumbnails/{id}/click                   record click (A/B tracking)
  POST /thumbnails/ab-groups/{ab_group_id}/select-winner  declare winner
"""
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.api.v1.deps import CurrentUser, DB
from app.schemas.common import TaskResponse
from app.schemas.thumbnail import (
    ABGroupRead,
    SelectWinnerRequest,
    ThumbnailGenerateRequest,
    ThumbnailRead,
)
from app.tasks.ai import enqueue_generate_thumbnails

router = APIRouter(tags=["thumbnails"])

_MIN_IMPRESSIONS = 500  # minimum per variant before auto-winner selection


# ── generation ────────────────────────────────────────────────────────────────

@router.post(
    "/publications/{publication_id}/thumbnails/generate",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_thumbnails(
    publication_id: uuid.UUID,
    payload: ThumbnailGenerateRequest,
    current_user: CurrentUser,
    db: DB,
) -> TaskResponse:
    pub = (
        await db.execute(
            text("""
                SELECT p.id FROM publications p
                JOIN channels c ON c.id=p.channel_id
                WHERE p.id=:pub_id AND c.organization_id=:org_id
            """),
            {"pub_id": str(publication_id), "org_id": str(current_user.organization_id)},
        )
    ).one_or_none()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")

    task_id = enqueue_generate_thumbnails(
        publication_id=str(publication_id),
        channel_style=payload.channel_style,
        count=payload.count,
    )
    return TaskResponse(task_id=task_id, status="queued")


# ── list variants ─────────────────────────────────────────────────────────────

@router.get(
    "/publications/{publication_id}/thumbnails",
    response_model=list[ThumbnailRead],
)
async def list_thumbnails(
    publication_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> list[ThumbnailRead]:
    rows = (
        await db.execute(
            text("""
                SELECT t.* FROM thumbnails t
                JOIN publications p ON p.id=t.publication_id
                JOIN channels c ON c.id=p.channel_id
                WHERE t.publication_id=:pub_id
                  AND c.organization_id=:org_id
                  AND t.status != 'archived'
                ORDER BY t.variant_index, t.created_at
            """),
            {"pub_id": str(publication_id), "org_id": str(current_user.organization_id)},
        )
    ).mappings().all()
    return [ThumbnailRead.from_row(r) for r in rows]


# ── single thumbnail ──────────────────────────────────────────────────────────

@router.get("/thumbnails/{thumbnail_id}", response_model=ThumbnailRead)
async def get_thumbnail(
    thumbnail_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> ThumbnailRead:
    row = (
        await db.execute(
            text("""
                SELECT t.* FROM thumbnails t
                JOIN publications p ON p.id=t.publication_id
                JOIN channels c ON c.id=p.channel_id
                WHERE t.id=:thumb_id AND c.organization_id=:org_id
            """),
            {"thumb_id": str(thumbnail_id), "org_id": str(current_user.organization_id)},
        )
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return ThumbnailRead.from_row(row)


# ── A/B group view ────────────────────────────────────────────────────────────

@router.get("/thumbnails/ab-groups/{ab_group_id}", response_model=ABGroupRead)
async def get_ab_group(
    ab_group_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> ABGroupRead:
    rows = (
        await db.execute(
            text("""
                SELECT t.* FROM thumbnails t
                JOIN publications p ON p.id=t.publication_id
                JOIN channels c ON c.id=p.channel_id
                WHERE t.ab_group_id=:group_id
                  AND c.organization_id=:org_id
                  AND t.status != 'archived'
                ORDER BY t.variant_index
            """),
            {"group_id": str(ab_group_id), "org_id": str(current_user.organization_id)},
        )
    ).mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail="A/B group not found")

    variants = [ThumbnailRead.from_row(r) for r in rows]
    winner = next((v for v in variants if v.is_winner), None)
    total_impressions = sum(v.impressions for v in variants)
    total_clicks = sum(v.clicks for v in variants)

    return ABGroupRead(
        ab_group_id=ab_group_id,
        publication_id=variants[0].publication_id,
        variants=variants,
        winner=winner,
        total_impressions=total_impressions,
        total_clicks=total_clicks,
    )


# ── scoring events ────────────────────────────────────────────────────────────

@router.post("/thumbnails/{thumbnail_id}/impression", status_code=status.HTTP_204_NO_CONTENT)
async def record_impression(
    thumbnail_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    result = await db.execute(
        text("""
            UPDATE thumbnails t SET impressions=impressions+1, updated_at=NOW()
            FROM publications p JOIN channels c ON c.id=p.channel_id
            WHERE t.id=:thumb_id
              AND t.publication_id=p.id
              AND c.organization_id=:org_id
        """),
        {"thumb_id": str(thumbnail_id), "org_id": str(current_user.organization_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Thumbnail not found")


@router.post("/thumbnails/{thumbnail_id}/click", status_code=status.HTTP_204_NO_CONTENT)
async def record_click(
    thumbnail_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> None:
    result = await db.execute(
        text("""
            UPDATE thumbnails t SET clicks=clicks+1, updated_at=NOW()
            FROM publications p JOIN channels c ON c.id=p.channel_id
            WHERE t.id=:thumb_id
              AND t.publication_id=p.id
              AND c.organization_id=:org_id
        """),
        {"thumb_id": str(thumbnail_id), "org_id": str(current_user.organization_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Thumbnail not found")


# ── winner selection ──────────────────────────────────────────────────────────

@router.post("/thumbnails/ab-groups/{ab_group_id}/select-winner", response_model=ThumbnailRead)
async def select_winner(
    ab_group_id: uuid.UUID,
    payload: SelectWinnerRequest,
    current_user: CurrentUser,
    db: DB,
) -> ThumbnailRead:
    """Declare a winner for an A/B group. Archives all other variants."""
    rows = (
        await db.execute(
            text("""
                SELECT t.id FROM thumbnails t
                JOIN publications p ON p.id=t.publication_id
                JOIN channels c ON c.id=p.channel_id
                WHERE t.ab_group_id=:group_id AND c.organization_id=:org_id
            """),
            {"group_id": str(ab_group_id), "org_id": str(current_user.organization_id)},
        )
    ).mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail="A/B group not found")

    ids = [str(r["id"]) for r in rows]
    if str(payload.thumbnail_id) not in ids:
        raise HTTPException(status_code=400, detail="thumbnail_id not in this A/B group")

    # Archive losers, mark winner
    await db.execute(
        text("""
            UPDATE thumbnails
            SET status='archived', is_active=false, is_winner=false, updated_at=NOW()
            WHERE ab_group_id=:group_id AND id!=:winner_id
        """),
        {"group_id": str(ab_group_id), "winner_id": str(payload.thumbnail_id)},
    )
    await db.execute(
        text("""
            UPDATE thumbnails
            SET is_winner=true, is_active=true, updated_at=NOW()
            WHERE id=:winner_id
        """),
        {"winner_id": str(payload.thumbnail_id)},
    )

    # Sync winner URL to publication
    await db.execute(
        text("""
            UPDATE publications p SET thumbnail_url=t.image_url, updated_at=NOW()
            FROM thumbnails t
            WHERE t.id=:winner_id AND t.publication_id=p.id
        """),
        {"winner_id": str(payload.thumbnail_id)},
    )

    winner_row = (
        await db.execute(
            text("SELECT * FROM thumbnails WHERE id=:id"),
            {"id": str(payload.thumbnail_id)},
        )
    ).mappings().one()
    return ThumbnailRead.from_row(winner_row)


# ── auto-select winner by CTR ─────────────────────────────────────────────────

@router.post(
    "/thumbnails/ab-groups/{ab_group_id}/auto-select-winner",
    response_model=ThumbnailRead,
)
async def auto_select_winner(
    ab_group_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
) -> ThumbnailRead:
    """Pick winner by highest actual CTR (requires ≥500 impressions per variant)."""
    rows = (
        await db.execute(
            text("""
                SELECT t.* FROM thumbnails t
                JOIN publications p ON p.id=t.publication_id
                JOIN channels c ON c.id=p.channel_id
                WHERE t.ab_group_id=:group_id
                  AND c.organization_id=:org_id
                  AND t.status='ready'
                ORDER BY t.variant_index
            """),
            {"group_id": str(ab_group_id), "org_id": str(current_user.organization_id)},
        )
    ).mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail="No ready variants in this A/B group")

    variants = [ThumbnailRead.from_row(r) for r in rows]

    under_threshold = [v for v in variants if v.impressions < _MIN_IMPRESSIONS]
    if under_threshold:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not enough data. "
                f"{len(under_threshold)} variant(s) below {_MIN_IMPRESSIONS} impressions. "
                f"Minimum per variant required for statistical significance."
            ),
        )

    # Rank by actual CTR desc, then predicted_ctr_score as tiebreaker
    best = max(
        variants,
        key=lambda v: (v.actual_ctr or 0.0, v.predicted_ctr_score),
    )

    # Delegate to select_winner endpoint logic
    return await select_winner(
        ab_group_id=ab_group_id,
        payload=SelectWinnerRequest(thumbnail_id=best.id),
        current_user=current_user,
        db=db,
    )
