import { SourceType } from './enums.model';
import { Paged } from './paging.model';

export interface Source {
  id: string;
  tenant_id: string;
  source_type: SourceType;
  name: string;
  url: string;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
}

export interface SourceCreate {
  source_type: SourceType;
  name: string;
  url: string;
  config?: Record<string, unknown>;
  is_active?: boolean;
}

export interface SourceUpdate {
  name?: string;
  url?: string;
  config?: Record<string, unknown>;
  is_active?: boolean;
}

export type PagedSources = Paged<Source>;

export const SOURCE_TYPE_OPTIONS: { value: SourceType; label: string }[] = [
  { value: 'news', label: 'News' },
  { value: 'job_board', label: 'Job Board' },
  { value: 'company_website', label: 'Company Website' },
];
