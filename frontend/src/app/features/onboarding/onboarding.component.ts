import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { AuthStore } from '../../core/auth/auth.store';
import {
  CUSTOMER_TYPE_OPTIONS,
  REGION_OPTIONS,
  SECTOR_OPTIONS,
  SIGNAL_FOCUS_OPTIONS,
  TaxonomyOption,
  TenantPreferencesUpsert,
} from '../../core/models/preferences.model';
import { PipelineService } from '../pipeline/pipeline.service';
import { TargetingService } from '../targeting/targeting.service';

interface ChipStep {
  key: 'target_customer_types' | 'sectors' | 'regions' | 'signal_focuses';
  title: string;
  description: string;
  options: TaxonomyOption[];
}

const CHIP_STEPS: ChipStep[] = [
  {
    key: 'target_customer_types',
    title: 'Target customer types',
    description:
      'Which kinds of companies do you sell to? Pick every segment your team would want to reach.',
    options: CUSTOMER_TYPE_OPTIONS,
  },
  {
    key: 'sectors',
    title: 'Sectors',
    description:
      'Which industries do these companies operate in? Multiple sectors are fine — leads will match any.',
    options: SECTOR_OPTIONS,
  },
  {
    key: 'regions',
    title: 'Regions',
    description:
      'Where are these companies based or expanding to? Pick the geographies your sales team can serve.',
    options: REGION_OPTIONS,
  },
  {
    key: 'signal_focuses',
    title: 'Signal focuses',
    description:
      'Which kinds of news or hiring activity should trigger a lead for you?',
    options: SIGNAL_FOCUS_OPTIONS,
  },
];

const WELCOME_INDEX = 0;
const FIRST_CHIP_INDEX = 1;
const FINISH_INDEX = CHIP_STEPS.length + 1; // welcome + 4 chip steps + finish

@Component({
  selector: 'app-onboarding',
  standalone: true,
  imports: [],
  templateUrl: './onboarding.component.html',
  styleUrl: './onboarding.component.scss',
})
export class OnboardingComponent {
  private targeting = inject(TargetingService);
  private pipeline = inject(PipelineService);
  private router = inject(Router);
  protected store = inject(AuthStore);

  protected readonly steps = CHIP_STEPS;
  protected readonly stepIndex = signal<number>(WELCOME_INDEX);
  protected readonly totalChipSteps = CHIP_STEPS.length;

  protected readonly customerTypes = signal<Set<string>>(new Set());
  protected readonly sectors = signal<Set<string>>(new Set());
  protected readonly regions = signal<Set<string>>(new Set());
  protected readonly signalFocuses = signal<Set<string>>(new Set());

  protected readonly runFirstScan = signal<boolean>(true);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly info = signal<string | null>(null);

  // Round-trip these so a partially-filled preference row keeps its
  // server-assigned values when the wizard saves.
  private minimumConfidence = 0;
  private isActive = true;

  protected readonly canEdit = computed(() => this.store.isAdmin());

  // Tenant_user lands on the same route in read-only mode — backend
  // PUT /tenant/preferences is admin-only, so showing the wizard
  // controls would be misleading.
  protected readonly readonly = computed(() => !this.canEdit());

  protected readonly currentStep = computed<ChipStep | null>(() => {
    const idx = this.stepIndex();
    if (idx === WELCOME_INDEX || idx === FINISH_INDEX) return null;
    return CHIP_STEPS[idx - FIRST_CHIP_INDEX];
  });

  protected readonly isWelcome = computed(() => this.stepIndex() === WELCOME_INDEX);
  protected readonly isFinish = computed(() => this.stepIndex() === FINISH_INDEX);
  protected readonly progressPercent = computed(() => {
    const idx = this.stepIndex();
    if (idx <= WELCOME_INDEX) return 0;
    if (idx >= FINISH_INDEX) return 100;
    return Math.round(((idx - WELCOME_INDEX) / this.totalChipSteps) * 100);
  });

  protected readonly currentSelectionEmpty = computed(() => {
    const step = this.currentStep();
    if (!step) return false;
    return this.setFor(step.key)().size === 0;
  });

  constructor() {
    // Pre-fill any partial preferences the tenant already has — useful
    // when an admin re-enters the wizard after a partial save or when
    // we land on /onboarding because some dimension is empty.
    const cached = this.store.preferences();
    if (cached) {
      this.applyServerPrefs(cached);
    } else if (this.canEdit()) {
      // Cache may be stale (token refresh, deep link) — fetch once.
      this.targeting.get().subscribe({
        next: (prefs) => this.applyServerPrefs(prefs),
        error: () => {
          // 404 = no prefs yet; nothing to pre-fill. Other errors are
          // recoverable — the user can still complete the form.
        },
      });
    }
  }

  // ---- step navigation -------------------------------------------------

