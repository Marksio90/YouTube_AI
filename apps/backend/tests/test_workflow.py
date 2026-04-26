from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.workflow import TriggerRequest, WorkflowActionResponse


def test_workflow_trigger_defaults_pipeline_and_context() -> None:
    payload = TriggerRequest()

    assert payload.pipeline_name == "youtube_content"
    assert payload.context == {}


def test_workflow_trigger_rejects_invalid_channel_id() -> None:
    with pytest.raises(ValidationError):
        TriggerRequest(channel_id="not-a-uuid")


def test_workflow_action_contract() -> None:
    run_id = uuid4()

    result = WorkflowActionResponse(
        status="ok",
        run_id=run_id,
        message="Workflow paused",
        task_id=None,
    )

    assert result.run_id == run_id
    assert result.status == "ok"
