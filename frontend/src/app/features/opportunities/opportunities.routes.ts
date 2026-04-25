import { Routes } from '@angular/router';

export const OPPORTUNITY_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./opportunities.component').then((m) => m.OpportunitiesComponent),
  },
];
