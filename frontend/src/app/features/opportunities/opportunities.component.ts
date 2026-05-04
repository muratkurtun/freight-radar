import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  SIGNAL_TYPE_OPTIONS,
  signalTypeLabel,
  UrgencyLevel,
} from '../../core/models/enums.model';
import { Opportunity } from '../../core/models/opportunity.model';
import {
  REGION_OPTIONS,
  SECTOR_OPTIONS,
  TaxonomyOption,
} from '../../core/models/preferences.model';
import { OpportunitiesService } from './opportunities.service';

const URGENCY_OPTIONS: { value: UrgencyLevel; label: string }[] = [
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

@Component({
  selector: 'app-opportunities',
  standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe],
  templateUrl: './opportunities.component.html',
  styleUrl: './opportunities.component.scss',
})
export class OpportunitiesComponent {
  private service = inject(OpportunitiesService);

  protected readonly items = signal<Opportunity[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly info = signal<string | null>(null);

  protected readonly limit = 20;
  protected readonly offset = signal(0);

  // Server-side filter (the API supports signal_type out of the box).
  protected readonly signalType = signal<string>('');

  // Client-side filters apply only to the page already loaded. The
  // backend doesn't yet accept sector/region/urgency/min-confidence
  // params — when leads scale beyond a single page, these need to move
  // server-side.
  protected readonly sectorFilter = signal<string>('');
  protected readonly regionFilter = signal<string>('');
  protected readonly urgencyFilter = signal<string>('');
  protected readonly minConfidence = signal<number>(0);

  protected readonly signalTypes = SIGNAL_TYPE_OPTIONS;
  protected readonly sectors: TaxonomyOption[] = SECTOR_OPTIONS;
  protected readonly regions: TaxonomyOption[] = REGION_OPTIONS;
  protected readonly urgencies = URGENCY_OPTIONS;
  protected readonly typeLabel = signalTypeLabel;

  protected readonly expandedId = signal<string | null>(null);

  protected readonly visible = computed<Opportunity[]>(() => {
    const sector = this.sectorFilter();
    const region = this.regionFilter();
    const urgency = this.urgencyFilter();
    const minConf = this.minConfidence();
    return this.items().filter((op) => {
      if (sector && op.sector !== sector) return false;
      if (region && op.region !== region) return false;
      if (urgency && op.urgency !== urgency) return false;
      if (minConf > 0 && this.confidence(op.confidence) < minConf) return false;
      return true;
    });
  });

  constructor() {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service
      .list({
        signal_type: this.signalType() || null,
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
          this.error.set('Leads could not be loaded.');
        },
      });
  }

  onTypeChange(value: string): void {
    this.signalType.set(value);
    this.offset.set(0);
    this.reload();
  }

  toggleExpand(id: string): void {
    this.expandedId.set(this.expandedId() === id ? null : id);
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

  clearFilters(): void {
    this.sectorFilter.set('');
    this.regionFilter.set('');
    this.urgencyFilter.set('');
    this.minConfidence.set(0);
  }

  copyOutreach(op: Opportunity): void {
    const text = (op.suggested_outreach_message ?? '').trim();
    if (!text) {
      this.error.set('No outreach message available for this lead.');
      setTimeout(() => this.error.set(null), 3000);
      return;
    }
    navigator.clipboard
      ?.writeText(text)
      .then(() => this.flashInfo('Outreach message copied.'))
      .catch(() => this.error.set('Could not copy to clipboard.'));
  }

  protected confidence(raw: string): number {
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : 0;
  }

  protected confidencePct(raw: string): number {
    return Math.round(this.confidence(raw) * 100);
  }

  protected urgencyClass(value: string | null | undefined): string {
    switch (value) {
      case 'high':
        return 'badge urgency high';
      case 'medium':
        return 'badge urgency medium';
      case 'low':
        return 'badge urgency low';
      default:
        return 'badge urgency unknown';
    }
  }

  protected confidenceClass(raw: string): string {
    const v = this.confidence(raw);
    if (v >= 0.75) return 'confidence high';
    if (v >= 0.5) return 'confidence medium';
    return 'confidence low';
  }

  private flashInfo(msg: string): void {
    this.info.set(msg);
    setTimeout(() => {
      if (this.info() === msg) this.info.set(null);
    }, 3000);
  }
}
