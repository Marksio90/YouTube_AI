from app.core.celery import celery_client


def enqueue_sync_analytics(*, channel_id: str, date_str: str) -> str:
    result = celery_client.send_task(
        "worker.tasks.analytics.sync_channel",
        kwargs={"channel_id": channel_id, "date": date_str},
        queue="default",
    )
    return result.id


def enqueue_sync_publication_analytics(*, publication_id: str, date_str: str) -> str:
    result = celery_client.send_task(
        "worker.tasks.analytics.sync_publication",
        kwargs={"publication_id": publication_id, "date": date_str},
        queue="default",
    )
    return result.id
