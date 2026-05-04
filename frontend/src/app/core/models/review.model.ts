import { ReviewStatus, UrgencyLevel } from './enums.model';
import { Paged } from './paging.model';

/**
 * Detected signal as returned by the API. signal_type is `string` so
 * legacy pre-0005 rows pass through (see opportunity.model.ts for the
 * back-compat rationale). New v2 lead fields are optional.
 */
export interface Signal {
  id: string;
  tenant_id: string;
  raw_source_item_id: string;
  signal_type: string;
  confidence: string;
  company_name: string | null;

  // Legacy fields
  location: string | null;
  role_title: string | null;
  supplier_name: string | null;
  summary: string | null;

  // v2 logistics-lead fields (optional)
  target_customer_type?: string | null;
  sector?: string | null;
  region?: string | null;
  detected_event?: string | null;
  why_relevant_for_logistics?: string | null;
  potential_logistics_need?: string | null;
  recommended_services?: string[];
  urgency?: UrgencyLevel | null;
  suggested_sales_action?: string | null;
  suggested_outreach_message?: string | null;
  evidence_snippet?: string | null;

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
