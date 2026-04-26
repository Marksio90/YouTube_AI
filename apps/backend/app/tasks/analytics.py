from app.core.celery import send_task


def enqueue_sync_analytics(*, channel_id: str, date_str: str) -> str:
    result = send_task(task_name="worker.tasks.analytics.sync_channel",
        kwargs={"channel_id": channel_id, "date": date_str},
        queue="analytics",
    )
    return result.id


def enqueue_sync_publication_analytics(*, publication_id: str, date_str: str) -> str:
    result = send_task(task_name="worker.tasks.analytics.sync_publication",
        kwargs={"publication_id": publication_id, "date": date_str},
        queue="analytics",
    )
    return result.id
