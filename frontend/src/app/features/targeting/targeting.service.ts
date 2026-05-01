import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiBaseService } from '../../core/http/api-base.service';
import {
  TenantPreferences,
  TenantPreferencesUpsert,
} from '../../core/models/preferences.model';

@Injectable({ providedIn: 'root' })
export class TargetingService {
  private api = inject(ApiBaseService);

  /** GET /tenant/preferences. Backend returns 404 (NotFoundError) when
   *  the tenant has not configured preferences yet — callers translate
   *  that into the empty/default UI state, not an error toast. */
  get(): Observable<TenantPreferences> {
    return this.api.get<TenantPreferences>('/tenant/preferences');
  }

  upsert(payload: TenantPreferencesUpsert): Observable<TenantPreferences> {
    return this.api.put<TenantPreferences>('/tenant/preferences', payload);
  }
}
