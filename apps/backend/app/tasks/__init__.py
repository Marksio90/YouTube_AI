# Tasks are imported lazily by endpoints to avoid circular imports at startup.
# Each task module registers itself with the Celery app via @celery_app.task decorator.
