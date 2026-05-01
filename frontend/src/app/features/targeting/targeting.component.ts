import { Component, computed, inject, signal } from '@angular/core';

import { AuthStore } from '../../core/auth/auth.store';
import {
  CUSTOMER_TYPE_OPTIONS,
  REGION_OPTIONS,
  SECTOR_OPTIONS,
  SIGNAL_FOCUS_OPTIONS,
  TaxonomyOption,
  TenantPreferences,
  TenantPreferencesUpsert,
} from '../../core/models/preferences.model';
import { PipelineService } from '../pipeline/pipeline.service';
import { TargetingService } from './targeting.service';

interface ChipGroup {
  key: 'target_customer_types' | 'sectors' | 'regions' | 'signal_focuses';
  label: string;
  options: TaxonomyOption[];
}

const GROUPS: ChipGroup[] = [
  { key: 'target_customer_types', label: 'Target Customer Type', options: CUSTOMER_TYPE_OPTIONS },
  { key: 'sectors', label: 'Sector', options: SECTOR_OPTIONS },
  { key: 'regions', label: 'Region', options: REGION_OPTIONS },
  { key: 'signal_focuses', label: 'Signal Focus', options: SIGNAL_FOCUS_OPTIONS },
];

@Component({
  selector: 'app-targeting',
  standalone: true,
  imports: [],
  templateUrl: './targeting.component.html',
  styleUrl: './targeting.component.scss',
})
export class TargetingComponent {
  private service = inject(TargetingService);
  private pipeline = inject(PipelineService);
  protected store = inject(AuthStore);

  protected readonly groups = GROUPS;

  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly triggering = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly info = signal<string | null>(null);

  protected readonly customerTypes = signal<Set<string>>(new Set());
  protected readonly sectors = signal<Set<string>>(new Set());
  protected readonly regions = signal<Set<string>>(new Set());
  protected readonly signalFocuses = signal<Set<string>>(new Set());

  // Hidden fields — round-tripped, not exposed in the UI to keep the
  // salesperson view simple. Defaults match the backend schema.
  private minimumConfidence = 0;
  private isActive = true;

  protected readonly canSave = computed(() => this.store.isAdmin());

  constructor() {
    this.load();
  }

  private load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service.get().subscribe({
      next: (pref) => {
        this.applyServerState(pref);
        this.loading.set(false);
      },
      error: (err) => {
        // 404 = no preferences saved yet. That's a normal first-run
        // state, not an error — show the default empty form.
        if (err?.status === 404) {
          this.loading.set(false);
          return;
        }
        this.loading.set(false);
        this.error.set('Could not load preferences.');
      },
    });
  }

  private applyServerState(pref: TenantPreferences): void {
    this.customerTypes.set(new Set(pref.target_customer_types));
    this.sectors.set(new Set(pref.sectors));
    this.regions.set(new Set(pref.regions));
    this.signalFocuses.set(new Set(pref.signal_focuses));
    this.minimumConfidence = pref.minimum_confidence ?? 0;
    this.isActive = pref.is_active;
  }

  private setFor(key: ChipGroup['key']) {
    switch (key) {
      case 'target_customer_types': return this.customerTypes;
      case 'sectors':                return this.sectors;
      case 'regions':                return this.regions;
      case 'signal_focuses':         return this.signalFocuses;
    }
  }

  isSelected(key: ChipGroup['key'], value: string): boolean {
    return this.setFor(key)().has(value);
  }

  toggle(key: ChipGroup['key'], value: string): void {
    if (!this.canSave()) return;
    const current = this.setFor(key);
    const next = new Set(current());
    if (next.has(value)) next.delete(value);
    else next.add(value);
    current.set(next);
  }

  save(): void {
    if (this.saving() || !this.canSave()) return;
    this.saving.set(true);
    this.error.set(null);
    this.info.set(null);

    const payload: TenantPreferencesUpsert = {
      target_customer_types: [...this.customerTypes()],
      sectors: [...this.sectors()],
      regions: [...this.regions()],
      signal_focuses: [...this.signalFocuses()],
      minimum_confidence: this.minimumConfidence,
      is_active: this.isActive,
    };

    this.service.upsert(payload).subscribe({
      next: (pref) => {
        this.applyServerState(pref);
        this.saving.set(false);
        this.flashInfo('Preferences saved.');
      },
      error: () => {
        this.saving.set(false);
        this.error.set('Could not save preferences.');
      },
    });
  }

  runPipeline(): void {
    if (this.triggering() || !this.canSave()) return;
    this.triggering.set(true);
    this.error.set(null);
    this.pipeline.trigger().subscribe({
      next: () => {
        this.triggering.set(false);
        this.flashInfo('Pipeline started. Results will appear in Opportunities.');
      },
      error: () => {
        this.triggering.set(false);
        this.error.set('Could not start the pipeline.');
      },
    });
  }

  private flashInfo(msg: string): void {
    this.info.set(msg);
    setTimeout(() => {
      if (this.info() === msg) this.info.set(null);
    }, 4000);
  }
}
