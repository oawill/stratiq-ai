import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { STATUS_LABEL, STATUS_TONE, kickoff, validZone } from "./live";

// The application currently has one (dark) theme, defined by CSS tokens. These tests keep the live football screens theme-ready: they must use only token
// classes (bg-violet, text-muted, border-line ...) and never hard-coded colours, so a future Light or System theme restyles them without touching them.
const DIR = __dirname;
const FILES = [...readdirSync(DIR).filter((f) => f.endsWith(".tsx")).map((f) => join(DIR, f)), join(DIR, "..", "..", "notifications", "FootballAlerts.tsx")];

describe("live football screens are theme-ready", () => {
  it.each(FILES.map((f) => [f.split(/[\\/]/).pop() as string, f]))("%s uses colour tokens only", (_name, path) => {
    const src = readFileSync(path, "utf8");
    expect(src.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []).toEqual([]);
    expect(src.match(/\b(rgb|rgba|hsl|hsla)\(/g) ?? []).toEqual([]);
    expect(src).not.toMatch(/style=\{\{[^}]*(color|background)\s*:/);              // inline colours would bypass the tokens
  });
});

describe("live helpers", () => {
  it("labels and tones every status the API can return", () => {
    for (const s of ["scheduled", "in_play", "paused", "finished", "awarded", "postponed", "suspended", "cancelled"]) {
      expect(STATUS_LABEL[s]).toBeTruthy();
      expect(STATUS_TONE[s]).toBeTruthy();
    }
  });
  it("shows kickoff in the chosen time zone and rejects unknown zones", () => {
    const iso = "2026-12-14T23:30:00Z";
    expect(kickoff(iso, "UTC")).toContain("23:30");
    expect(kickoff(iso, "Asia/Tokyo")).toContain("08:30");
    expect(kickoff(null, "UTC")).toBe("Kickoff time not confirmed");
    expect(validZone("Europe/London")).toBe(true);
    expect(validZone("Mars/Base")).toBe(false);
    expect(validZone(null)).toBe(false);
  });
});
