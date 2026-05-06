import { Routes } from '@angular/router';
import {
  adminGuard,
  authGuard,
  onboardingGuard,
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

  // Onboarding sits outside the shell so the wizard renders without
  // sidebar / topbar distractions. trialGuard ensures the user is
  // authed + subscription-active; onboardingGuard is NOT applied here
  // (this is the destination — applying it would loop).
  {
    path: 'onboarding',
    canActivate: [trialGuard],
    loadChildren: () =>
      import('./features/onboarding/onboarding.routes').then(
        (m) => m.ONBOARDING_ROUTES,
      ),
  },

  // --- APP SHELL (authed + subscription active) ---
  {
    path: '',
    canActivate: [trialGuard],
    loadComponent: () =>
      import('./layout/shell/shell.component').then((m) => m.ShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'opportunities' },
      // Targeting + source-pool stay open inside the shell so an admin
      // can edit preferences without first being shoved through the
      // wizard. The four lead-facing routes below pick up
      // onboardingGuard so a tenant member with no preferences gets
      // redirected to /onboarding before they hit an empty leads list.
      {
        path: 'company-leads',
        canActivate: [onboardingGuard],
        loadChildren: () =>
          import('./features/company-leads/company-leads.routes').then(
            (m) => m.COMPANY_LEADS_ROUTES,
          ),
      },
      {
        path: 'opportunities',
        canActivate: [onboardingGuard],
        loadChildren: () =>
          import('./features/opportunities/opportunities.routes').then(
            (m) => m.OPPORTUNITY_ROUTES,
          ),
      },
      {
        path: 'reviews',
        canActivate: [adminGuard, onboardingGuard],
        loadChildren: () =>
          import('./features/reviews/reviews.routes').then((m) => m.REVIEWS_ROUTES),
      },
      {
        path: 'pipeline',
        canActivate: [adminGuard, onboardingGuard],
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
