import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthStore } from '../auth/auth.store';

/**
 * - 401 (not /auth/login)             -> clear session + /login
 * - 403 with code=trial_expired       -> flip store + /trial-expired
 * Everything else is re-thrown so feature components can render their
 * own messages.
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const store = inject(AuthStore);
  const router = inject(Router);

  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      if (err.status === 401 && !req.url.includes('/auth/login')) {
        store.clear();
        router.navigate(['/login']);
      } else if (err.status === 403 && err.error?.error?.code === 'trial_expired') {
        // Keep the user signed in — the expired screen needs the session.
        const u = store.currentUser();
        if (u && u.subscription_status !== 'expired') {
          store.setCurrentUser({ ...u, subscription_status: 'expired' });
        }
        router.navigate(['/trial-expired']);
      }
      return throwError(() => err);
    }),
  );
};
