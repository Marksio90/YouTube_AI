"""
Workflow type enumerations.

Every state, event, and policy in the system is represented here.
These enums are the single source of truth — use them everywhere; never raw strings.
"""
from __future__ import annotations

import enum


class RunStatus(str, enum.Enum):
    pending   = "pending"    # Created, not yet started
    running   = "running"    # At least one job executing
    paused    = "paused"     # Manually paused; no new jobs dispatched
    completed = "completed"  # All required jobs finished successfully
    failed    = "failed"     # A required job exhausted all retries
    cancelled = "cancelled"  # Manually cancelled


class JobStatus(str, enum.Enum):
    pending   = "pending"    # Waiting for dependencies or not yet dispatched
    scheduled = "scheduled"  # Celery task submitted, not yet running
    running   = "running"    # Task is actively executing
    completed = "completed"  # Task succeeded (terminal)
    failed    = "failed"     # All retries exhausted (terminal unless manually reset)
    retrying  = "retrying"   # Transient failure; waiting before next attempt
    skipped   = "skipped"    # Bypassed due to policy or dependency failure (terminal)
    cancelled = "cancelled"  # Manually cancelled (terminal)


class FailPolicy(str, enum.Enum):
    fail_run  = "fail_run"  # Abort the entire run immediately
    skip      = "skip"      # Mark this job skipped and continue
    continue_ = "continue"  # Keep job as failed and continue to next steps


class EventType(str, enum.Enum):
    # Run lifecycle
    run_created   = "run.created"
    run_started   = "run.started"
    run_paused    = "run.paused"
    run_resumed   = "run.resumed"
    run_completed = "run.completed"
    run_failed    = "run.failed"
    run_cancelled = "run.cancelled"

    # Job lifecycle
    job_scheduled = "job.scheduled"
    job_started   = "job.started"
    job_completed = "job.completed"
    job_failed    = "job.failed"
    job_retrying  = "job.retrying"
    job_skipped   = "job.skipped"
    job_cancelled = "job.cancelled"

    # Manual overrides
    manual_pause         = "manual.pause"
    manual_resume        = "manual.resume"
    manual_cancel        = "manual.cancel"
    manual_retry_run     = "manual.retry_run"
    manual_retry_job     = "manual.retry_job"
    manual_skip_job      = "manual.skip_job"
    manual_inject_result = "manual.inject_result"
    manual_patch_context = "manual.patch_context"

    # Engine events
    engine_restart = "engine.restart"


# Terminal states — once a job/run reaches these, no automatic transitions occur
JOB_TERMINAL  = frozenset({JobStatus.completed, JobStatus.failed, JobStatus.skipped, JobStatus.cancelled})
RUN_TERMINAL  = frozenset({RunStatus.completed, RunStatus.failed, RunStatus.cancelled})

# States that count as "dependency satisfied" for downstream jobs
DEPS_OK_STATES = frozenset({JobStatus.completed, JobStatus.skipped})
