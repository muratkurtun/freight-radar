import { SourceType, UrgencyLevel } from './enums.model';
import { Paged } from './paging.model';

/**
 * Opportunity (approved logistics-lead signal joined with raw item +
 * source). All v2 lead fields are optional so:
 *
 *   - legacy pre-0005 rows (which only carry company_name / location /
 *     role_title / supplier_name / summary) still deserialize cleanly;
 *   - the existing UI keeps rendering without code changes;
 *   - new UI can opt in to the lead fields when present.
 *
 * `signal_type` is widened to `string` because the backend dropped its
 * CHECK constraint in 0005 and legacy rows still carry pre-pivot values
 * (`warehouse_opening` etc.). Use `signalTypeLabel()` from enums.model
 * to humanize the value safely.
 */
export interface Opportunity {
  signal_id: string;
  signal_type: string;
  confidence: string;
  company_name: string | null;

  // Legacy fields (pre-0005) — populated on historical rows.
  location: string | null;
  role_title: string | null;
  supplier_name: string | null;
  summary: string | null;

  // Logistics-lead fields (post-0005) — optional for back-compat.
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

  created_at: string;
  raw_title: string | null;
  raw_url: string | null;
  published_at: string | null;
  source_id: string;
  source_name: string;
  source_type: SourceType;
}

export type PagedOpportunities = Paged<Opportunity>;
