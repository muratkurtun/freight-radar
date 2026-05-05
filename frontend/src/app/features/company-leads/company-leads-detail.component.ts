import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import {
  CompanyLeadDetail,
  CompanyLeadRelatedSignal,
  leadTierBadgeClass,
  teamStatusBadgeClass,
  teamStatusLabel,
} from '../../core/models/company-lead.model';
import { signalTypeLabel } from '../../core/models/enums.model';
import { feedbackActionBadgeClass, feedbackActionLabel } from '../../core/models/feedback.model';
import { CompanyLeadsService } from './company-leads.service';

@Component({
  selector: 'app-company-leads-detail',
  standalone: true,
  imports: [DatePipe, DecimalPipe, RouterLink],
  templateUrl: './company-leads-detail.component.html',
  styleUrl: './company-leads.scss',
})
export class CompanyLeadsDetailComponent {
  private service = inject(CompanyLeadsService);

  /** Bound from the route param via withComponentInputBinding(). */
  readonly companyId = input.required<string>();

  protected readonly data = signal<CompanyLeadDetail | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly info = signal<string | null>(null);

  protected readonly typeLabel = signalTypeLabel;
  protected readonly statusLabel = teamStatusLabel;
  protected readonly statusBadge = teamStatusBadgeClass;
  protected readonly tierBadge = leadTierBadgeClass;
  protected readonly fbLabel = feedbackActionLabel;
  protected readonly fbBadge = feedbackActionBadgeClass;

  constructor() {
    // input.required() is set when the component activates; load lazily
    // off the next microtask so the signal is materialized.
    queueMicrotask(() => this.load());
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service.detail(this.companyId()).subscribe({
      next: (data) => {
        this.data.set(data);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Could not load company lead.');
      },
    });
  }

  copyOutreach(signal: CompanyLeadRelatedSignal): void {
    const text = (signal.suggested_outreach_message ?? '').trim();
    if (!text) return;
    navigator.clipboard
      ?.writeText(text)
      .then(() => this.flashInfo('Outreach message copied.'))
      .catch(() => this.error.set('Could not copy to clipboard.'));
  }

  protected confidence(raw: string): number {
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : 0;
  }

  private flashInfo(msg: string): void {
    this.info.set(msg);
    setTimeout(() => {
      if (this.info() === msg) this.info.set(null);
    }, 3000);
  }
}
