import { SubscriptionStatus, UserRole } from './enums.model';

export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
}

export interface CurrentUser {
  user_id: string;
  tenant_id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  subscription_status: SubscriptionStatus;
  trial_ends_at: string | null;
}

export interface RegisterRequest {
  tenant_name: string;
  full_name: string;
  email: string;
  password: string;
}

export interface RegisterResponse {
  access_token: string;
  token_type: 'bearer';
  user: CurrentUser;
}
