import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiBaseService } from '../../core/http/api-base.service';
import { PipelineRunStatus } from '../../core/models/enums.model';
import {
  PagedPipelineRuns,
  PipelineTriggerResponse,
} from '../../core/models/pipeline.model';

export interface PipelineRunsQuery {
  source_id?: string | null;
  status?: PipelineRunStatus | null;
  limit?: number;
}

@Injectable({ providedIn: 'root' })
export class PipelineService {
  private api = inject(ApiBaseService);

  list(query: PipelineRunsQuery = {}): Observable<PagedPipelineRuns> {
    return this.api.get<PagedPipelineRuns>('/pipeline-runs', {
      source_id: query.source_id ?? null,
      status: query.status ?? null,
      limit: query.limit ?? 20,
    });
  }

  trigger(): Observable<PipelineTriggerResponse> {
    return this.api.post<PipelineTriggerResponse>('/pipeline/run', {});
  }
}