  next(): void {
    const idx = this.stepIndex();
    if (idx === FINISH_INDEX) return;

    // On chip steps, require ≥1 selection before moving forward. The
    // backend matching predicate treats empty arrays as "match nothing"
    // (no wildcards) so an empty step would silently produce zero
    // leads — fail loud instead.
    const step = this.currentStep();
    if (step && this.setFor(step.key)().size === 0) {
      this.error.set(`Pick at least one ${step.title.toLowerCase()}.`);
      return;
    }
    this.error.set(null);
    this.stepIndex.update((v) => v + 1);
  }

  back(): void {
    if (this.stepIndex() === WELCOME_INDEX) return;
    this.error.set(null);
    this.stepIndex.update((v) => v - 1);
  }

  goToStep(idx: number): void {
    if (idx < WELCOME_INDEX || idx > FINISH_INDEX) return;
    // Only allow jumping back to a previously-visited step.
    if (idx > this.stepIndex()) return;
    this.error.set(null);
    this.stepIndex.set(idx);
  }

  // ---- chip toggle -----------------------------------------------------

  isSelected(key: ChipStep['key'], value: string): boolean {
    return this.setFor(key)().has(value);
  }

  toggle(key: ChipStep['key'], value: string): void {
    if (!this.canEdit()) return;
    const current = this.setFor(key);
    const next = new Set(current());
    if (next.has(value)) next.delete(value);
    else next.add(value);
    current.set(next);
    this.error.set(null);
  }

  // ---- save flow -------------------------------------------------------

  protected payloadValid(): boolean {
    return (
      this.customerTypes().size > 0 &&
      this.sectors().size > 0 &&
      this.regions().size > 0 &&
      this.signalFocuses().size > 0
    );
  }

  finish(): void {
    if (!this.canEdit() || this.saving()) return;
    if (!this.payloadValid()) {
      this.error.set('Pick at least one option in each step before finishing.');
      return;
    }

    const payload: TenantPreferencesUpsert = {
      target_customer_types: [...this.customerTypes()],
      sectors: [...this.sectors()],
      regions: [...this.regions()],
      signal_focuses: [...this.signalFocuses()],
      minimum_confidence: this.minimumConfidence,
      is_active: this.isActive,
    };

    this.saving.set(true);
    this.error.set(null);
    this.targeting.upsert(payload).subscribe({
      next: (saved) => {
        this.store.setPreferences(saved);
        if (this.runFirstScan()) {
          this.triggerFirstScanThenRedirect();
        } else {
          this.saving.set(false);
          this.redirectAfterSave();
        }
      },
      error: () => {
        this.saving.set(false);
        this.error.set('Could not save preferences. Please try again.');
      },
    });
  }

  private triggerFirstScanThenRedirect(): void {
    this.pipeline.trigger().subscribe({
      next: () => {
        this.saving.set(false);
        this.info.set(
          'Your first scan has started. Leads will appear shortly.',
        );
        // Give the user a beat to read the toast before navigating.
        setTimeout(() => this.redirectAfterSave(), 1200);
      },
      error: () => {
        this.saving.set(false);
        // Preferences are saved; just the scheduling failed. Keep the
        // user on the wizard with a clear message — they can run the
        // scan later from the pipeline page.
        this.info.set(
          'Preferences saved, but the first scan could not be started. You can run it later.',
        );
        setTimeout(() => this.redirectAfterSave(), 1500);
      },
    });
  }

  private redirectAfterSave(): void {
    // Phase 8 added /company-leads as the sales-team primary screen.
    // Falling back to /opportunities here keeps the redirect safe even
    // if a future change removes the company-leads route.
    this.router.navigateByUrl('/company-leads').catch(() => {
      this.router.navigateByUrl('/opportunities');
    });
  }

  // ---- helpers ---------------------------------------------------------

  private setFor(key: ChipStep['key']) {
    switch (key) {
      case 'target_customer_types':
        return this.customerTypes;
      case 'sectors':
        return this.sectors;
      case 'regions':
        return this.regions;
      case 'signal_focuses':
        return this.signalFocuses;
    }
  }

  private applyServerPrefs(prefs: {
    target_customer_types: string[];
    sectors: string[];
    regions: string[];
    signal_focuses: string[];
    minimum_confidence: number;
    is_active: boolean;
  }): void {
    this.customerTypes.set(new Set(prefs.target_customer_types));
    this.sectors.set(new Set(prefs.sectors));
    this.regions.set(new Set(prefs.regions));
    this.signalFocuses.set(new Set(prefs.signal_focuses));
    this.minimumConfidence = prefs.minimum_confidence ?? 0;
    this.isActive = prefs.is_active ?? true;
  }

  protected selectionSummary(key: ChipStep['key']): string {
    const set = this.setFor(key)();
    if (set.size === 0) return 'None selected';
    const step = CHIP_STEPS.find((s) => s.key === key);
    if (!step) return `${set.size} selected`;
    const labels = step.options
      .filter((o) => set.has(o.value))
      .map((o) => o.label);
    return labels.join(', ');
  }

  protected stepLabel(idx: number): string {
    if (idx === WELCOME_INDEX) return 'Welcome';
    if (idx === FINISH_INDEX) return 'Finish';
    return CHIP_STEPS[idx - FIRST_CHIP_INDEX].title;
  }
}
