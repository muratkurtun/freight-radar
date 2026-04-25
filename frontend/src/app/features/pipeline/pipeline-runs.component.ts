import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';

import { PipelineRunStatus } from '../../core/models/enums.model';
import { PipelineRun } from '../../core/models/pipeline.model';
import { PipelineService } from './pipeline.service';

@Component({
  selector: 'app-pipeline-runs',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './pipeline-runs.component.html',
  styleUrl: './pipeline-runs.component.scss',
})
export class PipelineRunsComponent {
  private service = inject(PipelineService);

  protected readonly items = signal<PipelineRun[]>([]);
  protected readonly loading = signal(false);
  protected readonly triggering = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly info = signal<string | null>(null);

  protected readonly statusFilter = signal<PipelineRunStatus | ''>('');

  constructor() {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.service.list({ status: this.statusFilter() || null, limit: 50 }).subscribe({
      next: (res) => {
        this.items.set(res.items);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Pipeline kayıtları alınamadı.');
      },
    });
  }

  trigger(): void {
    if (this.triggering()) return;
    this.triggering.set(true);
    this.info.set(null);
    this.service.trigger().subscribe({
      next: (res) => {
        this.info.set(res.message);
        this.triggering.set(false);
        // new run row shows up in pipeline_runs once the background task
        // persists the RUNNING row; wait a beat before refreshing.
        setTimeout(() => this.reload(), 1500);
      },
      error: () => {
        this.error.set('Pipeline tetiklenemedi.');
        this.triggering.set(false);
      },
    });
  }

  onFilterChange(value: string): void {
    this.statusFilter.set(value as PipelineRunStatus | '');
    this.reload();
  }

  statusClass(status: PipelineRunStatus): string {
    switch (status) {
      case 'success':
        return 'chip success';
      case 'failed':
        return 'chip danger';
      case 'running':
        return 'chip warning';
    }
  }

  duration(run: PipelineRun): string {
    if (!run.finished_at) return '—';
    const diffMs = new Date(run.finished_at).getTime() - new Date(run.started_at).getTime();
    const sec = Math.max(0, Math.round(diffMs / 1000));
    if (sec < 60) return `${sec}s`;
    return `${Math.floor(sec / 60)}m ${sec % 60}s`;
  }

  truncate(text: string, max = 80): string {
    return text.length > max ? `${text.slice(0, max)}…` : text;
  }
}
