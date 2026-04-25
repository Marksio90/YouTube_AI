"""
Timeline builder foundation for future ffmpeg / AI video backends.

The builder takes:
  - scene plan
  - asset list
  - audio input metadata

and outputs an explicit timeline structure that rendering engines can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Scene:
    scene_id: str
    start_seconds: float
    duration_seconds: float
    transition: str = "cut"
    narration: str | None = None


@dataclass(slots=True)
class Asset:
    asset_id: str
    type: str
    url: str
    scene_id: str | None = None
    start_seconds: float | None = None
    duration_seconds: float | None = None


def build_timeline(
    *,
    audio_url: str,
    scene_plan: list[dict[str, Any]],
    assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scenes = [_to_scene(raw) for raw in scene_plan]
    mapped_assets = [_to_asset(raw) for raw in assets]

    _validate_scenes(scenes)
    _validate_assets(mapped_assets, scenes)

    timeline: list[dict[str, Any]] = []
    scene_lookup = {s.scene_id: s for s in scenes}

    for scene in scenes:
        scene_assets = _assets_for_scene(scene, mapped_assets)
        timeline.append(
            {
                "kind": "scene",
                "scene_id": scene.scene_id,
                "start_seconds": scene.start_seconds,
                "duration_seconds": scene.duration_seconds,
                "end_seconds": round(scene.start_seconds + scene.duration_seconds, 3),
                "transition": scene.transition,
                "narration": scene.narration,
                "audio_track": {"url": audio_url},
                "asset_tracks": [
                    {
                        "asset_id": a.asset_id,
                        "type": a.type,
                        "url": a.url,
                        "start_seconds": a.start_seconds if a.start_seconds is not None else scene.start_seconds,
                        "duration_seconds": a.duration_seconds if a.duration_seconds is not None else scene.duration_seconds,
                        "scene_id": a.scene_id or scene.scene_id,
                    }
                    for a in scene_assets
                ],
            }
        )

    timeline.sort(key=lambda x: x["start_seconds"])

    # add hard references for downstream backends
    for row in timeline:
        row["renderer_hints"] = {
            "ffmpeg": {
                "video_filter_graph": "TBD",
                "audio_filter_graph": "TBD",
            },
            "ai_video": {
                "prompt_chunks": [row.get("narration") or ""],
                "asset_binding": [t["asset_id"] for t in row["asset_tracks"]],
            },
        }
        if row["scene_id"] in scene_lookup:
            row["scene_order"] = list(scene_lookup).index(row["scene_id"])

    return timeline


def _assets_for_scene(scene: Scene, assets: list[Asset]) -> list[Asset]:
    direct = [a for a in assets if a.scene_id == scene.scene_id]
    if direct:
        return direct
    timed = []
    for a in assets:
        if a.start_seconds is None:
            continue
        a_end = a.start_seconds + (a.duration_seconds or scene.duration_seconds)
        scene_end = scene.start_seconds + scene.duration_seconds
        overlaps = not (a_end <= scene.start_seconds or a.start_seconds >= scene_end)
        if overlaps:
            timed.append(a)
    return timed


def _to_scene(raw: dict[str, Any]) -> Scene:
    return Scene(
        scene_id=str(raw["scene_id"]),
        start_seconds=float(raw["start_seconds"]),
        duration_seconds=float(raw["duration_seconds"]),
        transition=str(raw.get("transition") or "cut"),
        narration=raw.get("narration"),
    )


def _to_asset(raw: dict[str, Any]) -> Asset:
    return Asset(
        asset_id=str(raw["asset_id"]),
        type=str(raw["type"]),
        url=str(raw["url"]),
        scene_id=raw.get("scene_id"),
        start_seconds=float(raw["start_seconds"]) if raw.get("start_seconds") is not None else None,
        duration_seconds=float(raw["duration_seconds"]) if raw.get("duration_seconds") is not None else None,
    )


def _validate_scenes(scenes: list[Scene]) -> None:
    if not scenes:
        raise ValueError("scene_plan cannot be empty")
    if len({s.scene_id for s in scenes}) != len(scenes):
        raise ValueError("scene_plan contains duplicate scene_id values")
    for s in scenes:
        if s.start_seconds < 0 or s.duration_seconds <= 0:
            raise ValueError(f"invalid scene timing for {s.scene_id}")


def _validate_assets(assets: list[Asset], scenes: list[Scene]) -> None:
    allowed_types = {"image", "video", "overlay", "subtitle"}
    scene_ids = {s.scene_id for s in scenes}
    for a in assets:
        if a.type not in allowed_types:
            raise ValueError(f"unsupported asset type '{a.type}' for asset {a.asset_id}")
        if a.scene_id and a.scene_id not in scene_ids:
            raise ValueError(f"asset {a.asset_id} references unknown scene_id '{a.scene_id}'")

