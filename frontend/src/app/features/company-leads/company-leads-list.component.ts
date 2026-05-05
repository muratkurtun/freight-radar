import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import {
  CompanyLeadSummary,
  CompanyTeamStatus,
  LeadTier,
  leadTierBadgeClass,
  teamStatusBadgeClass,
  teamStatusLabel,
} from '../../core/models/company-lead.model';
import { signalTypeLabel } from '../../core/models/enums.model';
import {
  REGION_OPTIONS,
  SECTOR_OPTIONS,
  TaxonomyOption,
} from '../../core/models/preferences.model';
import { CompanyLeadsService } from './company-leads.service';

const TIER_OPTIONS: { value: LeadTier; label: string }[] = [
  { value: 'hot', label: 'Hot (≥75)' },
  { value: 'warm', label: 'Warm (50–74)' },
  { value: 'low', label: 'Low (<50)' },
];

const TEAM_STATUS_OPTIONS: { value: CompanyTeamStatus; label: string }[] = [
  { value: 'new', label: 'New' },
  { value: 'relevant', label: 'Relevant' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'contacted', label: 'Contacted' },
  { value: 'converted', label: 'Converted' },
  { value: 'not_relevant', label: 'Not Relevant' },
  { value: 'dismissed', label: 'Dismissed' },
];

@Component({
  selector: 'app-company-leads-list',
  standalone: true,
  imports: [FormsModule, DatePipe, RouterLink],
  templateUrl: './company-leads-list.component.html',
  styleUrl: './company-leads.scss',
})
export class CompanyLeadsListComponent {
  private service = inject(CompanyLeadsService);

  protected readonly items = signal<CompanyLeadSummary[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly limit = 20;
  protected readonly offset = signal(0);

  // Server-side filters
  protected readonly sector = signal<string>('');
  protected readonly region = signal<string>('');
  protected readonly leadTier = signal<LeadTier | ''>('');
  protected readonly teamStatus = signal<CompanyTeamStatus | ''>('');
  protected readonly minScore = signal<number>(0);

  protected readonly sectors: TaxonomyOption[] = SECTOR_OPTIONS;
  protected readonly regions: TaxonomyOption[] = REGION_OPTIONS;
  protected readonly tiers = TIER_OPTIONS;
  protected readonly statuses = TEAM_STATUS_OPTIONS;

  protected readonly typeLabel = signalTypeLabel;
  protected readonly statusLabel = teamStatusLabel;
  protected readonly statusBadge = teamStatusBadgeClass;
  protected readonly tierBadge = leadTierBadgeClass;

  constructor() {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service
      .list({
        sector: this.sector() || null,
        region: this.region() || null,
        lead_tier: (this.leadTier() || null) as LeadTier | null,
        latest_team_action: (this.teamStatus() || null) as CompanyTeamStatus | null,
        min_score: this.minScore() > 0 ? this.minScore() : null,
        limit: this.limit,
        offset: this.offset(),
      })
      .subscribe({
        next: (res) => {
          this.items.set(res.items);
          this.total.set(res.page.total);
          this.loading.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.error.set('Company leads could not be loaded.');
        },
      });
  }

  applyFilters(): void {
    this.offset.set(0);
    this.reload();
  }

  clearFilters(): void {
    this.sector.set('');
    this.region.set('');
    this.leadTier.set('');
    this.teamStatus.set('');
    this.minScore.set(0);
    this.applyFilters();
  }

  next(): void {
    if (this.offset() + this.limit >= this.total()) return;
    this.offset.update((v) => v + this.limit);
    this.reload();
  }

  prev(): void {
    if (this.offset() === 0) return;
    this.offset.update((v) => Math.max(0, v - this.limit));
    this.reload();
  }
}
