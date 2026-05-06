import { Injectable, computed, signal } from '@angular/core';
import { CurrentUser } from '../models/auth.model';
import { TenantPreferences } from '../models/preferences.model';

const TOKEN_KEY = 'or_admin_token';

@Injectable({ providedIn: 'root' })
export class AuthStore {
  readonly token = signal<string | null>(this.readToken());
  readonly currentUser = signal<CurrentUser | null>(null);

  /**
   * Cached tenant preferences for the current session. `null` covers
   * both "haven't fetched yet" and "fetched, server returned 404 (not
   * configured)"; the `preferencesLoaded` flag distinguishes them so
   * `onboardingGuard` knows whether it still needs to fetch.
   */
  readonly preferences = signal<TenantPreferences | null>(null);
  readonly preferencesLoaded = signal(false);

  readonly isAuthenticated = computed(() => this.token() !== null);
  readonly isAdmin = computed(() => {
    const role = this.currentUser()?.role;
    return role === 'tenant_admin' || role === 'platform_admin';
  });
  readonly isPlatformAdmin = computed(
    () => this.currentUser()?.role === 'platform_admin',
  );
  readonly subscriptionStatus = computed(() => this.currentUser()?.subscription_status ?? null);
  readonly isTrialExpired = computed(() => this.subscriptionStatus() === 'expired');
  readonly isOnTrial = computed(() => this.subscriptionStatus() === 'trial');

  /**
   * Onboarding is "complete" when the tenant has a preference row AND
   * has picked at least one value in every one of the four taxonomies.
   * Empty arrays match no source in the platform pool (no wildcards
   * by product strategy — see Phase 4), so a partial preference is
   * effectively the same as no preference.
   */
  readonly isOnboardingComplete = computed(() => {
    const p = this.preferences();
    if (!p) return false;
    return (
      p.target_customer_types.length > 0 &&
      p.sectors.length > 0 &&
      p.regions.length > 0 &&
      p.signal_focuses.length > 0
    );
  });

  setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
    this.token.set(token);
  }

  setCurrentUser(user: CurrentUser): void {
    this.currentUser.set(user);
  }

  setPreferences(prefs: TenantPreferences | null): void {
    this.preferences.set(prefs);
    this.preferencesLoaded.set(true);
  }

  clear(): void {
    localStorage.removeItem(TOKEN_KEY);
    this.token.set(null);
    this.currentUser.set(null);
    this.preferences.set(null);
    this.preferencesLoaded.set(false);
  }

  private readToken(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  }
}
