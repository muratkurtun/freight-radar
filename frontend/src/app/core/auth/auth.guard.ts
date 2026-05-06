import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';
import { Observable, catchError, map, of } from 'rxjs';

import { AuthService } from './auth.service';
import { AuthStore } from './auth.store';

/**
 * Require a valid session.
 * - No token                              -> /login
 * - Token, no profile                     -> fetch /auth/me first
 * - Token + profile                       -> pass
 * - Token but /me fails (401, deactivated) -> clear + /login
 *
 * Subscription status is NOT checked here — a trial-expired user must
 * still reach /trial-expired, /upgrade and /auth/me. See `trialGuard`
 * for the app-shell gate.
 */
export const authGuard: CanActivateFn = (): boolean | Observable<boolean> => {
  const store = inject(AuthStore);
  const router = inject(Router);
  const auth = inject(AuthService);

  if (!store.token()) {
    router.navigate(['/login']);
    return false;
  }
  if (store.currentUser()) {
    return true;
  }
  return auth.fetchCurrentUser().pipe(
    map(() => true),
    catchError(() => {
      store.clear();
      router.navigate(['/login']);
      return of(false);
    }),
  );
};

/** App shell gate: authed + subscription not expired. */
export const trialGuard: CanActivateFn = (route, state) => {
  const store = inject(AuthStore);
  const router = inject(Router);

  const base = authGuard(route, state);
  const check = (ok: boolean): boolean => {
    if (!ok) return false;
    if (store.isTrialExpired()) {
      router.navigate(['/trial-expired']);
      return false;
    }
    return true;
  };

  if (base === false) return false;
  if (base === true) return check(true);
  return (base as Observable<boolean>).pipe(map(check));
};

/** Admin + authed + not expired. */
export const adminGuard: CanActivateFn = (route, state) => {
  const store = inject(AuthStore);
  const router = inject(Router);

  const base = trialGuard(route, state);
  const check = (ok: boolean): boolean => {
    if (!ok) return false;
    if (store.isAdmin()) return true;
    router.navigate(['/opportunities']);
    return false;
  };

  if (base === false) return false;
  if (base === true) return check(true);
  return (base as Observable<boolean>).pipe(map(check));
};

/** Strictly platform_admin. Tenant admins are bounced to /opportunities.
 *  Used for cross-tenant tooling like the platform Source Pool. */
export const platformAdminGuard: CanActivateFn = (route, state) => {
  const store = inject(AuthStore);
  const router = inject(Router);

  const base = trialGuard(route, state);
  const check = (ok: boolean): boolean => {
    if (!ok) return false;
    if (store.isPlatformAdmin()) return true;
    router.navigate(['/opportunities']);
    return false;
  };

  if (base === false) return false;
  if (base === true) return check(true);
  return (base as Observable<boolean>).pipe(map(check));
};

/** /login + /register: bounce already-authed users straight into the app. */
export const publicGuard: CanActivateFn = () => {
  const store = inject(AuthStore);
  const router = inject(Router);
  if (store.token()) {
    router.navigate(['/']);
    return false;
  }
  return true;
};

/**
 * Tenant-side onboarding gate.
 *
 * - platform_admin always passes (cross-tenant; no per-tenant preferences).
 * - any other authenticated tenant member with completed targeting passes.
 * - tenant member with missing / partial preferences gets sent to
 *   /onboarding. Tenant_user lands on the same route in read-only mode
 *   ("ask your tenant admin to finish setup") because the backend
 *   PUT /tenant/preferences is admin-only.
 *
 * The guard ensures preferences are loaded before deciding (one HTTP
 * call on first protected nav per session); subsequent navs are sync
 * via the cached signal.
 *
 * Pair this with `trialGuard` or `adminGuard` on the route — this
 * guard does not re-check auth or subscription on its own.
 */
export const onboardingGuard: CanActivateFn = (): boolean | UrlTree | Observable<boolean | UrlTree> => {
  const store = inject(AuthStore);
  const auth = inject(AuthService);
  const router = inject(Router);

  if (store.isPlatformAdmin()) return true;

  const decide = (): boolean | UrlTree => {
    if (store.isOnboardingComplete()) return true;
    return router.parseUrl('/onboarding');
  };

  if (store.preferencesLoaded()) {
    return decide();
  }

  return auth.fetchPreferences().pipe(
    map(() => decide()),
    catchError(() => of(decide())),
  );
};
