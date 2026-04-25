import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiBaseService } from '../../core/http/api-base.service';
import { SignalType } from '../../core/models/enums.model';
import { PagedOpportunities } from '../../core/models/opportunity.model';

export interface OpportunitiesQuery {
  signal_type?: SignalType | null;
  since?: string | null;
  limit?: number;
  offset?: number;
}

@Injectable({ providedIn: 'root' })
export class OpportunitiesService {
  private api = inject(ApiBaseService);

  list(query: OpportunitiesQuery = {}): Observable<PagedOpportunities> {
    return this.api.get<PagedOpportunities>('/opportunities', {
      signal_type: query.signal_type ?? null,
      since: query.since ?? null,
      limit: query.limit ?? 20,
      offset: query.offset ?? 0,
    });
  }
}
