import { Routes } from '@angular/router';

export const SOURCES_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./sources.component').then((m) => m.SourcesComponent),
  },
];
