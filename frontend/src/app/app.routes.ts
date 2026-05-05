import { Routes } from '@angular/router';
import {
  adminGuard,
  authGuard,
  platformAdminGuard,
  publicGuard,
  trialGuard,
} from './core/auth/auth.guard';

export const routes: Routes = [
  // --- PUBLIC ---
  {
    path: 'login',
    canActivate: [publicGuard],
    loadChildren: () =>
      import('./features/login/login.routes').then((m) => m.LOGIN_ROUTES),
  },
  {
    path: 'register',
    canActivate: [publicGuard],
    loadChildren: () =>
      import('./features/register/register.routes').then((m) => m.REGISTER_ROUTES),
  },

  // --- AUTHED BUT OUTSIDE THE SHELL (accessible to expired users) ---
  {
    path: 'trial-welcome',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/trial/trial-welcome.component').then((m) => m.TrialWelcomeComponent),
  },
  {
    path: 'trial-expired',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/trial/trial-expired.component').then((m) => m.TrialExpiredComponent),
  },
  {
    path: 'upgrade',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/trial/upgrade.component').then((m) => m.UpgradeComponent),
  },

  // --- APP SHELL (authed + subscription active) ---
  {
    path: '',
    canActivate: [trialGuard],
    loadComponent: () =>
      import('./layout/shell/shell.component').then((m) => m.ShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'opportunities' },
      {
        path: 'company-leads',
        loadChildren: () =>
          import('./features/company-leads/company-leads.routes').then(
            (m) => m.COMPANY_LEADS_ROUTES,
          ),
      },
      {
        path: 'opportunities',
        loadChildren: () =>
          import('./features/opportunities/opportunities.routes').then(
            (m) => m.OPPORTUNITY_ROUTES,
          ),
      },
      {
        path: 'reviews',
        canActivate: [adminGuard],
        loadChildren: () =>
          import('./features/reviews/reviews.routes').then((m) => m.REVIEWS_ROUTES),
      },
      {
        path: 'pipeline',
        canActivate: [adminGuard],
        loadChildren: () =>
          import('./features/pipeline/pipeline.routes').then((m) => m.PIPELINE_ROUTES),
      },
      {
        path: 'targeting',
        loadChildren: () =>
          import('./features/targeting/targeting.routes').then((m) => m.TARGETING_ROUTES),
      },
      {
        path: 'source-pool',
        canActivate: [platformAdminGuard],
        loadChildren: () =>
          import('./features/source-pool/source-pool.routes').then((m) => m.SOURCE_POOL_ROUTES),
      },
    ],
  },

  { path: '**', redirectTo: '' },
];
