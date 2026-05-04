import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  SIGNAL_TYPE_OPTIONS,
  signalTypeLabel,
  UrgencyLevel,
} from '../../core/models/enums.model';
import {
  Feedback,
  FeedbackAction,
  FeedbackCreate,
  FeedbackReason,
  PRIMARY_FEEDBACK_ACTIONS,
  REASON_OPTIONS,
  REASON_REQUIRED_ACTIONS,
  feedbackActionBadgeClass,
  feedbackActionLabel,
} from '../../core/models/feedback.model';
import { Opportunity } from '../../core/models/opportunity.model';
import {
  REGION_OPTIONS,
  SECTOR_OPTIONS,
  TaxonomyOption,
} from '../../core/models/preferences.model';
import { FeedbackService } from './feedback.service';
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
  private feedback = inject(FeedbackService);

  protected readonly items = signal<Opportunity[]>([]);
  protected readonly total = signal(0);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly info = signal<string | null>(null);

  protected readonly limit = 20;
  protected readonly offset = signal(0);

  protected readonly signalType = signal<string>('');
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

  // Feedback UI state
  protected readonly feedbackActions = PRIMARY_FEEDBACK_ACTIONS;
  protected readonly reasonOptions = REASON_OPTIONS;
  protected readonly actionLabel = feedbackActionLabel;
  protected readonly badgeClass = feedbackActionBadgeClass;

  /** id of the row whose reason picker is open ("Not Relevant" /
   *  "Dismiss" / etc. — UI requires a reason before submission). */
  protected readonly reasonPromptFor = signal<{
    signalId: string;
    action: FeedbackAction;
  } | null>(null);
  protected readonly pendingReason = signal<FeedbackReason | ''>('');
  protected readonly pendingNote = signal<string>('');
  protected readonly submittingFor = signal<string | null>(null);

  protected readonly historyFor = signal<string | null>(null);
  protected readonly historyItems = signal<Feedback[]>([]);
  protected readonly historyLoading = signal(false);

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
    const next = this.expandedId() === id ? null : id;
    this.expandedId.set(next);
    if (next) {
      this.loadHistory(next);
    } else {
      this.historyFor.set(null);
      this.historyItems.set([]);
    }
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

  // ---- Feedback flow -----------------------------------------------

  /**
   * Click handler for a feedback action button on a lead row.
   *
   * - Negative actions (Not Relevant / Dismiss / Wrong *) open the
   *   reason picker; submission happens after the user picks a reason.
   * - Positive actions are submitted immediately, with optional note.
   */
  onFeedbackClick(op: Opportunity, action: FeedbackAction): void {
    if (REASON_REQUIRED_ACTIONS.has(action)) {
      this.reasonPromptFor.set({ signalId: op.signal_id, action });
      this.pendingReason.set('');
      this.pendingNote.set('');
      return;
    }
    this.submitFeedback(op, { action, note: this.optionalNote() });
  }

  cancelReasonPrompt(): void {
    this.reasonPromptFor.set(null);
    this.pendingReason.set('');
    this.pendingNote.set('');
  }

  confirmReasonPrompt(op: Opportunity): void {
    const prompt = this.reasonPromptFor();
    if (!prompt) return;
    if (!this.pendingReason()) {
      this.error.set('Please select a reason.');
      setTimeout(() => this.error.set(null), 3000);
      return;
    }
    this.submitFeedback(op, {
      action: prompt.action,
      reason: this.pendingReason() as FeedbackReason,
      note: this.optionalNote(),
    });
  }

  protected isReasonPromptOpenFor(signalId: string): boolean {
    return this.reasonPromptFor()?.signalId === signalId;
  }

  protected pendingActionLabel(): string {
    const a = this.reasonPromptFor()?.action;
    return a ? feedbackActionLabel(a) : '';
  }

  private submitFeedback(op: Opportunity, payload: FeedbackCreate): void {
    if (this.submittingFor()) return;
    this.submittingFor.set(op.signal_id);
    this.feedback.submit(op.signal_id, payload).subscribe({
      next: (created) => {
        this.submittingFor.set(null);
        // Optimistic-style update on the row: badge + count come from
        // the server payload, but we have all fields we need on
        // `created` to update the local list without a full reload.
        this.items.update((rows) =>
          rows.map((row) =>
            row.signal_id === op.signal_id
              ? {
                  ...row,
                  feedback_count: (row.feedback_count ?? 0) + 1,
                  last_feedback_action: created.action,
                  last_feedback_at: created.created_at,
                  last_feedback_user_id: created.user_id,
                }
              : row,
          ),
        );
        // If the user was looking at history, refresh it.
        if (this.historyFor() === op.signal_id) {
          this.historyItems.update((rows) => [created, ...rows]);
        }
        this.cancelReasonPrompt();
        this.flashInfo(`Feedback recorded: ${feedbackActionLabel(payload.action)}.`);
      },
      error: () => {
        this.submittingFor.set(null);
        this.error.set('Could not save feedback.');
      },
    });
  }

  private optionalNote(): string | undefined {
    const note = this.pendingNote().trim();
    return note ? note : undefined;
  }

  private loadHistory(signalId: string): void {
    this.historyFor.set(signalId);
    this.historyItems.set([]);
    this.historyLoading.set(true);
    this.feedback.history(signalId).subscribe({
      next: (rows) => {
        this.historyItems.set(rows);
        this.historyLoading.set(false);
      },
      error: () => {
        this.historyLoading.set(false);
        // Non-fatal: keep the detail panel open without history.
      },
    });
  }

  // ---- helpers -----------------------------------------------------

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
