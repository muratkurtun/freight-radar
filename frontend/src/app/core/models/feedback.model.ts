/**
 * Sales-team feedback on a detected signal. Append-only history; the
 * "current team status" is the most recent row across all tenant
 * users (computed server-side, exposed as last_feedback_action on
 * Opportunity).
 */

export type FeedbackAction =
  | 'relevant'
  | 'not_relevant'
  | 'qualified'
  | 'contacted'
  | 'converted'
  | 'dismissed'
  | 'wrong_company'
  | 'wrong_sector'
  | 'not_a_logistics_lead';

export type FeedbackReason =
  | 'wrong_company'
  | 'wrong_sector'
  | 'not_a_logistics_lead'
  | 'duplicate'
  | 'low_confidence';

export interface FeedbackCreate {
  action: FeedbackAction;
  reason?: FeedbackReason | null;
  note?: string | null;
}

export interface Feedback {
  id: string;
  tenant_id: string;
  signal_id: string;
  user_id: string;
  action: FeedbackAction;
  reason: FeedbackReason | null;
  note: string | null;
  created_at: string;
}

/**
 * Primary lifecycle buttons surfaced on every lead row. The remaining
 * three negative actions (wrong_company, wrong_sector,
 * not_a_logistics_lead) are exposed as REASON values via the Not
 * Relevant flow rather than primary buttons.
 */
export const PRIMARY_FEEDBACK_ACTIONS: { value: FeedbackAction; label: string }[] = [
  { value: 'relevant', label: 'Relevant' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'converted', label: 'Converted' },
  { value: 'not_relevant', label: 'Not Relevant' },
  { value: 'dismissed', label: 'Dismiss' },
];

/**
 * Backend rule: reason is required for these actions. Frontend mirrors
 * the rule so the user fills it in before we POST. Keep in sync with
 * backend NEGATIVE_FEEDBACK_ACTIONS.
 */
export const REASON_REQUIRED_ACTIONS: ReadonlySet<FeedbackAction> = new Set<FeedbackAction>([
  'not_relevant',
  'dismissed',
  'wrong_company',
  'wrong_sector',
  'not_a_logistics_lead',
]);

export const REASON_OPTIONS: { value: FeedbackReason; label: string }[] = [
  { value: 'wrong_company', label: 'Wrong company' },
  { value: 'wrong_sector', label: 'Wrong sector' },
  { value: 'not_a_logistics_lead', label: 'Not a logistics lead' },
  { value: 'duplicate', label: 'Duplicate' },
  { value: 'low_confidence', label: 'Low confidence' },
];

const ACTION_LABEL_INDEX: Record<string, string> = {
  relevant: 'Relevant',
  not_relevant: 'Not Relevant',
  qualified: 'Qualified',
  contacted: 'Contacted',
  converted: 'Converted',
  dismissed: 'Dismissed',
  wrong_company: 'Wrong company',
  wrong_sector: 'Wrong sector',
  not_a_logistics_lead: 'Not a logistics lead',
};

export function feedbackActionLabel(value: string | null | undefined): string {
  if (!value) return '';
  return ACTION_LABEL_INDEX[value] ?? value.replace(/_/g, ' ');
}

/**
 * Visual badge class derived from the action. Six colors: positive
 * lifecycle (relevant / qualified / contacted / converted) and
 * negative / corrective (not_relevant / dismissed / wrong_*).
 */
export function feedbackActionBadgeClass(value: string | null | undefined): string {
  switch (value) {
    case 'relevant':
      return 'fb-badge fb-relevant';
    case 'qualified':
      return 'fb-badge fb-qualified';
    case 'contacted':
      return 'fb-badge fb-contacted';
    case 'converted':
      return 'fb-badge fb-converted';
    case 'not_relevant':
    case 'wrong_company':
    case 'wrong_sector':
    case 'not_a_logistics_lead':
      return 'fb-badge fb-not-relevant';
    case 'dismissed':
      return 'fb-badge fb-dismissed';
    default:
      return 'fb-badge fb-none';
  }
}
