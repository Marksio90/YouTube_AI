import asyncio

import structlog

from worker.celery_app import app
from worker.db import get_db_session

logger = structlog.get_logger(__name__)


@app.task(
    bind=True,
    name="worker.tasks.youtube.upload_video",
    queue="default",
    max_retries=3,
    default_retry_delay=60,
)
def upload_video_task(self, video_id: str) -> dict:
    log = logger.bind(video_id=video_id, task_id=self.request.id)
    log.info("youtube_upload.start")

    try:
        result = asyncio.run(_upload_video(video_id, log))
        return result
    except Exception as exc:
        log.error("youtube_upload.failed", error=str(exc))
        raise self.retry(exc=exc)


async def _upload_video(video_id: str, log) -> dict:
    async with get_db_session() as db:
        from sqlalchemy import text

        video = (await db.execute(
            text("""
                SELECT v.*, c.access_token_enc, c.refresh_token_enc
                FROM videos v JOIN channels c ON c.id = v.channel_id
                WHERE v.id = :id
            """),
            {"id": video_id},
        )).mappings().one_or_none()

        if not video:
            raise ValueError(f"Video {video_id} not found")

        await db.execute(
            text("UPDATE videos SET status='producing' WHERE id=:id"),
            {"id": video_id},
        )

        # YouTube upload would be implemented here with google-auth + googleapiclient
        # Placeholder: mark as scheduled
        log.info("youtube_upload.placeholder", video_id=video_id)

        await db.execute(
            text("UPDATE videos SET status='scheduled' WHERE id=:id"),
            {"id": video_id},
        )

    return {"video_id": video_id, "status": "scheduled"}
