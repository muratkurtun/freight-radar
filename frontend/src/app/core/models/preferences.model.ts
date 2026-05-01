/**
 * Targeting taxonomies — the controlled vocabularies the salesperson
 * picks from. The backend stores these as TEXT[] arrays (no enum
 * constraint at the DB layer) so the frontend is the source of truth
 * for the option set. Keep these lists in sync with whatever the
 * platform admin tags the source pool with — a tag in the pool with no
 * matching option here is invisible to tenants.
 */

export interface TaxonomyOption {
  value: string;
  label: string;
}

export const CUSTOMER_TYPE_OPTIONS: TaxonomyOption[] = [
  { value: 'importer', label: 'Importer' },
  { value: 'exporter', label: 'Exporter' },
  { value: 'manufacturer', label: 'Manufacturer' },
  { value: 'distributor', label: 'Distributor' },
  { value: 'retailer', label: 'Retailer' },
  { value: 'ecommerce', label: 'E-commerce' },
  { value: 'wholesaler', label: 'Wholesaler' },
];

export const SECTOR_OPTIONS: TaxonomyOption[] = [
  { value: 'textile', label: 'Textile' },
  { value: 'automotive', label: 'Automotive' },
  { value: 'machinery', label: 'Machinery' },
  { value: 'food', label: 'Food' },
  { value: 'chemical', label: 'Chemical' },
  { value: 'furniture', label: 'Furniture' },
  { value: 'electronics', label: 'Electronics' },
  { value: 'medical', label: 'Medical' },
  { value: 'retail', label: 'Retail' },
  { value: 'industrial', label: 'Industrial' },
];

export const REGION_OPTIONS: TaxonomyOption[] = [
  { value: 'turkey', label: 'Turkey' },
  { value: 'eu', label: 'European Union' },
  { value: 'germany', label: 'Germany' },
  { value: 'uk', label: 'United Kingdom' },
  { value: 'middle_east', label: 'Middle East' },
  { value: 'global', label: 'Global' },
];

export const SIGNAL_FOCUS_OPTIONS: TaxonomyOption[] = [
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
];

export interface TenantPreferences {
  id: string;
  tenant_id: string;
  target_customer_types: string[];
  sectors: string[];
  regions: string[];
  signal_focuses: string[];
  minimum_confidence: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TenantPreferencesUpsert {
  target_customer_types: string[];
  sectors: string[];
  regions: string[];
  signal_focuses: string[];
  minimum_confidence: number;
  is_active: boolean;
}
