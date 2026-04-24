"""
WorkflowContext — typed, mergeable view of the shared state dict.

The context starts with the run's input, grows as jobs complete, and is
persisted to workflow_runs.context (JSONB) after every step.

Design:
  - Wraps a plain dict; the dict is what's stored in the DB
  - required() raises ContextKeyMissingError rather than KeyError so the
    engine can produce a clear diagnostic instead of a bare exception
  - merge() is append-only: later outputs override earlier ones for the same key
  - Typed shortcuts for the keys used by built-in jobs
"""
from __future__ import annotations

from typing import Any

from worker.workflow.exceptions import ContextKeyMissingError


class WorkflowContext:
    """Thread-safe-ish wrapper. Not thread-safe; designed for single-coroutine use."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data or {})

    # ── Core access ───────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def require(self, key: str, step_id: str = "unknown") -> Any:
        """Return the value or raise ContextKeyMissingError."""
        if key not in self._data:
            raise ContextKeyMissingError(key, step_id)
        return self._data[key]

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def merge(self, output: dict[str, Any]) -> None:
        """Merge a job's output into the shared context. Later values win."""
        self._data.update(output)

    def snapshot(self) -> dict[str, Any]:
        """Return a copy suitable for JSON serialisation."""
        return dict(self._data)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        keys = sorted(self._data.keys())
        return f"WorkflowContext(keys={keys})"

    # ── Typed shortcuts for built-in pipeline keys ─────────────────────────────

    @property
    def channel_id(self) -> str:
        return str(self._data.get("channel_id", ""))

    @property
    def topic_id(self) -> str | None:
        v = self._data.get("topic_id")
        return str(v) if v else None

    @property
    def brief_id(self) -> str | None:
        v = self._data.get("brief_id")
        return str(v) if v else None

    @property
    def script_id(self) -> str | None:
        v = self._data.get("script_id")
        return str(v) if v else None

    @property
    def publication_id(self) -> str | None:
        v = self._data.get("publication_id")
        return str(v) if v else None

    @property
    def audio_url(self) -> str | None:
        return self._data.get("audio_url")

    @property
    def thumbnail_url(self) -> str | None:
        return self._data.get("thumbnail_url")

    @property
    def youtube_video_id(self) -> str | None:
        return self._data.get("youtube_video_id")
