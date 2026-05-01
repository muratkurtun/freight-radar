import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';

import { SourceType } from '../../core/models/enums.model';
import {
  CUSTOMER_TYPE_OPTIONS,
  REGION_OPTIONS,
  SECTOR_OPTIONS,
  SIGNAL_FOCUS_OPTIONS,
  TaxonomyOption,
} from '../../core/models/preferences.model';
import {
  PlatformSource,
  PlatformSourceCreate,
  PlatformSourceUpdate,
  SOURCE_TYPE_OPTIONS,
} from '../../core/models/source.model';
import { SourcePoolService } from './source-pool.service';

interface TagGroup {
  key: 'region_tags' | 'sector_tags' | 'customer_type_tags' | 'signal_focus_tags';
  label: string;
  options: TaxonomyOption[];
}

const TAG_GROUPS: TagGroup[] = [
  { key: 'region_tags', label: 'Regions', options: REGION_OPTIONS },
  { key: 'sector_tags', label: 'Sectors', options: SECTOR_OPTIONS },
  { key: 'customer_type_tags', label: 'Customer Types', options: CUSTOMER_TYPE_OPTIONS },
  { key: 'signal_focus_tags', label: 'Signal Focuses', options: SIGNAL_FOCUS_OPTIONS },
];

function urlValidator(control: AbstractControl): ValidationErrors | null {
  const value = (control.value ?? '').trim();
  if (!value) return null;
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return { url: true };
    }
    return null;
  } catch {
    return { url: true };
  }
}

@Component({
  selector: 'app-source-pool',
  standalone: true,
  imports: [DatePipe, ReactiveFormsModule],
  templateUrl: './source-pool.component.html',
  styleUrl: './source-pool.component.scss',
})
export class SourcePoolComponent {
  private service = inject(SourcePoolService);
  private fb = inject(FormBuilder);

  protected readonly typeOptions = SOURCE_TYPE_OPTIONS;
  protected readonly tagGroups = TAG_GROUPS;

