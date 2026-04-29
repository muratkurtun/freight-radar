import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';

import { AuthStore } from '../../core/auth/auth.store';
import { SourceType } from '../../core/models/enums.model';
import {
  SOURCE_TYPE_OPTIONS,
  Source,
  SourceCreate,
  SourceUpdate,
} from '../../core/models/source.model';
import { PipelineService } from '../pipeline/pipeline.service';
import { SourcesService } from './sources.service';

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
  selector: 'app-sources',
  standalone: true,
  imports: [DatePipe, ReactiveFormsModule],
  templateUrl: './sources.component.html',
  styleUrl: './sources.component.scss',
})
export class SourcesComponent {
  private service = inject(SourcesService);
  private pipeline = inject(PipelineService);
  private fb = inject(FormBuilder);
  protected store = inject(AuthStore);

  protected readonly typeOptions = SOURCE_TYPE_OPTIONS;

  protected readonly items = signal<Source[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly info = signal<string | null>(null);

  protected readonly editingId = signal<string | null>(null);
  protected readonly formOpen = signal(false);
  protected readonly saving = signal(false);
  protected readonly busyRowId = signal<string | null>(null);
  protected readonly triggering = signal(false);

  protected readonly canManage = computed(() => this.store.isAdmin());

  protected readonly form = this.fb.nonNullable.group({
    source_type: this.fb.nonNullable.control<SourceType>('news', Validators.required),
    name: this.fb.nonNullable.control('', [Validators.required, Validators.maxLength(200)]),
    url: this.fb.nonNullable.control('', [Validators.required, Validators.maxLength(1000), urlValidator]),
    is_active: this.fb.nonNullable.control(true),
  });

  constructor() {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service.list({ limit: 100 }).subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Kaynaklar yüklenemedi.');
      },
    });
  }

  startCreate(): void {
    this.editingId.set(null);
    this.form.reset({ source_type: 'news', name: '', url: '', is_active: true });
    this.form.controls.source_type.enable();
    this.formOpen.set(true);
  }

  startEdit(source: Source): void {
    this.editingId.set(source.id);
    this.form.reset({
      source_type: source.source_type,
      name: source.name,
      url: source.url,
      is_active: source.is_active,
    });
    // source_type is immutable per backend SourceUpdate.
    this.form.controls.source_type.disable();
    this.formOpen.set(true);
  }

  cancelForm(): void {
    this.formOpen.set(false);
    this.editingId.set(null);
    this.form.controls.source_type.enable();
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.error.set(null);

    const editingId = this.editingId();
    const raw = this.form.getRawValue();

    if (editingId) {
      const payload: SourceUpdate = {
        name: raw.name.trim(),
        url: raw.url.trim(),
        is_active: raw.is_active,
      };
      this.service.update(editingId, payload).subscribe({
        next: () => {
          this.saving.set(false);
          this.cancelForm();
          this.flashInfo('Kaynak güncellendi.');
          this.reload();
        },
        error: () => {
          this.saving.set(false);
          this.error.set('Kaynak güncellenemedi.');
        },
      });
    } else {
      const payload: SourceCreate = {
        source_type: raw.source_type,
        name: raw.name.trim(),
        url: raw.url.trim(),
        is_active: raw.is_active,
      };
      this.service.create(payload).subscribe({
        next: () => {
          this.saving.set(false);
          this.cancelForm();
          this.flashInfo('Kaynak eklendi.');
          this.reload();
        },
        error: () => {
          this.saving.set(false);
          this.error.set('Kaynak eklenemedi.');
        },
      });
    }
  }

  toggleActive(source: Source): void {
    if (this.busyRowId()) return;
    this.busyRowId.set(source.id);
    this.service
      .update(source.id, { is_active: !source.is_active })
      .subscribe({
        next: () => {
          this.busyRowId.set(null);
          this.flashInfo(source.is_active ? 'Kaynak pasifleştirildi.' : 'Kaynak aktifleştirildi.');
          this.reload();
        },
        error: () => {
          this.busyRowId.set(null);
          this.error.set('Durum güncellenemedi.');
        },
      });
  }

  remove(source: Source): void {
    if (this.busyRowId()) return;
    const ok = window.confirm(
      `"${source.name}" kaynağını silmek istediğine emin misin? Bu işlem geri alınamaz.`,
    );
    if (!ok) return;
    this.busyRowId.set(source.id);
    this.service.remove(source.id).subscribe({
      next: () => {
        this.busyRowId.set(null);
        this.flashInfo('Kaynak silindi.');
        this.reload();
      },
      error: () => {
        this.busyRowId.set(null);
        this.error.set('Kaynak silinemedi.');
      },
    });
  }

  runPipeline(): void {
    if (this.triggering()) return;
    this.triggering.set(true);
    this.pipeline.trigger().subscribe({
      next: (res) => {
        this.triggering.set(false);
        this.flashInfo(res.message || 'Pipeline started');
      },
      error: () => {
        this.triggering.set(false);
        this.error.set('Pipeline tetiklenemedi.');
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

  private flashInfo(msg: string): void {
    this.info.set(msg);
    setTimeout(() => {
      if (this.info() === msg) this.info.set(null);
    }, 3500);
  }
}
