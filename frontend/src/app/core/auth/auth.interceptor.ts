import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthStore } from './auth.store';

/**
 * Attaches the JWT as a Bearer token on every outgoing request except
 * the login call itself.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const store = inject(AuthStore);
  const token = store.token();

  if (!token || req.url.includes('/auth/login')) {
    return next(req);
  }

  const authed = req.clone({
    setHeaders: { Authorization: `Bearer ${token}` },
  });
  return next(authed);
};
