import { SignalType, SourceType } from './enums.model';
import { Paged } from './paging.model';

export interface Opportunity {
  signal_id: string;
  signal_type: SignalType;
  confidence: string;
  company_name: string | null;
  location: string | null;
  role_title: string | null;
  supplier_name: string | null;
  summary: string | null;
  created_at: string;
  raw_title: string | null;
  raw_url: string | null;
  published_at: string | null;
  source_id: string;
  source_name: string;
  source_type: SourceType;
}

export type PagedOpportunities = Paged<Opportunity>;
