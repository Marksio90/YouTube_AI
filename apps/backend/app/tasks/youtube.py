from app.core.celery import celery_client


def enqueue_upload(*, publication_id: str) -> str:
    result = celery_client.send_task(
        "worker.tasks.youtube.upload_video",
        kwargs={"video_id": publication_id},
        queue="default",
    )
    return result.id


def enqueue_sync_metrics(*, channel_id: str) -> str:
    result = celery_client.send_task(
        "worker.tasks.youtube.sync_channel_metrics",
        kwargs={"channel_id": channel_id},
        queue="default",
    )
    return result.id
