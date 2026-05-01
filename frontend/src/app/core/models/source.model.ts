import { SourceType } from './enums.model';
import { Paged } from './paging.model';

/**
 * Platform pool source. Backend `tenant_id IS NULL`. Tag arrays drive
 * tenant matching (see backend PlatformSourceRepository).
 */
export interface PlatformSource {
  id: string;
  source_type: SourceType;
  name: string;
  url: string;
  config: Record<string, unknown>;
  is_active: boolean;
  region_tags: string[];
  sector_tags: string[];
  customer_type_tags: string[];
  signal_focus_tags: string[];
  language: string | null;
  priority: number;
  quality_score: number | null;
  noise_level: number | null;
  created_at: string;
}

export interface PlatformSourceCreate {
  source_type: SourceType;
  name: string;
  url: string;
  config?: Record<string, unknown>;
  is_active?: boolean;
  region_tags?: string[];
  sector_tags?: string[];
  customer_type_tags?: string[];
  signal_focus_tags?: string[];
  language?: string | null;
  priority?: number;
  quality_score?: number | null;
  noise_level?: number | null;
}

export interface PlatformSourceUpdate {
  name?: string;
  url?: string;
  config?: Record<string, unknown>;
  is_active?: boolean;
  region_tags?: string[];
  sector_tags?: string[];
  customer_type_tags?: string[];
  signal_focus_tags?: string[];
  language?: string | null;
  priority?: number;
  quality_score?: number | null;
  noise_level?: number | null;
}

export type PagedPlatformSources = Paged<PlatformSource>;

export const SOURCE_TYPE_OPTIONS: { value: SourceType; label: string }[] = [
  { value: 'news', label: 'News' },
  { value: 'job_board', label: 'Job Board' },
  { value: 'company_website', label: 'Company Website' },
];
