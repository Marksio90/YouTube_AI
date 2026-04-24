"""
Workflow state machine.

Defines the valid transition graph for both WorkflowRun and WorkflowJob and
exposes a single validate() call that raises InvalidTransitionError on violations.

Transition diagrams
───────────────────
WorkflowRun:
    pending ──▶ running ──▶ completed
                   │ ◀──── paused ───────────────┐
                   │                              │
                   └──▶ failed ──▶ running (retry/resume)
                   └──▶ cancelled
    pending ──▶ cancelled

WorkflowJob:
    pending ──▶ scheduled ──▶ running ──▶ completed
                                │ ◀── retrying ──┐
                                └──▶ failed ─────┘ (after retry exhausted)
                                └──▶ cancelled
    pending ──▶ skipped
    pending ──▶ cancelled
    failed  ──▶ pending  (manual retry reset)
    cancelled ──▶ pending (manual reset)
"""
from __future__ import annotations

from worker.workflow.exceptions import InvalidTransitionError
from worker.workflow.types import JobStatus, RunStatus

# ── Transition tables ─────────────────────────────────────────────────────────

_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.pending:   frozenset({RunStatus.running, RunStatus.cancelled}),
    RunStatus.running:   frozenset({RunStatus.completed, RunStatus.failed,
                                    RunStatus.paused, RunStatus.cancelled}),
    RunStatus.paused:    frozenset({RunStatus.running, RunStatus.cancelled}),
    RunStatus.failed:    frozenset({RunStatus.running}),   # resume / manual retry
    RunStatus.completed: frozenset(),                       # terminal
    RunStatus.cancelled: frozenset(),                       # terminal
}

_JOB_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.pending:   frozenset({JobStatus.scheduled, JobStatus.skipped,
                                    JobStatus.cancelled}),
    JobStatus.scheduled: frozenset({JobStatus.running, JobStatus.cancelled}),
    JobStatus.running:   frozenset({JobStatus.completed, JobStatus.retrying,
                                    JobStatus.failed, JobStatus.cancelled}),
    JobStatus.retrying:  frozenset({JobStatus.running, JobStatus.failed,
                                    JobStatus.cancelled}),
    JobStatus.failed:    frozenset({JobStatus.pending}),   # manual reset for retry
    JobStatus.completed: frozenset(),                       # terminal
    JobStatus.skipped:   frozenset(),                       # terminal
    JobStatus.cancelled: frozenset({JobStatus.pending}),   # manual reset
}


# ── Public API ────────────────────────────────────────────────────────────────

def validate_run_transition(
    current: RunStatus,
    target: RunStatus,
    run_id: str = "",
) -> None:
    """Raise InvalidTransitionError if current → target is not allowed."""
    allowed = _RUN_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(current, target, entity=f"run:{run_id}")


def validate_job_transition(
    current: JobStatus,
    target: JobStatus,
    job_id: str = "",
) -> None:
    """Raise InvalidTransitionError if current → target is not allowed."""
    allowed = _JOB_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidTransitionError(current, target, entity=f"job:{job_id}")


def run_can_transition(current: RunStatus, target: RunStatus) -> bool:
    return target in _RUN_TRANSITIONS.get(current, frozenset())


def job_can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in _JOB_TRANSITIONS.get(current, frozenset())


def run_allowed_transitions(current: RunStatus) -> frozenset[RunStatus]:
    return _RUN_TRANSITIONS.get(current, frozenset())


def job_allowed_transitions(current: JobStatus) -> frozenset[JobStatus]:
    return _JOB_TRANSITIONS.get(current, frozenset())
