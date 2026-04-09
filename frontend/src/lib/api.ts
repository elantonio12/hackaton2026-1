/**
 * API client and auth utilities for EcoRuta frontend.
 */

const API_BASE = import.meta.env.PUBLIC_API_URL || 'https://apihackaton.syle.studio/api/v1';

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
// Role-based redirect
// ---------------------------------------------------------------------------

export function redirectByRole(user: Record<string, unknown>) {
  const role = user.role as string || 'citizen';
  switch (role) {
    case 'admin':     window.location.href = '/admin'; break;
    case 'collector': window.location.href = '/recolector/ruta'; break;
    default:          window.location.href = '/usuario/info'; break;
  }
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

export async function apiRegister(name: string, email: string, password: string) {
  const res = await apiFetch('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ name, email, password }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al registrarse');
  // If auto-verified (no Resend), save auth
  if (data.access_token) {
    saveAuth(data.access_token, data.user);
  }
  return data;
}

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

export async function apiVerifyEmail(token: string) {
  const res = await apiFetch(`/auth/verify-email?token=${encodeURIComponent(token)}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al verificar');
  if (data.access_token) {
    saveAuth(data.access_token, data.user);
  }
  return data;
}

export async function apiGetMe() {
  const res = await apiFetch('/auth/me');
  if (!res.ok) {
    clearAuth();
    throw new Error('Sesión expirada');
  }
  return res.json();
}

export async function apiLogout() {
  await apiFetch('/auth/logout', { method: 'POST' });
  clearAuth();
}
