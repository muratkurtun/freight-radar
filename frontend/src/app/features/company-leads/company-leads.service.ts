import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiBaseService } from '../../core/http/api-base.service';
import {
  CompanyLeadDetail,
  CompanyTeamStatus,
  LeadTier,
  PagedCompanyLeads,
} from '../../core/models/company-lead.model';

export interface CompanyLeadsQuery {
  sector?: string | null;
  region?: string | null;
  lead_tier?: LeadTier | null;
  latest_team_action?: CompanyTeamStatus | null;
  min_score?: number | null;
  limit?: number;
  offset?: number;
}

@Injectable({ providedIn: 'root' })
export class CompanyLeadsService {
  private api = inject(ApiBaseService);

  list(query: CompanyLeadsQuery = {}): Observable<PagedCompanyLeads> {
    return this.api.get<PagedCompanyLeads>('/company-leads', {
      sector: query.sector ?? null,
      region: query.region ?? null,
      lead_tier: query.lead_tier ?? null,
      latest_team_action: query.latest_team_action ?? null,
      min_score: query.min_score ?? null,
      limit: query.limit ?? 20,
      offset: query.offset ?? 0,
    });
  }

  detail(companyId: string): Observable<CompanyLeadDetail> {
    return this.api.get<CompanyLeadDetail>(`/company-leads/${companyId}`);
  }
}
