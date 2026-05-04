/**
 * Backend SignalType vocabulary (post-pivot, migration 0005).
 *
 * The DB no longer has a CHECK constraint on signal_type, so legacy
 * pre-0005 strings (`warehouse_opening`, `supplier_change`,
 * `hiring_supply_chain_role`) may still appear on historical rows. The
 * read-side type is therefore widened to `string` everywhere — see
 * `signalTypeLabel()` for a humanized display fallback.
 */
export type SignalType =
  | 'export_expansion'
  | 'import_need'
  | 'new_factory'
  | 'new_warehouse'
  | 'capacity_increase'
  | 'new_market_entry'
  | 'distributorship'
  | 'ecommerce_growth'
  | 'hiring_logistics_role'
  | 'hiring_export_role'
  | 'investment_incentive'
  | 'supply_chain_problem'
  | 'tender_or_contract';

export type SourceType = 'news' | 'job_board' | 'company_website';
export type ReviewStatus = 'pending_review' | 'approved' | 'rejected';
export type PipelineRunStatus = 'running' | 'success' | 'failed';
export type UserRole = 'platform_admin' | 'tenant_admin' | 'tenant_user';
export type SubscriptionStatus = 'trial' | 'active' | 'expired';
export type UrgencyLevel = 'low' | 'medium' | 'high';

export const SIGNAL_TYPE_OPTIONS: { value: SignalType; label: string }[] = [
  { value: 'export_expansion', label: 'Export expansion' },
  { value: 'import_need', label: 'Import need' },
  { value: 'new_factory', label: 'New factory' },
  { value: 'new_warehouse', label: 'New warehouse' },
  { value: 'capacity_increase', label: 'Capacity increase' },
  { value: 'new_market_entry', label: 'New market entry' },
  { value: 'distributorship', label: 'Distributorship' },
  { value: 'ecommerce_growth', label: 'E-commerce growth' },
  { value: 'hiring_logistics_role', label: 'Hiring logistics role' },
  { value: 'hiring_export_role', label: 'Hiring export role' },
  { value: 'investment_incentive', label: 'Investment incentive' },
  { value: 'supply_chain_problem', label: 'Supply chain problem' },
  { value: 'tender_or_contract', label: 'Tender or contract' },
];

const SIGNAL_TYPE_LABEL_INDEX: Record<string, string> = SIGNAL_TYPE_OPTIONS.reduce(
  (acc, opt) => {
    acc[opt.value] = opt.label;
    return acc;
  },
  {} as Record<string, string>,
);

/**
 * Humanized label for any signal_type string.
 *
 * - Returns the configured label for a known v2 type
 * - Returns 'Unknown' when the value is null / empty
 * - Falls back to the raw string (Title Cased) for unknown values so
 *   pre-pivot legacy rows (`warehouse_opening` etc.) still render.
 */
export function signalTypeLabel(value: string | null | undefined): string {
  if (!value) return 'Unknown';
  const known = SIGNAL_TYPE_LABEL_INDEX[value];
  if (known) return known;
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
