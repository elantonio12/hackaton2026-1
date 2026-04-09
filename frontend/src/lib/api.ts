/**
 * API client and auth utilities for EcoRuta frontend.
 */

/** Root URL of the backend (no trailing slash, no /api/v1). */
export const API_ROOT = import.meta.env.PUBLIC_API_URL || 'https://apihackaton.syle.studio';

const API_BASE = `${API_ROOT}/api/v1`;

// ---------------------------------------------------------------------------
// JWT / localStorage helpers
// ---------------------------------------------------------------------------

export function saveAuth(token: string, user: Record<string, unknown>) {
  localStorage.setItem('ecoruta_token', token);
  localStorage.setItem('ecoruta_user', JSON.stringify(user));
}

export function getToken(): string | null {
  return localStorage.getItem('ecoruta_token');
}

export function getUser(): Record<string, unknown> | null {
  const raw = localStorage.getItem('ecoruta_user');
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export function clearAuth() {
  localStorage.removeItem('ecoruta_token');
  localStorage.removeItem('ecoruta_user');
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

// ---------------------------------------------------------------------------
// Role-based access control
// ---------------------------------------------------------------------------

export type Role = 'admin' | 'collector' | 'citizen';

/** Home path for each role — used by login redirect and access denials. */
export function homeForRole(role: string | undefined): string {
  switch (role) {
    case 'admin':     return '/admin';
    case 'collector': return '/recolector/ruta';
    default:          return '/usuario/info';
  }
}

export function redirectByRole(user: Record<string, unknown>) {
  window.location.href = homeForRole(user.role as string);
}

/**
 * Refresh the cached user from /auth/me.
 * - Updates localStorage with the latest user data
 * - Clears auth + redirects to /auth/login if the token is invalid
 * - Returns the fresh user, or null if not authenticated
 */
export async function refreshUser(): Promise<Record<string, unknown> | null> {
  if (!isAuthenticated()) return null;
  try {
    const res = await apiFetch('/auth/me');
    if (!res.ok) {
      clearAuth();
      window.location.href = '/auth/login';
      return null;
    }
    const data = await res.json();
    // /auth/me returns either the user directly or { user: ... }
    const user = data.user ?? data;
    localStorage.setItem('ecoruta_user', JSON.stringify(user));
    return user;
  } catch {
    return getUser();
  }
}

/**
 * Enforce that the current user has one of the allowed roles.
 * - Refreshes the user from the backend first (so role changes are detected)
 * - Redirects to the role's home if the user has the wrong role
 * - Redirects to /auth/login if not authenticated
 * - Returns the user if access is granted, otherwise null
 */
export async function requireRole(allowed: Role | Role[]): Promise<Record<string, unknown> | null> {
  if (!isAuthenticated()) {
    window.location.href = '/auth/login';
    return null;
  }
  const user = await refreshUser();
  if (!user) return null;
  const role = (user.role as string) || 'citizen';
  const allowedList = Array.isArray(allowed) ? allowed : [allowed];
  if (!allowedList.includes(role as Role)) {
    window.location.href = homeForRole(role);
    return null;
  }
  return user;
}

// ---------------------------------------------------------------------------
// API fetch wrapper
// ---------------------------------------------------------------------------

async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return fetch(`${API_BASE}${path}`, { ...options, headers });
}

// ---------------------------------------------------------------------------
// Auth API calls
// ---------------------------------------------------------------------------

export async function apiLogin(email: string, password: string) {
  const res = await apiFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al iniciar sesión');
  saveAuth(data.access_token, data.user);
  return data;
}

export async function apiInviteUser(name: string, email: string, role: string) {
  const res = await apiFetch('/auth/invite', {
    method: 'POST',
    body: JSON.stringify({ name, email, role }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al invitar usuario');
  return data;
}

export async function apiGetMe() {
  const res = await apiFetch('/auth/me');
  if (!res.ok) {
    clearAuth();
    throw new Error('Sesión expirada');
  }
  const data = await res.json();
  const user = data.user ?? data;
  localStorage.setItem('ecoruta_user', JSON.stringify(user));
  return user;
}

export async function apiLogout() {
  await apiFetch('/auth/logout', { method: 'POST' });
  clearAuth();
}
