/**
 * Workflow contract types shared with backend API schema.
 *
 * Source of truth:
 * - apps/backend/app/schemas/workflow.py
 * - /openapi.json
 */

export interface WorkflowActionResponse {
  status: string;
  run_id: string;
  message: string;
  task_id: string | null;
}

export interface WorkflowAuditEvent {
  id: string;
  run_id: string;
  job_id: string | null;
  event_type: string;
  actor: string;
  data: Record<string, unknown>;
  occurred_at: string;
}

export interface WorkflowAuditResponse {
  run_id: string;
  events: WorkflowAuditEvent[];
  total: number;
}

export interface TriggerWorkflowRequest {
  channel_id?: string;
  topic_id?: string;
  pipeline_name?: string;
  context?: Record<string, unknown>;
}
