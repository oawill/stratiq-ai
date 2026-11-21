/**
 * Pure input rules for the carousel, kept apart from the component so they can be unit tested.
 *
 * Wheel: one deliberate gesture moves one slide. While a transition is running, and while the tail of a trackpad's momentum is still
 * arriving, further events are swallowed so they can neither skip a slide nor leak into page scrolling. Once the last slide is
 * showing, a downward wheel is passed through so the rest of the page scrolls normally; the same at the first slide going up.
 */

export const TRANSITION_MS = 750;
/** Wheel events ignored after a slide change. Slightly longer than the transition so momentum does not trigger a second change. */
export const LOCK_MS = 900;
/** Two wheel events closer than this belong to one gesture. */
const SAME_GESTURE_MS = 120;
/** The carousel only owns the wheel while the page is scrolled to (within a few pixels of) the top. */
const ENGAGED_SCROLL_PX = 2;
const MIN_DELTA = 4;

export interface WheelState {
  lockedUntil: number;
  lastTime: number;
  lastAbs: number;
}

export const INITIAL_WHEEL: WheelState = { lockedUntil: 0, lastTime: -Infinity, lastAbs: 0 };

export type WheelAction = "next" | "prev" | "none";

export interface WheelInput {
  deltaX: number;
  deltaY: number;
  time: number;
  scrollY: number;
  index: number;
  count: number;
}

export interface WheelResult {
  action: WheelAction;
  /** True when the browser's default (page scroll) must be cancelled. */
  prevent: boolean;
  state: WheelState;
}

export function wheelIntent(prev: WheelState, e: WheelInput): WheelResult {
  const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
  const abs = Math.abs(d);
  const inStream = e.time - prev.lastTime < SAME_GESTURE_MS;
  // Remember every event (even ones we ignore) so a momentum tail is recognised no matter where it started.
  const seen: WheelState = { ...prev, lastTime: e.time, lastAbs: abs };

  if (e.scrollY > ENGAGED_SCROLL_PX) return { action: "none", prevent: false, state: seen };
  if (abs < MIN_DELTA) return { action: "none", prevent: false, state: seen };

  // A transition is running, or this is the decaying tail of the previous gesture: swallow it.
  if (e.time < prev.lockedUntil || (inStream && abs <= prev.lastAbs * 1.05)) {
    return { action: "none", prevent: true, state: seen };
  }

  const dir = d > 0 ? 1 : -1;
  const target = e.index + dir;
  if (target < 0 || target >= e.count) {
    // Past the end: let the page scroll (down from the last slide). Up from the first slide there is nowhere to go.
    return { action: "none", prevent: false, state: seen };
  }
  return { action: dir > 0 ? "next" : "prev", prevent: true, state: { ...seen, lockedUntil: e.time + LOCK_MS } };
}

/** A horizontal swipe changes slide; a mostly vertical one is left to scroll the page. */
export function swipeIntent(dx: number, dy: number): "next" | "prev" | null {
  if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy) * 1.2) return null;
  return dx < 0 ? "next" : "prev";
}

export function clampIndex(i: number, count: number): number {
  return Math.min(count - 1, Math.max(0, i));
}
