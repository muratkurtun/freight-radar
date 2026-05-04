import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiBaseService } from '../../core/http/api-base.service';
import { PagedOpportunities } from '../../core/models/opportunity.model';

export interface OpportunitiesQuery {
  /** Filter is a free-form string so callers can pass either v2 values
   *  from SIGNAL_TYPE_OPTIONS or legacy strings without TS friction. */
  signal_type?: string | null;
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
