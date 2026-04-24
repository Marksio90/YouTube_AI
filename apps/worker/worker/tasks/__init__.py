"""
Import all task modules so Celery autodiscovery can register them.
Order matters only insofar as there are no circular imports — keep alphabetical.
"""

from worker.tasks import ai  # noqa: F401
from worker.tasks import analytics  # noqa: F401
from worker.tasks import media  # noqa: F401
from worker.tasks import pipeline  # noqa: F401
from worker.tasks import recommendations  # noqa: F401
from worker.tasks import scoring  # noqa: F401
from worker.tasks import topics  # noqa: F401
from worker.tasks import workflow  # noqa: F401
from worker.tasks import youtube  # noqa: F401

__all__ = ["ai", "analytics", "media", "pipeline", "recommendations", "scoring", "topics", "workflow", "youtube"]
