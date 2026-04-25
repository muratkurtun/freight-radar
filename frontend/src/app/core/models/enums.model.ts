export type SignalType =
  | 'warehouse_opening'
  | 'supplier_change'
  | 'hiring_supply_chain_role';

export type SourceType = 'news' | 'job_board' | 'company_website';
export type ReviewStatus = 'pending_review' | 'approved' | 'rejected';
export type PipelineRunStatus = 'running' | 'success' | 'failed';
export type UserRole = 'platform_admin' | 'tenant_admin' | 'tenant_user';
export type SubscriptionStatus = 'trial' | 'active' | 'expired';
