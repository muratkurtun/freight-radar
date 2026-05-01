import { Routes } from '@angular/router';

export const SOURCE_POOL_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./source-pool.component').then((m) => m.SourcePoolComponent),
  },
];
