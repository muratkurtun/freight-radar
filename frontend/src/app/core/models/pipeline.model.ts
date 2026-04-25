import { PipelineRunStatus } from './enums.model';

export interface PipelineRun {
  id: string;
  tenant_id: string;
  source_id: string;
  status: PipelineRunStatus;
  started_at: string;
  finished_at: string | null;
  items_collected: number;
  items_new: number;
  signals_detected: number;
  error_message: string | null;
}

export interface PagedPipelineRuns {
  items: PipelineRun[];
}

export interface PipelineTriggerResponse {
  status: 'accepted';
  tenant_id: string;
  message: string;
}
