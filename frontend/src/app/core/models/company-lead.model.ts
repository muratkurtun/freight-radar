import { Paged } from './paging.model';
import {
  Feedback,
  feedbackActionBadgeClass,
  feedbackActionLabel,
} from './feedback.model';

/**
 * Company-level lead view. Each row aggregates every approved signal
 * for one company plus the team's feedback history; see
 * app/repositories/company_leads.py for the SQL contract.
 *
 * `latest_team_action` is the priority-derived status (converted >
 * contacted > qualified > relevant > dismissed/not_relevant > new),
 * NOT the timestamp-most-recent action — that timestamp lives in
 * `latest_feedback_at`.
 */

export type LeadTier = 'hot' | 'warm' | 'low';

export type CompanyTeamStatus =
  | 'converted'
  | 'contacted'
  | 'qualified'
  | 'relevant'
  | 'dismissed'
  | 'not_relevant'
  | 'new';

export interface FeedbackCounts {
  relevant: number;
  qualified: number;
  contacted: number;
  converted: number;
  dismissed: number;
  not_relevant: number;
  wrong_company: number;
  wrong_sector: number;
  not_a_logistics_lead: number;
  total: number;
}

export interface CompanyLeadSummary {
  company_id: string;
  company_name: string;
  normalized_name: string;
  sector: string | null;
  region: string | null;
  website: string | null;

  signal_count: number;
  latest_signal_date: string;
  top_signal_type: string | null;

  highest_lead_score: number;
  lead_tier: LeadTier;

  recommended_services: string[];
  latest_detected_event: string | null;
  suggested_next_action: string | null;

  latest_team_action: CompanyTeamStatus;
  latest_feedback_at: string | null;
  feedback_counts: FeedbackCounts;
}

export interface CompanyLeadRelatedSignal {
  signal_id: string;
  signal_type: string;
  detected_event: string | null;
  potential_logistics_need: string | null;
  recommended_services: string[];
  confidence: string;
  lead_score: number;
  lead_tier: LeadTier;
  urgency: string | null;
  source_name: string;
  source_url: string | null;
  suggested_outreach_message: string | null;
  created_at: string;
  current_team_action: string | null;
  latest_feedback_at: string | null;
}

export interface CompanyLeadDetail extends CompanyLeadSummary {
  related_signals: CompanyLeadRelatedSignal[];
}

export type PagedCompanyLeads = Paged<CompanyLeadSummary>;

/** Render the priority-derived team status, including the synthetic
 *  'new' state. Delegates to feedbackActionLabel for the action-shaped
 *  values so labels stay consistent across the app. */
export function teamStatusLabel(value: string | null | undefined): string {
  if (!value || value === 'new') return 'New';
  return feedbackActionLabel(value);
}

/** Reuse the feedback badge palette; 'new' falls through to the
 *  neutral `fb-none` class via the helper's default branch. */
export function teamStatusBadgeClass(value: string | null | undefined): string {
  return feedbackActionBadgeClass(value);
}

export function leadTierBadgeClass(tier: LeadTier): string {
  switch (tier) {
    case 'hot':
      return 'tier-badge tier-hot';
    case 'warm':
      return 'tier-badge tier-warm';
    case 'low':
      return 'tier-badge tier-low';
  }
}

export type { Feedback };
