import { Injectable, inject } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { ApiBaseService } from '../http/api-base.service';
import { AuthStore } from './auth.store';
import {
  CurrentUser,
  LoginRequest,
  RegisterRequest,
  RegisterResponse,
  TokenResponse,
} from '../models/auth.model';

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

  logout(): void {
    this.store.clear();
  }
}
