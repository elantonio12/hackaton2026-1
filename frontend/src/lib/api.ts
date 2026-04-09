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

// ---------------------------------------------------------------------------
// Trucks API (recolector views)
// ---------------------------------------------------------------------------

export type TruckStatus = 'idle' | 'en_route' | 'collecting' | 'returning' | 'offline';

export interface TruckOut {
  id: string;
  name: string;
  zone: string;
  capacity_m3: number;
  current_load_m3: number;
  depot_lat: number;
  depot_lon: number;
  current_lat: number;
  current_lon: number;
  status: TruckStatus;
  current_route_id: number | null;
  updated_at: string;
}

export interface TruckRouteStop {
  order: number;
  container_id: string;
  latitude: number;
  longitude: number;
  fill_level: number;
  status: 'pending' | 'collected' | 'skipped';
  distance_along_route_m: number;
}

export interface ActiveRouteOut {
  id: number;
  truck_id: string;
  stops: TruckRouteStop[];
  polyline_geojson: { type: 'LineString'; coordinates: [number, number][] };
  distance_km: number;
  duration_min: number;
  status: string;
  started_at: string;
  completed_at: string | null;
}

/** Fetch the truck assigned to the currently logged-in collector. */
export async function apiGetMyTruck(): Promise<TruckOut> {
  const res = await apiFetch('/trucks/me');
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'No tienes un camion asignado');
  }
  return res.json();
}

/** Fetch the active route for the current collector. Returns null if none. */
export async function apiGetMyRoute(): Promise<ActiveRouteOut | null> {
  const res = await apiFetch('/trucks/me/route');
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Error al obtener la ruta activa');
  return res.json();
}

/** List all trucks (admin RouteList). */
export async function apiListTrucks(): Promise<TruckOut[]> {
  const res = await apiFetch('/trucks/');
  if (!res.ok) throw new Error('Error al listar camiones');
  return res.json();
}

/** Fetch the active route for a specific truck (admin RouteList). */
export async function apiGetTruckRoute(truckId: string): Promise<ActiveRouteOut | null> {
  const res = await apiFetch(`/trucks/${truckId}/route`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Error al obtener la ruta del camion');
  return res.json();
}

/** Trigger /routes/optimize. Admin-only. */
export async function apiOptimizeRoutes(): Promise<{ generated: number; skipped: number; message: string }> {
  const res = await apiFetch('/routes/optimize', { method: 'POST' });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al optimizar rutas');
  return data;
}

// ---------------------------------------------------------------------------
// Trucks CRUD (admin)
// ---------------------------------------------------------------------------

export interface TruckCreatePayload {
  id: string;
  name: string;
  /** Optional — backend derives from depot coordinates if omitted. */
  zone?: string;
  capacity_m3: number;
  depot_lat: number;
  depot_lon: number;
  recolector_email: string;
  recolector_name: string;
}

export interface TruckCreateResponse {
  truck: TruckOut;
  recolector_email: string;
  recolector_temp_password: string;
}

export interface TruckUpdatePayload {
  name?: string;
  zone?: string;
  capacity_m3?: number;
  depot_lat?: number;
  depot_lon?: number;
  status?: string;
}

export async function apiCreateTruck(payload: TruckCreatePayload): Promise<TruckCreateResponse> {
  const res = await apiFetch('/trucks/', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al crear camion');
  return data;
}

export async function apiUpdateTruck(truckId: string, payload: TruckUpdatePayload): Promise<TruckOut> {
  const res = await apiFetch(`/trucks/${truckId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al actualizar camion');
  return data;
}

export async function apiDeleteTruck(truckId: string): Promise<void> {
  const res = await apiFetch(`/trucks/${truckId}`, { method: 'DELETE' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Error al desactivar camion');
  }
}

// ---------------------------------------------------------------------------
// Sensors CRUD (admin)
// ---------------------------------------------------------------------------

export interface SensorInfo {
  sensor_id: string;
  container_id: string;
  latitude: number;
  longitude: number;
  zone: string;
  activo?: boolean;
  status?: string;
}

export interface SensorRegistrationPayload {
  sensor_id: string;
  container_id: string;
  latitude: number;
  longitude: number;
  /** Optional — backend derives from coordinates if omitted. */
  zone?: string;
}

export interface SensorUpdatePayload {
  latitude?: number;
  longitude?: number;
  zone?: string;
  activo?: boolean;
  status?: string;
}

export async function apiListSensors(): Promise<SensorInfo[]> {
  const res = await apiFetch('/sensors/registry');
  if (!res.ok) throw new Error('Error al listar sensores');
  return res.json();
}

export async function apiGetSensor(sensorId: string): Promise<SensorInfo> {
  const res = await apiFetch(`/sensors/registry/${sensorId}`);
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Sensor no encontrado');
  }
  return res.json();
}

export async function apiCreateSensor(payload: SensorRegistrationPayload): Promise<SensorInfo> {
  const res = await apiFetch('/sensors/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al registrar sensor');
  return data;
}

export async function apiUpdateSensor(sensorId: string, payload: SensorUpdatePayload): Promise<SensorInfo> {
  const res = await apiFetch(`/sensors/registry/${sensorId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Error al actualizar sensor');
  return data;
}

export async function apiDeleteSensor(sensorId: string): Promise<void> {
  const res = await apiFetch(`/sensors/registry/${sensorId}`, { method: 'DELETE' });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Error al desactivar sensor');
  }
}

// ---------------------------------------------------------------------------
// CDMX geo helpers (point-in-polygon over the 16 alcaldias)
// ---------------------------------------------------------------------------

/**
 * Resolve the alcaldia containing the given coordinates. Returns null
 * if the point is outside CDMX. Used by the admin sensor/truck CRUD
 * to auto-fill the zone dropdown as soon as the user enters lat/lon.
 */
export async function apiLookupAlcaldia(lat: number, lon: number): Promise<string | null> {
  const res = await apiFetch(`/cdmx/alcaldia?lat=${lat}&lon=${lon}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error('Error al consultar alcaldia');
  const data = await res.json();
  return data.alcaldia ?? null;
}
