import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  SIGNAL_TYPE_OPTIONS,
  signalTypeLabel,
} from '../../core/models/enums.model';
import { Opportunity } from '../../core/models/opportunity.model';
import { OpportunitiesService } from './opportunities.service';

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

  protected readonly limit = 20;
  protected readonly offset = signal(0);
  // String, not SignalType, so legacy rows in the dropdown (if any are
  // ever surfaced via filter) and v2 values both round-trip cleanly.
  protected readonly signalType = signal<string>('');

  readonly signalTypes = SIGNAL_TYPE_OPTIONS;

  /** Render any signal_type string (v2 or legacy) as a human label. */
  protected readonly typeLabel = signalTypeLabel;

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
          this.error.set('Opportunities alınamadı.');
        },
      });
  }

  onTypeChange(value: string): void {
    this.signalType.set(value);
    this.offset.set(0);
    this.reload();
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

  protected confidence(raw: string): number {
    return parseFloat(raw);
  }
}
