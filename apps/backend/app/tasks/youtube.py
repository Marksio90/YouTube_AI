from app.core.celery import send_task


def enqueue_upload(*, publication_id: str) -> str:
    result = send_task(
        task_name="worker.tasks.youtube.upload_video",
        kwargs={"publication_id": publication_id},
        queue="default",
    )
    return result.id


def enqueue_publish_pipeline(
    *,
    publication_id: str,
    media_url: str,
    audio_url: str | None = None,
    thumbnail_url: str | None = None,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    visibility: str | None = None,
) -> str:
    result = send_task(
        task_name="worker.tasks.youtube.publish_video_pipeline",
        kwargs={
            "publication_id": publication_id,
            "media_url": media_url,
            "audio_url": audio_url,
            "thumbnail_url": thumbnail_url,
            "title": title,
            "description": description,
            "tags": tags or [],
            "visibility": visibility,
        },
        queue="default",
    )
    return result.id


def enqueue_sync_metrics(*, channel_id: str) -> str:
    result = send_task(
        task_name="worker.tasks.youtube.sync_channel_metrics",
        kwargs={"channel_id": channel_id},
        queue="default",
    )
    return result.id
