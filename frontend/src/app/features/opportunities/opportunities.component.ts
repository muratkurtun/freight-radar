import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { SignalType } from '../../core/models/enums.model';
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
  protected readonly signalType = signal<SignalType | ''>('');

  readonly signalTypes: { value: SignalType; label: string }[] = [
    { value: 'warehouse_opening', label: 'Warehouse Opening' },
    { value: 'supplier_change', label: 'Supplier Change' },
    { value: 'hiring_supply_chain_role', label: 'Supply Chain Hiring' },
  ];

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
    this.signalType.set(value as SignalType | '');
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
