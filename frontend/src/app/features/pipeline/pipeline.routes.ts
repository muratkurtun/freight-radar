import { Routes } from '@angular/router';

export const PIPELINE_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'runs' },
  {
    path: 'runs',
    loadComponent: () =>
      import('./pipeline-runs.component').then((m) => m.PipelineRunsComponent),
  },
];
