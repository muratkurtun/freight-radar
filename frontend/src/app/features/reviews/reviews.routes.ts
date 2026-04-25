import { Routes } from '@angular/router';

export const REVIEWS_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'pending' },
  {
    path: 'pending',
    loadComponent: () =>
      import('./reviews-pending.component').then((m) => m.ReviewsPendingComponent),
  },
];
