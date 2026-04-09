/**
 * Display formatters shared across pages.
 *
 * Keep these tiny and pure — no DOM, no API calls. They're imported
 * by Astro page <script> blocks via the lib alias.
 */

/**
 * Format a number-of-hours duration as a human-readable string.
 *
 *   0.2  → "12 min"
 *   0.5  → "30 min"
 *   1.0  → "1h"
 *   3.42 → "3h 25min"
 *   24.0 → "1d"
 *   50.5 → "2d 3h"
 *   null → "N/D"
 *
 * Use this anywhere the backend returns `estimated_hours_to_full` so
 * we never render values like "0.2h" which are unreadable for ops.
 */
export function formatHoursToFull(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || Number.isNaN(hours)) {
    return 'N/D';
  }
  if (hours < 0) return 'N/D';

  // Sub-hour: minutes only
  if (hours < 1) {
    const minutes = Math.max(1, Math.round(hours * 60));
    return `${minutes} min`;
  }

  // Sub-day: hours [+ minutes]
  if (hours < 24) {
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    if (m === 0) return `${h}h`;
    if (m === 60) return `${h + 1}h`;
    return `${h}h ${m}min`;
  }

  // Multi-day: days [+ hours]
  const days = Math.floor(hours / 24);
  const remH = Math.round(hours - days * 24);
  if (remH === 0) return `${days}d`;
  if (remH === 24) return `${days + 1}d`;
  return `${days}d ${remH}h`;
}
