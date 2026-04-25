import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { Signal as SignalRow } from '../../core/models/review.model';
import { ReviewsService } from './reviews.service';

@Component({
  selector: 'app-reviews-pending',
  standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe],
  templateUrl: './reviews-pending.component.html',
  styleUrl: './reviews-pending.component.scss',
})
export class ReviewsPendingComponent {
  private service = inject(ReviewsService);

  protected readonly items = signal<SignalRow[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly limit = 20;
  protected readonly offset = signal(0);

  /** id of the row whose reject reason form is open */
  protected readonly rejectingId = signal<string | null>(null);
  protected readonly rejectReason = signal('');
  protected readonly decisionLoading = signal(false);

  constructor() {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service.listPending(this.limit, this.offset()).subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.total.set(res.page.total);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Pending listesi alınamadı.');
      },
    });
  }

  approve(id: string): void {
    if (this.decisionLoading()) return;
    this.decisionLoading.set(true);
    this.service.decide(id, { action: 'approve' }).subscribe({
      next: () => this.removeFromList(id),
      error: () => this.error.set('Onay işlemi başarısız.'),
      complete: () => this.decisionLoading.set(false),
    });
  }

  openReject(id: string): void {
    this.rejectingId.set(id);
    this.rejectReason.set('');
  }

  cancelReject(): void {
    this.rejectingId.set(null);
    this.rejectReason.set('');
  }

  confirmReject(id: string): void {
    const reason = this.rejectReason().trim();
    if (!reason || this.decisionLoading()) return;
    this.decisionLoading.set(true);
    this.service.decide(id, { action: 'reject', reason }).subscribe({
      next: () => {
        this.removeFromList(id);
        this.cancelReject();
      },
      error: () => this.error.set('Reddetme işlemi başarısız.'),
      complete: () => this.decisionLoading.set(false),
    });
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

  private removeFromList(id: string): void {
    this.items.update((list) => list.filter((s) => s.id !== id));
    this.total.update((v) => Math.max(0, v - 1));
  }
}
