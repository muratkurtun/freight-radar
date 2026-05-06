import { Injectable, inject } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { AuthStore } from '../../core/auth/auth.store';
import { ApiBaseService } from '../../core/http/api-base.service';
import {
  TenantPreferences,
  TenantPreferencesUpsert,
} from '../../core/models/preferences.model';

@Injectable({ providedIn: 'root' })
export class TargetingService {
  private api = inject(ApiBaseService);
  private store = inject(AuthStore);

  /** GET /tenant/preferences. Backend returns 404 (NotFoundError) when
   *  the tenant has not configured preferences yet — callers translate
   *  that into the empty/default UI state, not an error toast.
   *
   *  On success the result is cached in AuthStore so onboardingGuard
   *  can decide synchronously on the next navigation. */
  get(): Observable<TenantPreferences> {
    return this.api
      .get<TenantPreferences>('/tenant/preferences')
      .pipe(tap((prefs) => this.store.setPreferences(prefs)));
  }

  /** PUT /tenant/preferences. The cache is refreshed from the server
   *  response so a partial save (e.g. wizard half-done) immediately
   *  updates `isOnboardingComplete`. */
  upsert(payload: TenantPreferencesUpsert): Observable<TenantPreferences> {
    return this.api
      .put<TenantPreferences>('/tenant/preferences', payload)
      .pipe(tap((prefs) => this.store.setPreferences(prefs)));
  }
}
