"""
Renderer abstraction for the video pipeline.

`MockCompositorRenderer` produces deterministic placeholder output now, while the
interface is designed for drop-in FFmpeg/AI renderers later.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from typing import Any

from worker.config import settings


class BaseRenderer(ABC):
    engine_name: str

    @abstractmethod
    def render(
        self,
        *,
        video_id: str,
        audio_url: str,
        timeline: list[dict[str, Any]],
    ) -> tuple[str, float]:
        """Render timeline into an output video URL and duration."""
        ...


class MockCompositorRenderer(BaseRenderer):
    engine_name = "mock-compositor-v1"

    def render(
        self,
        *,
        video_id: str,
        audio_url: str,
        timeline: list[dict[str, Any]],
    ) -> tuple[str, float]:
        # Deterministic placeholder URL derived from render input hash.
        fingerprint = hashlib.sha256(
            json.dumps(
                {"video_id": video_id, "audio_url": audio_url, "timeline": timeline},
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()[:16]
        duration = 0.0
        if timeline:
            duration = max((float(row["start_seconds"]) + float(row["duration_seconds"])) for row in timeline)
        return (
            f"{settings.mock_media_base_url}/video/{video_id}/{fingerprint}-{uuid.uuid4().hex[:8]}.mp4",
            round(duration, 2),
        )


def get_renderer(engine: str | None) -> BaseRenderer:
    # Future engines:
    # - ffmpeg-compositor-v1
    # - runwayml-v1
    # - pika-labs-v1
    if not engine or engine == "mock-compositor-v1":
        return MockCompositorRenderer()
    raise ValueError(f"Unsupported render engine: {engine}")

