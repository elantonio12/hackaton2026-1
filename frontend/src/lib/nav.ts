/**
 * Shared navigation config for authenticated sections.
 */

export const adminNav = [
  { href: '/admin',              label: 'Dashboard' },
  { href: '/admin/sensores',     label: 'Sensores' },
  { href: '/admin/rutas',        label: 'Rutas' },
  { href: '/admin/reportes',     label: 'Reportes' },
  { href: '/admin/metricas',     label: 'Metricas' },
  { href: '/admin/estimaciones', label: 'Estimaciones' },
  { href: '/admin/recolectores', label: 'Invitar usuario' },
];

export const collectorNav = [
  { href: '/recolector/ruta', label: 'Mi ruta' },
  { href: '/recolector/mapa', label: 'Mapa' },
];

export const citizenNav = [
  { href: '/usuario/info',     label: 'Mi zona' },
  { href: '/usuario/reportes', label: 'Reportes' },
];
