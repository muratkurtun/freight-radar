import { ReviewStatus, SignalType } from './enums.model';
import { Paged } from './paging.model';

export interface Signal {
  id: string;
  tenant_id: string;
  raw_source_item_id: string;
  signal_type: SignalType;
  confidence: string;
  company_name: string | null;
  location: string | null;
  role_title: string | null;
  supplier_name: string | null;
  summary: string | null;
  extra: Record<string, unknown>;
  prompt_version: string;
  review_status: ReviewStatus;
  created_at: string;
}

export type PagedSignals = Paged<Signal>;

export interface ReviewDecisionRequest {
  action: 'approve' | 'reject';
  reason?: string;
}
