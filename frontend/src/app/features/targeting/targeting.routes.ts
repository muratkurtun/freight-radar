import { Routes } from '@angular/router';

export const TARGETING_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./targeting.component').then((m) => m.TargetingComponent),
  },
];
