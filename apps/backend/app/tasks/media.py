from app.core.celery import send_task


def enqueue_render_video(
    *,
    video_id: str,
    audio_url: str,
    scene_plan: list[dict],
    assets: list[dict],
    engine: str = "mock-compositor-v1",
) -> str:
    result = send_task(
        task_name="worker.tasks.media.render_video",
        kwargs={
            "video_id": video_id,
            "audio_url": audio_url,
            "scene_plan": scene_plan,
            "assets": assets,
            "engine": engine,
        },
        queue="media",
    )
    return result.id