  protected readonly items = signal<PlatformSource[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly info = signal<string | null>(null);

  protected readonly editingId = signal<string | null>(null);
  protected readonly formOpen = signal(false);
  protected readonly saving = signal(false);
  protected readonly busyRowId = signal<string | null>(null);
  protected readonly showTagErrors = signal(false);

  // Tag selections live outside the FormGroup because chip toggles play
  // nicer with signal-backed Sets than with FormArrays for this UI.
  protected readonly tagSelections = {
    region_tags: signal<Set<string>>(new Set()),
    sector_tags: signal<Set<string>>(new Set()),
    customer_type_tags: signal<Set<string>>(new Set()),
    signal_focus_tags: signal<Set<string>>(new Set()),
  } as const;

  /** A source must have ≥1 tag in every dimension before it can be saved
   *  — empty arrays match no tenants (no wildcards, by product strategy). */
  protected readonly tagsValid = computed(
    () =>
      this.tagSelections.region_tags().size > 0 &&
      this.tagSelections.sector_tags().size > 0 &&
      this.tagSelections.customer_type_tags().size > 0 &&
      this.tagSelections.signal_focus_tags().size > 0,
  );

  protected readonly form = this.fb.nonNullable.group({
    source_type: this.fb.nonNullable.control<SourceType>('news', Validators.required),
    name: this.fb.nonNullable.control('', [Validators.required, Validators.maxLength(200)]),
    url: this.fb.nonNullable.control('', [Validators.required, Validators.maxLength(1000), urlValidator]),
    is_active: this.fb.nonNullable.control(true),
    language: this.fb.nonNullable.control(''),
    priority: this.fb.nonNullable.control(100, [Validators.min(0), Validators.max(10000)]),
    quality_score: this.fb.control<number | null>(null),
    noise_level: this.fb.control<number | null>(null),
  });

  constructor() {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service.list({ limit: 200 }).subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Could not load source pool.');
      },
    });
  }

  // ---- form open / close ------------------------------------------

  startCreate(): void {
    this.editingId.set(null);
    this.form.reset({
      source_type: 'news',
      name: '',
      url: '',
      is_active: true,
      language: '',
      priority: 100,
      quality_score: null,
      noise_level: null,
    });
    this.form.controls.source_type.enable();
    this.resetTags();
    this.showTagErrors.set(false);
    this.formOpen.set(true);
  }

  startEdit(source: PlatformSource): void {
    this.editingId.set(source.id);
    this.form.reset({
      source_type: source.source_type,
      name: source.name,
      url: source.url,
      is_active: source.is_active,
      language: source.language ?? '',
      priority: source.priority,
      quality_score: source.quality_score,
      noise_level: source.noise_level,
    });
    // source_type is immutable per backend PlatformSourceUpdate.
    this.form.controls.source_type.disable();
    this.tagSelections.region_tags.set(new Set(source.region_tags));
    this.tagSelections.sector_tags.set(new Set(source.sector_tags));
    this.tagSelections.customer_type_tags.set(new Set(source.customer_type_tags));
    this.tagSelections.signal_focus_tags.set(new Set(source.signal_focus_tags));
    this.showTagErrors.set(false);
    this.formOpen.set(true);
  }

  cancelForm(): void {
    this.formOpen.set(false);
    this.editingId.set(null);
    this.form.controls.source_type.enable();
  }

  // ---- chip selectors ---------------------------------------------

  isTagSelected(key: TagGroup['key'], value: string): boolean {
    return this.tagSelections[key]().has(value);
  }

  toggleTag(key: TagGroup['key'], value: string): void {
    const current = this.tagSelections[key];
    const next = new Set(current());
    if (next.has(value)) next.delete(value);
    else next.add(value);
    current.set(next);
    this.showTagErrors.set(false);
  }

  tagGroupEmpty(key: TagGroup['key']): boolean {
    return this.tagSelections[key]().size === 0;
  }

  tagLabelFor(key: TagGroup['key'], value: string): string {
    const group = this.tagGroups.find((g) => g.key === key);
    return group?.options.find((o) => o.value === value)?.label ?? value;
  }

  private resetTags(): void {
    this.tagSelections.region_tags.set(new Set());
    this.tagSelections.sector_tags.set(new Set());
    this.tagSelections.customer_type_tags.set(new Set());
    this.tagSelections.signal_focus_tags.set(new Set());
  }

  private selectedTags(key: TagGroup['key']): string[] {
    return [...this.tagSelections[key]()];
  }

  // ---- save / row actions -----------------------------------------

  submit(): void {
    if (this.form.invalid || !this.tagsValid()) {
      this.form.markAllAsTouched();
      this.showTagErrors.set(true);
      return;
    }
    this.saving.set(true);
    this.error.set(null);

    const editingId = this.editingId();
    const raw = this.form.getRawValue();
    const language = raw.language.trim() || null;
    const tags = {
      region_tags: this.selectedTags('region_tags'),
      sector_tags: this.selectedTags('sector_tags'),
      customer_type_tags: this.selectedTags('customer_type_tags'),
      signal_focus_tags: this.selectedTags('signal_focus_tags'),
    };

    if (editingId) {
      const payload: PlatformSourceUpdate = {
        name: raw.name.trim(),
        url: raw.url.trim(),
        is_active: raw.is_active,
        language,
        priority: raw.priority,
        quality_score: raw.quality_score,
        noise_level: raw.noise_level,
        ...tags,
      };
      this.service.update(editingId, payload).subscribe({
        next: () => this.afterSave('Source updated.'),
        error: () => this.onSaveError('Could not update source.'),
      });
    } else {
      const payload: PlatformSourceCreate = {
        source_type: raw.source_type,
        name: raw.name.trim(),
        url: raw.url.trim(),
        is_active: raw.is_active,
        language,
        priority: raw.priority,
        quality_score: raw.quality_score,
        noise_level: raw.noise_level,
        ...tags,
      };
      this.service.create(payload).subscribe({
        next: () => this.afterSave('Source added.'),
        error: () => this.onSaveError('Could not add source.'),
      });
    }
  }

  private afterSave(msg: string): void {
    this.saving.set(false);
    this.cancelForm();
    this.flashInfo(msg);
    this.reload();
  }

  private onSaveError(msg: string): void {
    this.saving.set(false);
    this.error.set(msg);
  }

  toggleActive(source: PlatformSource): void {
    if (this.busyRowId()) return;
    this.busyRowId.set(source.id);
    this.service.update(source.id, { is_active: !source.is_active }).subscribe({
      next: () => {
        this.busyRowId.set(null);
        this.flashInfo(source.is_active ? 'Deactivated.' : 'Activated.');
        this.reload();
      },
      error: () => {
        this.busyRowId.set(null);
        this.error.set('Could not update status.');
      },
    });
  }

  remove(source: PlatformSource): void {
    if (this.busyRowId()) return;
    const ok = window.confirm(
      `Delete "${source.name}"?\n\n` +
        'This is destructive: the source row, its pipeline_runs and ' +
        'raw_source_items rows are removed via FK cascade.\n\n' +
        'Prefer Deactivate to take the source out of rotation while ' +
        'preserving historical data.',
    );
    if (!ok) return;
    this.busyRowId.set(source.id);
    this.service.remove(source.id).subscribe({
      next: () => {
        this.busyRowId.set(null);
        this.flashInfo('Source deleted.');
        this.reload();
      },
      error: () => {
        this.busyRowId.set(null);
        this.error.set('Could not delete source.');
      },
    });
  }

  typeLabel(type: SourceType): string {
    return this.typeOptions.find((o) => o.value === type)?.label ?? type;
  }

  hasError(name: 'source_type' | 'name' | 'url'): boolean {
    const c = this.form.controls[name];
    return c.invalid && (c.touched || c.dirty);
  }

  rowTagLabels(s: PlatformSource, key: TagGroup['key']): string[] {
    const values = (s as unknown as Record<string, string[]>)[key] ?? [];
    return values.map((v) => this.tagLabelFor(key, v));
  }

  private flashInfo(msg: string): void {
    this.info.set(msg);
    setTimeout(() => {
      if (this.info() === msg) this.info.set(null);
    }, 3500);
  }
}
