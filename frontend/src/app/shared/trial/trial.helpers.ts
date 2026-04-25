import { CurrentUser } from '../../core/models/auth.model';

/** Whole days remaining until trial_ends_at. Negative when expired. */
export function trialDaysRemaining(user: CurrentUser | null): number | null {
  if (!user?.trial_ends_at) return null;
  const end = new Date(user.trial_ends_at).getTime();
  const now = Date.now();
  return Math.ceil((end - now) / (1000 * 60 * 60 * 24));
}

/** True when the backend-derived status is 'expired'. */
export function isTrialExpired(user: CurrentUser | null): boolean {
  return user?.subscription_status === 'expired';
}

/** True while the user is on an active trial (not yet expired). */
export function isOnTrial(user: CurrentUser | null): boolean {
  return user?.subscription_status === 'trial';
}
