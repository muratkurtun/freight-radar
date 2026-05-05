import { Routes } from '@angular/router';

export const COMPANY_LEADS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./company-leads-list.component').then(
        (m) => m.CompanyLeadsListComponent,
      ),
  },
  {
    path: ':companyId',
    loadComponent: () =>
      import('./company-leads-detail.component').then(
        (m) => m.CompanyLeadsDetailComponent,
      ),
  },
];
