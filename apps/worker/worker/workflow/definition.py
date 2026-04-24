"""
Pipeline definitions — the declarative spec for every workflow.

A PipelineDef is an immutable, serialisable description of a DAG of steps.
The engine reads it; it never mutates it.

To add a new pipeline:
    1. Build a PipelineDef with the steps
    2. Register it: PIPELINE_REGISTRY["my_pipeline"] = my_pipeline
    3. Trigger a WorkflowRun with pipeline_name="my_pipeline"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worker.workflow.exceptions import PipelineNotFoundError, StepNotFoundError
from worker.workflow.types import FailPolicy


# ── Step ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StepDef:
    """Declarative description of one step in a pipeline."""

    step_id:   str           # Unique slug within the pipeline: "generate_script"
    step_type: str           # Maps to a BaseWorkflowJob subclass: "script"
    depends_on: tuple[str, ...] = field(default_factory=tuple)

    fail_policy:          FailPolicy = FailPolicy.fail_run
    max_retries:          int        = 3
    retry_delay_seconds:  float      = 30.0
    timeout_seconds:      float      = 600.0   # Per-attempt timeout

    # Passed verbatim to BaseWorkflowJob.build_payload() as extra config
    config: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.depends_on, list):
            object.__setattr__(self, "depends_on", tuple(self.depends_on))


# ── Pipeline ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PipelineDef:
    """An immutable, ordered DAG of steps."""

    name:    str
    version: str
    steps:   tuple[StepDef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if isinstance(self.steps, list):
            object.__setattr__(self, "steps", tuple(self.steps))

    def get_step(self, step_id: str) -> StepDef:
        for s in self.steps:
            if s.step_id == step_id:
                return s
        raise StepNotFoundError(step_id, self.name)

    def topological_order(self) -> list[StepDef]:
        """
        Kahn's algorithm — returns steps in a valid execution order.
        Raises ValueError if the DAG has a cycle (should never happen for our pipelines).
        """
        in_degree: dict[str, int] = {s.step_id: 0 for s in self.steps}
        adjacency: dict[str, list[str]] = {s.step_id: [] for s in self.steps}

        for step in self.steps:
            for dep in step.depends_on:
                if dep not in in_degree:
                    raise StepNotFoundError(dep, self.name)
                adjacency[dep].append(step.step_id)
                in_degree[step.step_id] += 1

        queue = [s for s in self.steps if in_degree[s.step_id] == 0]
        ordered: list[StepDef] = []
        step_map = {s.step_id: s for s in self.steps}

        while queue:
            current = queue.pop(0)
            ordered.append(current)
            for neighbor_id in adjacency[current.step_id]:
                in_degree[neighbor_id] -= 1
                if in_degree[neighbor_id] == 0:
                    queue.append(step_map[neighbor_id])

        if len(ordered) != len(self.steps):
            raise ValueError(f"Pipeline '{self.name}' contains a cycle")

        return ordered

    def ready_steps(
        self,
        done: set[str],
        failed: set[str],
    ) -> list[StepDef]:
        """Steps whose dependencies are all satisfied (completed or skipped)."""
        return [
            s for s in self.steps
            if s.step_id not in done and s.step_id not in failed
            and all(d in done for d in s.depends_on)
        ]


# ── Built-in pipelines ────────────────────────────────────────────────────────
#
# Pipeline: topic → brief → script → compliance → audio + visuals → thumbnail
#           → metadata → publication → analytics → optimization

YOUTUBE_PIPELINE = PipelineDef(
    name    = "youtube_content",
    version = "1.0",
    steps   = (
        # ── Stage 1: Research ────────────────────────────────────────────────
        StepDef(
            step_id    = "generate_brief",
            step_type  = "brief",
            depends_on = (),
            fail_policy         = FailPolicy.fail_run,
            max_retries         = 3,
            retry_delay_seconds = 30.0,
            timeout_seconds     = 400.0,
        ),

        # ── Stage 2: Script production ───────────────────────────────────────
        StepDef(
            step_id    = "generate_script",
            step_type  = "script",
            depends_on = ("generate_brief",),
            fail_policy         = FailPolicy.fail_run,
            max_retries         = 3,
            retry_delay_seconds = 60.0,
            timeout_seconds     = 600.0,
        ),

        # ── Stage 3: Compliance gate ─────────────────────────────────────────
        StepDef(
            step_id    = "check_compliance",
            step_type  = "compliance",
            depends_on = ("generate_script",),
            fail_policy         = FailPolicy.fail_run,
            max_retries         = 2,
            retry_delay_seconds = 30.0,
            timeout_seconds     = 300.0,
        ),

        # ── Stage 4a: Audio (can skip if TTS fails) ──────────────────────────
        StepDef(
            step_id    = "generate_audio",
            step_type  = "audio",
            depends_on = ("check_compliance",),
            fail_policy         = FailPolicy.skip,
            max_retries         = 2,
            retry_delay_seconds = 60.0,
            timeout_seconds     = 600.0,
        ),

        # ── Stage 4b: Visuals (can skip if image gen fails) ──────────────────
        StepDef(
            step_id    = "generate_visuals",
            step_type  = "visuals",
            depends_on = ("check_compliance",),
            fail_policy         = FailPolicy.skip,
            max_retries         = 2,
            retry_delay_seconds = 60.0,
            timeout_seconds     = 600.0,
        ),

        # ── Stage 5: Thumbnail (depends on visuals; skipped if visuals skipped)
        StepDef(
            step_id    = "generate_thumbnail",
            step_type  = "thumbnail",
            depends_on = ("generate_visuals",),
            fail_policy         = FailPolicy.skip,
            max_retries         = 2,
            retry_delay_seconds = 30.0,
            timeout_seconds     = 400.0,
        ),

        # ── Stage 6: SEO metadata (non-blocking; continues on failure) ────────
        StepDef(
            step_id    = "generate_metadata",
            step_type  = "metadata",
            depends_on = ("generate_script",),
            fail_policy         = FailPolicy.continue_,
            max_retries         = 2,
            retry_delay_seconds = 30.0,
            timeout_seconds     = 300.0,
        ),

        # ── Stage 7: Publish (requires compliance + audio + thumbnail + meta) ─
        StepDef(
            step_id    = "publish",
            step_type  = "publication",
            depends_on = (
                "check_compliance",
                "generate_audio",
                "generate_thumbnail",
                "generate_metadata",
            ),
            fail_policy         = FailPolicy.fail_run,
            max_retries         = 3,
            retry_delay_seconds = 120.0,
            timeout_seconds     = 900.0,
            config              = {"privacy_status": "private"},
        ),

        # ── Stage 8: Analytics sync (best-effort) ────────────────────────────
        StepDef(
            step_id    = "sync_analytics",
            step_type  = "analytics",
            depends_on = ("publish",),
            fail_policy         = FailPolicy.continue_,
            max_retries         = 2,
            retry_delay_seconds = 60.0,
            timeout_seconds     = 300.0,
        ),

        # ── Stage 9: AI optimisation recommendations (best-effort) ───────────
        StepDef(
            step_id    = "optimize",
            step_type  = "optimization",
            depends_on = ("sync_analytics",),
            fail_policy         = FailPolicy.continue_,
            max_retries         = 1,
            retry_delay_seconds = 30.0,
            timeout_seconds     = 300.0,
        ),
    ),
)


# ── Registry ──────────────────────────────────────────────────────────────────

PIPELINE_REGISTRY: dict[str, PipelineDef] = {
    "youtube_content": YOUTUBE_PIPELINE,
}


def get_pipeline(name: str) -> PipelineDef:
    try:
        return PIPELINE_REGISTRY[name]
    except KeyError:
        raise PipelineNotFoundError(name)


def register_pipeline(pipeline: PipelineDef) -> None:
    PIPELINE_REGISTRY[pipeline.name] = pipeline
