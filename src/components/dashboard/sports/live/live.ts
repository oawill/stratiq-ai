// Types and helpers for the Live Predictions dashboard. Everything shown comes from /app-api/football/live; nothing is computed or invented here.

export interface Percent { home: number; draw: number; away: number }
export interface ForecastSummary { version_no: number; official: boolean; generated_at: string; percent: Percent; model: string }
export interface ResultCheck { available: boolean; outcome?: "home" | "draw" | "away"; most_likely?: "home" | "draw" | "away"; most_likely_was_right?: boolean; probability_given_to_outcome?: number; version_no?: number; note: string }
export interface Fixture {
  id: string; competition: string; season: string; matchday: number | null; home_team: string; away_team: string; status: string; venue: string | null;
  kickoff_utc: string | null; date: string; source: string; last_synced_at: string | null; final_score: { home: number; away: number } | null; forecastable: boolean;
  forecast: ForecastSummary | null; result_check: ResultCheck | null;
}
export interface Freshness { last_verified_at: string | null; stale: boolean; provider_failing: boolean; last_error: string | null; message: string | null }
export interface FixtureList { fixtures: Fixture[]; total: number; window: string; time_zone: string; freshness: Freshness; note: string }

export const STATUS_LABEL: Record<string, string> = {
  scheduled: "Scheduled", in_play: "Live", paused: "Half-time", finished: "Full time", awarded: "Awarded", postponed: "Postponed", suspended: "Suspended", cancelled: "Cancelled",
};
export const STATUS_TONE: Record<string, "cyan" | "green" | "violet" | "muted" | "amber"> = {
  scheduled: "muted", in_play: "green", paused: "green", finished: "cyan", awarded: "cyan", postponed: "amber", suspended: "amber", cancelled: "amber",
};
export const MODEL_LABEL: Record<string, string> = { ensemble: "Calibrated ensemble", dixon_coles: "Dixon-Coles" };

export const ZONES = [
  "UTC", "Europe/London", "Europe/Paris", "Europe/Berlin", "Africa/Lagos", "Africa/Johannesburg", "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo",
  "Australia/Sydney", "America/New_York", "America/Chicago", "America/Los_Angeles", "America/Sao_Paulo",
];

export function validZone(z: string | undefined | null): z is string {
  if (!z) return false;
  try { new Intl.DateTimeFormat("en-GB", { timeZone: z }); return true; } catch { return false; }
}

/** "Sat 14 Dec, 15:00 GMT" in the chosen time zone. */
export function kickoff(iso: string | null, tz: string): string {
  if (!iso) return "Kickoff time not confirmed";
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: tz, timeZoneName: "short" }).format(new Date(iso));
}

export function stamp(iso: string | null, tz: string): string {
  if (!iso) return "never";
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: tz, timeZoneName: "short" }).format(new Date(iso));
}

export const pc = (x: number) => `${x.toFixed(1)}%`;
export const num = (x: number | null | undefined, d = 2) => (x === null || x === undefined ? "n/a" : x.toFixed(d));

export const TABS = [
  { id: "today", label: "Today's matches" },
  { id: "upcoming", label: "Upcoming fixtures" },
  { id: "intel", label: "Match intelligence" },
  { id: "history", label: "Prediction history" },
  { id: "completed", label: "Completed matches" },
] as const;
export type TabId = (typeof TABS)[number]["id"] | "performance";
