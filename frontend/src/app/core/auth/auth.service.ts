import { Injectable, inject } from '@angular/core';
import { Observable, catchError, of, tap } from 'rxjs';

import { ApiBaseService } from '../http/api-base.service';
import { AuthStore } from './auth.store';
import {
  CurrentUser,
  LoginRequest,
  RegisterRequest,
  RegisterResponse,
  TokenResponse,
} from '../models/auth.model';
import { TenantPreferences } from '../models/preferences.model';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private api = inject(ApiBaseService);
  private store = inject(AuthStore);

  login(payload: LoginRequest): Observable<TokenResponse> {
    return this.api
      .post<TokenResponse>('/auth/login', payload)
      .pipe(tap((res) => this.store.setToken(res.access_token)));
  }

  register(payload: RegisterRequest): Observable<RegisterResponse> {
    return this.api
      .post<RegisterResponse>('/auth/register', payload)
      .pipe(
        tap((res) => {
          this.store.setToken(res.access_token);
          this.store.setCurrentUser(res.user);
        }),
      );
  }

  fetchCurrentUser(): Observable<CurrentUser> {
    return this.api
      .get<CurrentUser>('/auth/me')
      .pipe(tap((user) => this.store.setCurrentUser(user)));
  }

  /**
   * Fetch + cache the tenant's preferences. Backend returns 404 when
   * the tenant has not configured them yet; that's a normal first-run
   * state, not an error — we cache `null` and let `isOnboardingComplete`
   * derive the badge / redirect behaviour. Any other error leaves the
   * cache empty so the next attempt retries.
   */
  fetchPreferences(): Observable<TenantPreferences | null> {
    return this.api.get<TenantPreferences>('/tenant/preferences').pipe(
      tap((prefs) => this.store.setPreferences(prefs)),
      catchError((err) => {
        if (err?.status === 404) {
          this.store.setPreferences(null);
          return of(null);
        }
        return of(null);
      }),
    );
  }

  logout(): void {
    this.store.clear();
  }
}
