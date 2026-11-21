import { describe, expect, it } from "vitest";
import { INITIAL_WHEEL, LOCK_MS, clampIndex, swipeIntent, wheelIntent, type WheelInput, type WheelState } from "./input";
import { SLIDES, slideIndexFromHash } from "./slides";

const ev = (o: Partial<WheelInput> = {}): WheelInput => ({ deltaX: 0, deltaY: 100, time: 1000, scrollY: 0, index: 0, count: 4, ...o });

describe("wheelIntent", () => {
  it("moves one slide per deliberate gesture and swallows the page scroll", () => {
    const r = wheelIntent(INITIAL_WHEEL, ev());
    expect(r.action).toBe("next");
    expect(r.prevent).toBe(true);
    expect(wheelIntent(INITIAL_WHEEL, ev({ deltaY: -100, index: 2 })).action).toBe("prev");
  });

  it("cannot skip a slide while the transition lock is active", () => {
    let s: WheelState = wheelIntent(INITIAL_WHEEL, ev({ time: 1000 })).state;
    const during = wheelIntent(s, ev({ time: 1000 + LOCK_MS - 50, index: 1 }));
    expect(during.action).toBe("none");
    expect(during.prevent).toBe(true);
    s = during.state;
    expect(wheelIntent({ ...s, lastTime: -Infinity }, ev({ time: 1000 + LOCK_MS + 1, index: 1 })).action).toBe("next");
  });

  it("ignores the decaying tail of a trackpad gesture but accepts a new, stronger one", () => {
    const first = wheelIntent(INITIAL_WHEEL, ev({ time: 0, deltaY: 120 }));
    // The tail arrives after the lock has expired but still within one gesture and decreasing.
    let s = { ...first.state, lockedUntil: 0, lastTime: 2000, lastAbs: 30 };
    expect(wheelIntent(s, ev({ time: 2050, deltaY: 20, index: 1 })).action).toBe("none");
    s = { ...s, lastTime: 2000, lastAbs: 20 };
    expect(wheelIntent(s, ev({ time: 2600, deltaY: 90, index: 1 })).action).toBe("next");
  });

  it("lets the page scroll once the last slide is showing", () => {
    const r = wheelIntent(INITIAL_WHEEL, ev({ index: 3 }));
    expect(r.action).toBe("none");
    expect(r.prevent).toBe(false);
  });

  it("does nothing going up from the first slide", () => {
    const r = wheelIntent(INITIAL_WHEEL, ev({ deltaY: -100, index: 0 }));
    expect(r).toMatchObject({ action: "none", prevent: false });
  });

  it("does not own the wheel when the page is scrolled down", () => {
    const r = wheelIntent(INITIAL_WHEEL, ev({ scrollY: 600 }));
    expect(r).toMatchObject({ action: "none", prevent: false });
  });

  it("ignores tiny movements and treats a horizontal swipe as direction", () => {
    expect(wheelIntent(INITIAL_WHEEL, ev({ deltaY: 2 })).action).toBe("none");
    expect(wheelIntent(INITIAL_WHEEL, ev({ deltaX: 90, deltaY: 5 })).action).toBe("next");
    expect(wheelIntent(INITIAL_WHEEL, ev({ deltaX: -90, deltaY: 5, index: 1 })).action).toBe("prev");
  });
});

describe("swipeIntent", () => {
  it("changes slide on a clear horizontal swipe only", () => {
    expect(swipeIntent(-80, 5)).toBe("next");
    expect(swipeIntent(80, -5)).toBe("prev");
    expect(swipeIntent(-30, 0)).toBeNull();
    expect(swipeIntent(-80, 90)).toBeNull(); // mostly vertical: the page scrolls
  });
});

describe("slides", () => {
  it("has four slides in a fixed order with unique ids, one per capability", () => {
    expect(SLIDES.map((s) => s.id)).toEqual(["sports", "business", "politics", "finance"]);
    expect(new Set(SLIDES.map((s) => s.background)).size).toBe(4);
    for (const s of SLIDES) expect(s.points.length).toBeGreaterThan(0);
  });
  it("maps URL hashes to slides", () => {
    expect(slideIndexFromHash("#politics")).toBe(2);
    expect(slideIndexFromHash("#pricing")).toBe(-1);
    expect(clampIndex(9, 4)).toBe(3);
    expect(clampIndex(-1, 4)).toBe(0);
  });
});
