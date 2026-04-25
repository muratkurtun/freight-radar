import { Injectable, computed, signal } from '@angular/core';
import { CurrentUser } from '../models/auth.model';

const TOKEN_KEY = 'or_admin_token';

@Injectable({ providedIn: 'root' })
export class AuthStore {
  readonly token = signal<string | null>(this.readToken());
  readonly currentUser = signal<CurrentUser | null>(null);

  readonly isAuthenticated = computed(() => this.token() !== null);
  readonly isAdmin = computed(() => {
    const role = this.currentUser()?.role;
    return role === 'tenant_admin' || role === 'platform_admin';
  });
  readonly subscriptionStatus = computed(() => this.currentUser()?.subscription_status ?? null);
  readonly isTrialExpired = computed(() => this.subscriptionStatus() === 'expired');
  readonly isOnTrial = computed(() => this.subscriptionStatus() === 'trial');

  setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
    this.token.set(token);
  }

  setCurrentUser(user: CurrentUser): void {
    this.currentUser.set(user);
  }

  clear(): void {
    localStorage.removeItem(TOKEN_KEY);
    this.token.set(null);
    this.currentUser.set(null);
  }

  private readToken(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  }
}
