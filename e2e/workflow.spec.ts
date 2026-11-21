import { expect, test, type Page } from "@playwright/test";

const stamp = Date.now();
const email = `e2e-${stamp}@stratiq.test`;
// Generated test credential for a throwaway local account; it is deleted by globalTeardown.
const password = `E2e-${stamp}-Pw!x`;

async function signUp(page: Page) {
  await page.goto("/signup");
  await page.getByLabel("Name").fill("E2E Tester");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

// The e2e accounts use the technical test domain @stratiq.test; that address is data, not branding, so it is ignored here.
// Likewise, URLs on the existing hosting hostname (stratiq-ai.vercel.app) are addresses, not branding; they change at domain cutover.
const withoutTestEmails = (t: string) => t.replace(/[\w.+-]+@stratiq\.test/g, "").replace(/https?:\/\/[\w.-]*stratiq[\w.-]*/g, "");

/** Every page a visitor can see must carry the VELQORIN brand (never "VELQORIN.ai" as a name, never the previous name). */
async function expectBranded(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  await expect(page, `${path} title`).toHaveTitle(/VELQORIN/);
  const text = withoutTestEmails(await page.evaluate(() => document.body.innerText));
  expect(text, `${path} shows the previous brand name`).not.toMatch(/stratiq/i);
  // velqorin.ai is the website address, not the brand: it may appear only in lower case (the footer address).
  expect(text, `${path} uses VELQORIN.ai as a brand`).not.toMatch(/VELQORIN\.ai|Velqorin\.ai/);
  const html = await page.content();
  const leftover = withoutTestEmails(html).replace(/(src|href|action|name|id|content)="[^"]*"/g, "").match(/.{0,50}stratiq.{0,50}/gi) ?? [];
  expect(leftover, `${path} markup mentions the previous brand`).toEqual([]);
}

test.describe.configure({ mode: "serial" });

test("public pages, metadata and assets carry the VELQORIN brand", async ({ page, request }) => {
  for (const path of ["/", "/login", "/signup", "/pricing", "/about", "/how-it-works", "/early-access", "/terms", "/privacy", "/no-such-page"]) {
    await expectBranded(page, path);
  }
  const home = await page.goto("/");
  const h = home!.headers();
  expect(h["x-content-type-options"]).toBe("nosniff");
  expect(h["x-frame-options"]).toBe("DENY");
  expect(h["content-security-policy"]).toBe("frame-ancestors 'none'");
  expect(h["referrer-policy"]).toBe("strict-origin-when-cross-origin");
  expect(h["permissions-policy"]).toContain("camera=()");
  await expect(page.getByRole("link", { name: "VELQORIN", exact: true }).first()).toBeVisible();
  await expect(page.getByText("Intelligence Beyond Prediction").first()).toBeVisible();
  await expect(page.getByText("Predict. Simulate. Strategize.").first()).toBeVisible();
  await expect(page.locator('meta[property="og:site_name"]')).toHaveAttribute("content", "VELQORIN");
  await expect(page).toHaveTitle("VELQORIN | AI Prediction & Strategic Intelligence");
  await expect(page.locator('meta[name="description"]')).toHaveAttribute("content", "Explore AI-powered sports predictions, business game theory, political scenarios, and financial intelligence with VELQORIN.");
  await expect(page.locator('meta[property="og:image"]')).toHaveCount(1);
  const ld = JSON.parse((await page.locator('script[type="application/ld+json"]').first().textContent()) ?? "{}");
  expect(ld.name).toBe("VELQORIN");
  expect(ld.slogan).toBe("Intelligence Beyond Prediction");
  const manifest = await (await request.get("/manifest.webmanifest")).json();
  expect(manifest.name).toBe("VELQORIN");
  expect(manifest.short_name).toBe("VELQORIN");
  for (const asset of ["/icon.svg", "/favicon.ico", "/apple-icon.png", "/opengraph-image.png", "/icons/icon-192.png", "/icons/icon-512.png"]) {
    const res = await request.get(asset);
    expect(res.status(), asset).toBe(200);
  }
  // The product names appear in the marketing navigation (the home page has its own anchor navigation, so check an inner page).
  await page.goto("/pricing");
  await page.getByRole("button", { name: /Intelligence/ }).click();
  for (const n of ["VELQORIN Sports", "VELQORIN Strategy", "VELQORIN Politics", "VELQORIN Markets"]) await expect(page.getByRole("link", { name: new RegExp(n) }).first()).toBeVisible();
});


test("anonymous visitors cannot reach the application or its API", async ({ page, request }) => {
  await page.goto("/dashboard/business");
  await expect(page).toHaveURL(/\/login/);
  expect((await request.get("/app-api/overview")).status()).toBe(401);
  expect((await request.get("/app-api/library/export")).status()).toBe(401);
  const post = await request.post("/app-api/business/solve", { data: {}, headers: { origin: "https://evil.example" } });
  expect([401, 403]).toContain(post.status());
  // Billing endpoints: anonymous checkout is refused, and the webhook never accepts unsigned requests.
  expect((await request.post("/api/billing/checkout", { data: { plan: "strategy_pro", interval: "month" } })).status()).toBe(401);
  expect((await request.post("/api/billing/portal", { data: {} })).status()).toBe(401);
  expect((await request.post("/api/team/invites", { data: { email: "x@example.com", role: "member" } })).status()).toBe(401);
  expect([400, 503]).toContain((await request.post("/api/stripe/webhook", { data: "{}" })).status());
});

test("unified landing page: one carousel of four capabilities, one header, interactive demonstrations and conversion sections", async ({ page, browser }) => {
  test.setTimeout(240_000);
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Primary" });

  const slide = () => page.locator('[role="group"][aria-roledescription="slide"]:not([aria-hidden="true"])');
  const dot = (n: number) => page.getByRole("button", { name: new RegExp(`^Go to slide ${n}:`) });

  await test.step("one header: Platform, Solutions, How It Works, Pricing, Get Started, with no second menu", async () => {
    await expect(page.getByRole("banner").getByRole("navigation")).toHaveCount(1);
    for (const label of ["Platform", "How It Works", "Pricing"]) await expect(nav.getByRole("link", { name: label, exact: true })).toBeVisible();
    await expect(nav.getByRole("button", { name: "Solutions" })).toBeVisible();
    await expect(page.getByRole("banner").getByRole("link", { name: "Get Started" })).toHaveAttribute("href", "/signup");
  });

  await test.step("the carousel starts on Sports and its slides respond to buttons, dots and arrow keys", async () => {
    await expect(page.getByRole("heading", { level: 1 })).toContainText("VELQORIN");
    await expect(slide()).toHaveCount(1);
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Predict the Game");
    await expect(page.getByRole("progressbar", { name: "Slide progress" })).toHaveAttribute("aria-valuenow", "1");
    await expect(page.getByRole("button", { name: "Previous slide" })).toBeDisabled();
    await page.getByRole("button", { name: "Next slide" }).click();
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Outthink the Competition");
    await expect(page).toHaveURL(/#business$/);
    await expect(dot(2)).toHaveAttribute("aria-current", "true");
    await page.keyboard.press("ArrowRight");
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Understand Political Possibilities");
    await page.keyboard.press("ArrowLeft");
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Outthink the Competition");
    await dot(4).click();
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Navigate Markets");
    await expect(page.getByRole("button", { name: "Next slide" })).toBeDisabled();
    await expect(page.getByRole("progressbar", { name: "Slide progress" })).toHaveAttribute("aria-valuenow", "4");
  });

  await test.step("the mouse wheel moves one slide per gesture, then hands the page back its scrolling", async () => {
    await page.goto("/");
    await page.mouse.move(600, 400);
    for (let i = 0; i < 6; i++) { await page.mouse.wheel(0, 100); await page.waitForTimeout(60); }
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Outthink the Competition"); // six quick notches = one slide
    expect(await page.evaluate(() => scrollY)).toBe(0);
    await page.waitForTimeout(1100);
    await page.mouse.wheel(0, 100);
    await page.waitForTimeout(1100);
    await page.mouse.wheel(0, 100);
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Navigate Markets");
    await page.waitForTimeout(1100);
    await page.mouse.wheel(0, 400); // last slide: the page itself scrolls
    await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(100);
    await page.mouse.wheel(0, -2000);
    await expect.poll(() => page.evaluate(() => scrollY)).toBe(0);
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Navigate Markets");
  });

  await test.step("Solutions menu and hash links move to a slide without reloading the page", async () => {
    await page.goto("/");
    await page.evaluate(() => { (window as unknown as { __kept: boolean }).__kept = true; });
    await nav.getByRole("button", { name: "Solutions" }).click();
    await page.getByRole("link", { name: "Political Intelligence", exact: true }).click();
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Understand Political Possibilities");
    await expect(page).toHaveURL(/#politics$/);
    expect(await page.evaluate(() => (window as unknown as { __kept?: boolean }).__kept)).toBe(true); // same document: no reload
    await page.goto("/#finance");
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Navigate Markets");
    await nav.getByRole("link", { name: "Pricing", exact: true }).click();
    await expect(page.locator("#pricing")).toBeInViewport();
    await expect(nav.getByRole("link", { name: "Pricing", exact: true })).toHaveAttribute("aria-current", "location");
  });

  await test.step("each slide's call to action opens its interactive demonstration on the same page", async () => {
    await page.goto("/#politics");
    await slide().getByRole("link", { name: "Try the election demo" }).click();
    await expect(page).toHaveURL(/#politics-demo$/);
    await expect(page.getByRole("heading", { level: 2, name: /Understand the Political Landscape/ })).toBeInViewport();
    await page.goto("/");
  });

  await test.step("the old per-domain pages now redirect into the carousel, and footer links choose slides", async () => {
    for (const [path, heading] of [["/sports", "Predict the Game"], ["/business", "Outthink the Competition"], ["/politics", "Understand Political Possibilities"], ["/finance", "Navigate Markets"]]) {
      await page.goto(path);
      await expect(page).toHaveURL(new RegExp(`/#${path.slice(1)}$`));
      await expect(slide().getByRole("heading", { level: 2 })).toContainText(heading);
    }
    await page.goto("/");
    await page.getByRole("contentinfo").getByRole("link", { name: /Politic/ }).click();
    await expect(slide().getByRole("heading", { level: 2 })).toContainText("Understand Political Possibilities");
    await page.goto("/");
  });

  await test.step("sports: probabilities sum to one and respond to the scenario", async () => {
    const sports = page.locator("#sports-demo");
    await sports.scrollIntoViewIfNeeded();
    await expect(sports.getByText("Fictional teams · simulated demonstration data · not a real prediction")).toBeVisible();
    await expect(sports.getByText("Demonstration fixtures")).toBeVisible();
    const probs = () => sports.evaluate((el) => [...el.querySelectorAll('[role="img"][aria-label$=" percent"]')].map((e) => parseFloat(e.getAttribute("aria-label")!.match(/([\d.]+) percent$/)![1])));
    const before = await probs();
    expect(before).toHaveLength(3);
    expect(before.reduce((a, b) => a + b, 0)).toBeCloseTo(100, 0);
    await sports.getByLabel("Home key attacker unavailable").check();
    await expect.poll(async () => (await probs())[0]).toBeLessThan(before[0]);
    expect((await probs()).reduce((a, b) => a + b, 0)).toBeCloseTo(100, 0);
    await sports.getByRole("button", { name: "Harbour City v Ironvale Athletic" }).click();
    await expect(sports.getByRole("combobox", { name: "Home team" })).toHaveValue("harbour");
    await expect(sports.getByText("Illustrative zones generated from the demonstration attack rating. Not player-tracking data.")).toBeVisible();
    await expect(page.getByRole("link", { name: "Try Sports Intelligence" })).toHaveAttribute("href", "/dashboard/sports");
  });

  await test.step("strategy: the scenario changes the matrix and the equilibrium analysis", async () => {
    const strategy = page.locator("#strategy-demo");
    await strategy.scrollIntoViewIfNeeded();
    await expect(strategy.getByRole("status")).toContainText("our best reply is");
    await expect(strategy.getByText("NE", { exact: true }).first()).toBeVisible();
    await strategy.getByLabel("Company expands market share").check();
    await expect(strategy.getByRole("status")).toContainText(/Nash equilibrium|no pure-strategy/);
    await expect(strategy.getByText(/Both firms choose prices simultaneously/)).toBeVisible();
    await expect(strategy.getByRole("table").first().locator("tbody td")).toHaveCount(9);
    await expect(page.getByRole("link", { name: "Explore Strategy Simulator" })).toHaveAttribute("href", "/dashboard/business");
  });

  await test.step("politics: hypothetical scenarios are labelled and kept apart from the forecast", async () => {
    const politics = page.locator("#politics-demo");
    await politics.scrollIntoViewIfNeeded();
    await expect(politics.getByText("Fictional country · simulated data · nonpartisan illustration")).toBeVisible();
    await expect(politics.getByText("Fictional previous election").first()).toBeVisible();
    await expect(politics.getByText("Your hypothetical scenario")).toHaveCount(0);
    const region = politics.getByRole("button", { name: /^Central Plains/ });
    await region.focus();
    await region.press("Enter");                      // the map is operable from the keyboard
    await expect(politics.getByLabel("Regional swing in")).toHaveValue("central");
    await politics.getByLabel(/Vote moving between Party A and Party B/).fill("6");
    await expect(politics.getByText("Your hypothetical scenario")).toBeVisible();
    await expect(politics.getByText("Hypothetical scenario").first()).toBeVisible();
    await politics.getByLabel("Party B", { exact: true }).check();
    await expect(politics.getByText(/Party A \+ Party C \+ Party B would hold/)).toBeVisible();
    await expect(politics.getByText(/Nothing here predicts or favours any real party or election/)).toBeVisible();
  });

  await test.step("markets: the scenario drives the risk analysis and nothing is promised", async () => {
    const markets = page.locator("#markets-demo");
    await markets.scrollIntoViewIfNeeded();
    await expect(markets.getByText("Simulated prices and assumptions · not market data · not investment advice")).toBeVisible();
    const loss = async () => parseInt(((await markets.locator("dt", { hasText: "Chance of loss" }).locator("xpath=following-sibling::dd").textContent()) ?? "0").replace("%", ""));
    await markets.getByLabel("Market scenario").selectOption("bull");
    const bull = await loss();
    await markets.getByLabel("Market scenario").selectOption("bear");
    await expect.poll(loss).toBeGreaterThan(bull);
    expect(await loss()).toBeGreaterThan(50);
    await markets.getByLabel("Risk tolerance").selectOption("aggressive");
    await markets.getByText("12 months").click();
    await expect(markets.getByRole("status")).toContainText("These are scenarios, not predictions or guaranteed returns.");
    await expect(markets.getByRole("row", { name: /Equities fall 20%/ })).toContainText("−18.0%");
    await expect(markets.getByText(/not market data and not a historical record/)).toBeVisible();
  });

  await test.step("trust, pricing and early-access sections are intact", async () => {
    await expect(page.getByRole("heading", { name: /Data → Analysis → Simulation → Decision intelligence/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: "How VELQORIN Works" })).toBeVisible();
    await expect(page.locator("#performance")).toBeVisible();
    await expect(page.locator("#pricing").getByRole("link", { name: "Join early access" }).first()).toHaveAttribute("href", /early-access/);
    await expect(page.locator("#early-access")).toBeVisible();
    await expect(page.getByRole("contentinfo")).toContainText("not financial, legal, or betting");
  });

  await test.step("phones get a swipeable carousel with readable text, a menu and no sideways scrolling", async () => {
    const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
    const m = await ctx.newPage();
    await m.goto("/");
    const heading = m.locator('[role="group"][aria-roledescription="slide"]:not([aria-hidden="true"]) h2');
    await expect(heading).toContainText("Predict the Game");
    await expect(m.getByRole("link", { name: "Try the match demo" })).toBeInViewport();
    await expect(m.getByRole("link", { name: "Get Started" }).last()).toBeInViewport();
    expect(await m.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    // A horizontal swipe changes the slide; touch events are dispatched on the carousel itself.
    const swipe = (dx: number) => m.locator("#solutions").evaluate((el, d) => {
      const touch = (x: number) => new Touch({ identifier: 1, target: el, clientX: x, clientY: 300 });
      el.dispatchEvent(new TouchEvent("touchstart", { bubbles: true, cancelable: true, touches: [touch(200)], changedTouches: [touch(200)] }));
      el.dispatchEvent(new TouchEvent("touchend", { bubbles: true, cancelable: true, touches: [], changedTouches: [touch(200 + d)] }));
    }, dx);
    await swipe(-120);
    await expect(heading).toContainText("Outthink the Competition");
    await swipe(120);
    await expect(heading).toContainText("Predict the Game");
    await m.getByRole("button", { name: "Open menu" }).click();
    await m.getByRole("navigation", { name: "Mobile" }).getByRole("link", { name: "Financial Intelligence" }).click();
    await expect(m).toHaveURL(/#finance$/);
    await expect(heading).toContainText("Navigate Markets");
    await expect(m.locator("#landing-menu")).toHaveCount(0);
    await ctx.close();
  });

  await test.step("reduced motion: the carousel still works and the transition bands are shown still", async () => {
    const ctx = await browser.newContext({ reducedMotion: "reduce" });
    const r = await ctx.newPage();
    await r.goto("/");
    await r.getByRole("button", { name: "Next slide" }).click();
    await expect(r.locator('[role="group"][aria-roledescription="slide"]:not([aria-hidden="true"]) h2')).toContainText("Outthink the Competition"); // still navigable, just not animated
    await expect(r.locator("[data-transition]").first()).toBeAttached();
    await expect.poll(() => r.locator("[data-transition]").first().locator("svg").evaluateAll((els) => els.map((e) => (e as SVGElement).style.opacity))).toEqual(["0.5", "0.5"]);
    await ctx.close();
  });
});

test("landing page leads to a working account and every module", async ({ page }) => {
  await test.step("landing page", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("VELQORIN");
    await page.goto("/login");
    await expect(page).toHaveURL(/\/login/);
    await page.getByRole("link", { name: "Create one" }).click();
  });

  await test.step("sign up and reach the dashboard", async () => {
    await signUp(page);
    await expect(page.getByRole("heading", { name: /Welcome, E2E/ })).toBeVisible();
    await expect(page.getByText("Models registered", { exact: true })).toBeVisible();
  });

  await test.step("dashboard shows the VELQORIN product names and no previous brand", async () => {
    for (const n of ["VELQORIN Sports", "VELQORIN Strategy", "VELQORIN Politics", "VELQORIN Markets", "VELQORIN SimLab"]) {
      await expect(page.getByRole("navigation", { name: "Dashboard" }).getByRole("link", { name: n })).toBeVisible();
    }
    for (const path of ["/dashboard", "/dashboard/sports", "/dashboard/business", "/dashboard/politics", "/dashboard/finance", "/dashboard/simulations", "/dashboard/history", "/dashboard/workspace", "/dashboard/team", "/dashboard/data", "/dashboard/billing", "/dashboard/settings"]) {
      await expectBranded(page, path);
    }
    await page.goto("/dashboard");
  });

  await test.step("sports: forecast, save, find it in history", async () => {
    await page.goto("/dashboard/sports");
    await page.locator("ul button[aria-pressed]").first().click();
    await expect(page.getByText("Model projection · not saved")).toBeVisible();
    await page.getByRole("button", { name: "Save forecast" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved at" })).toBeVisible();
    await page.goto("/dashboard/history");
    await expect(page.locator("summary").first()).toContainText(" vs ");
  });

  await test.step("business: solve and save a game", async () => {
    await page.goto("/dashboard/business");
    await expect(page.getByText(/only pure Nash equilibrium/)).toBeVisible();
    await page.locator("#sc-title").fill("E2E price war");
    await page.getByRole("button", { name: "Save scenario" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Saved." })).toBeVisible();
  });

  await test.step("simulation lab: run, finish, explain", async () => {
    await page.goto("/dashboard/simulations");
    await page.locator("#sim-iter").selectOption("1000");
    await page.locator("#sim-seed").fill("42");
    await expect(page.getByText(/Model is valid/)).toBeVisible();
    await page.getByRole("button", { name: "Run simulation" }).click();
    await expect(page.getByRole("link", { name: "CSV" })).toBeVisible({ timeout: 90_000 }); // only shown once the run has completed
    await expect(page.getByText(/Across 1,000 runs/)).toBeVisible();
    await page.getByRole("button", { name: "Explain", exact: true }).first().click();
    await page.getByRole("button", { name: "Explain everything" }).click();
    await expect(page.getByText(/^Computed explanation ·/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Limitations" })).toBeVisible();
  });

  await test.step("politics and finance modules respond", async () => {
    await page.goto("/dashboard/politics");
    await expect(page.getByText("Seats needed", { exact: true })).toBeVisible();
    await expect(page.getByText("Voting power (Shapley–Shubik)")).toBeVisible();
    await page.goto("/dashboard/finance");
    await expect(page.getByText("Diversification ratio", { exact: true })).toBeVisible();
    await expect(page.getByText("Educational · not investment advice")).toBeVisible();
  });

  await test.step("library lists the work, filters it, explains it and exports it", async () => {
    await page.goto("/dashboard/workspace");
    await expect(page.getByText("E2E price war").first()).toBeVisible();
    await page.getByLabel("Search the library").fill("price war");
    await expect(page.getByText("E2E price war").first()).toBeVisible();
    await expect(page.getByText("Revenue").or(page.getByText("Product launch profit"))).toHaveCount(0);
    await page.getByLabel("Search the library").fill("");
    const res = await page.request.get("/app-api/library/export");
    expect(res.status()).toBe(200);
    const bundle = await res.json();
    expect(bundle.format).toBe("stratiq-workspace-export");
    expect(bundle.counts.predictions).toBe(1);
    expect(bundle.counts.scenarios).toBe(1);
    expect(bundle.counts.simulation_runs).toBe(1);
  });

  await test.step("plan and billing page shows the plan and its limits", async () => {
    await page.goto("/dashboard/billing");
    await expect(page.getByRole("heading", { name: "Plan & Billing" })).toBeVisible();
    await expect(page.getByText("Current plan", { exact: true })).toBeVisible();
    await expect(page.getByText("Saved scenarios", { exact: true })).toBeVisible();
    await expect(page.getByText("Payments are handled by Stripe")).toBeVisible();
  });

  await test.step("a second workspace is isolated, and switching back restores the first", async () => {
    await page.goto("/dashboard/workspace");
    await page.getByLabel("Create a new workspace").fill("E2E second");
    await page.getByRole("button", { name: "Create" }).click();
    await expect(page.getByText("Nothing saved yet")).toBeVisible();
    const empty = await (await page.request.get("/app-api/library/export")).json();
    expect(empty.counts).toEqual({ predictions: 0, scenarios: 0, simulation_runs: 0 });
    await page.getByRole("button", { name: "Switch to this" }).first().click();
    await expect(page.getByText("E2E price war").first()).toBeVisible();
  });

  await test.step("sign out ends the session", async () => {
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login/);
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
    expect((await page.request.get("/app-api/overview")).status()).toBe(401);
  });

  await test.step("the account can sign back in", async () => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
    await page.getByRole("button", { name: "Account menu" }).click();
    await page.getByRole("button", { name: "Sign out" }).click();
  });

  await test.step("a wrong password is refused without revealing which part was wrong", async () => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("definitely-wrong-password");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page.getByText("Incorrect email or password.")).toBeVisible();
  });
});

test("teammates: invite, accept, share work, comment, change role, remove", async ({ browser }) => {
  const email2 = `e2e-${stamp}-b@stratiq.test`;
  const owner = await (await browser.newContext()).newPage();
  const mate = await (await browser.newContext()).newPage();
  owner.on("dialog", (d) => d.accept());

  await test.step("the owner creates an invitation and gets a one-time link", async () => {
    await owner.goto("/login");
    await owner.getByLabel("Email").fill(email);
    await owner.getByLabel("Password").fill(password);
    await owner.getByRole("button", { name: "Log in" }).click();
    await expect(owner).toHaveURL(/\/dashboard$/);
    await owner.goto("/dashboard/team");
    await expect(owner.getByRole("heading", { name: "Team" })).toBeVisible();
    await owner.getByLabel("Email address").fill(email2);
    await owner.getByRole("button", { name: "Create invitation" }).click();
    await expect(owner.getByRole("status").filter({ hasText: "Invitation created" })).toBeVisible();
  });
  const link = await owner.getByLabel("Invitation link").inputValue();
  expect(link).toMatch(/\/invite\/[A-Za-z0-9_-]{40,}$/);
  const path = new URL(link).pathname;

  await test.step("the invitee signs up from the link and accepts", async () => {
    await mate.goto(path);
    await expect(mate.getByRole("heading", { name: "You're invited" })).toBeVisible();
    await mate.getByRole("link", { name: "Create account" }).click();
    await mate.getByLabel("Name").fill("E2E Teammate");
    await mate.getByLabel("Email").fill(email2);
    await mate.getByLabel("Password").fill(password);
    await mate.getByRole("button", { name: "Create account" }).click();
    await expect(mate).toHaveURL(/\/invite\//); // sign-up returns to the invitation
    await mate.getByRole("button", { name: "Accept invitation" }).click();
    await expect(mate).toHaveURL(/\/dashboard$/);
  });

  await test.step("a used link stops working", async () => {
    const anon = await (await browser.newContext()).newPage();
    await anon.goto(path);
    await expect(anon.getByRole("heading", { name: "Invitation not available" })).toBeVisible();
    await anon.close();
  });

  await test.step("the teammate sees the owner's saved work and comments on it", async () => {
    await mate.goto("/dashboard/workspace");
    const row = mate.locator("li", { hasText: "E2E price war" }).first();
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: "Comments" }).click();
    await row.getByLabel("Add a comment").fill("Looks right to me");
    await row.getByRole("button", { name: "Comment", exact: true }).click();
    await expect(row.getByText("Looks right to me")).toBeVisible();
  });

  await test.step("the owner sees the comment and the join in the activity feed", async () => {
    await owner.goto("/dashboard/workspace");
    const row = owner.locator("li", { hasText: "E2E price war" }).first();
    await row.getByRole("button", { name: "Comments" }).click();
    await expect(row.getByText("Looks right to me")).toBeVisible();
    await expect(row.getByText("E2E Teammate").first()).toBeVisible();
    await owner.goto("/dashboard/team");
    await expect(owner.getByLabel("Workspace activity").getByText(/E2E Teammate joined as member/)).toBeVisible();
    await expect(owner.getByLabel("Workspace activity").getByText("Commented on a scenario")).toBeVisible();
  });

  await test.step("downgrading the teammate to viewer makes the workspace read-only for them", async () => {
    await owner.getByLabel("Role for E2E Teammate").selectOption("viewer");
    await expect(owner.getByLabel("Role for E2E Teammate")).toHaveValue("viewer");
    await mate.goto("/dashboard/workspace");
    const row = mate.locator("li", { hasText: "E2E price war" }).first();
    await row.getByRole("button", { name: "Comments" }).click();
    await expect(row.getByText("Viewers can read comments but not post.")).toBeVisible();
  });

  await test.step("removing the teammate ends their access to the workspace", async () => {
    await owner.getByRole("button", { name: "Remove" }).click();
    await expect(owner.getByLabel("Workspace members").getByText("E2E Teammate")).toHaveCount(0);
    await mate.goto("/dashboard/workspace");
    await expect(mate.getByText("E2E price war")).toHaveCount(0);
  });

  await owner.context().close();
  await mate.context().close();
});

test("bring your own data: upload, validate, and use it in Sports, SimLab, Markets and Politics", async ({ page }) => {
  // Small, clearly synthetic files generated here; no real data is involved.
  const teams = ["Ash", "Birch", "Cedar", "Dune", "Elm", "Fir"];
  const matches = ["date,home_team,away_team,home_goals,away_goals"];
  for (let round = 0; round < 24; round++) {   // enough matches (about 120) for the backtest, which needs more than 100
    teams.forEach((h, i) => {
      const a = teams[(i + 1 + round) % teams.length];
      if (a !== h) matches.push(`2024-01-${String(round + 1).padStart(2, "0")},${h},${a},${(i + round) % 4},${(i * 2 + round) % 3}`);
    });
  }
  const sports = matches.join("\n");
  const series = "month,demand\n" + Array.from({ length: 30 }, (_, i) => `${i + 1},${100 + (i % 7) * 3 + Math.sin(i) * 5}`).join("\n");
  const returns = "date,Alpha Fund,Beta Fund\n" + Array.from({ length: 30 }, (_, i) => `${new Date(Date.UTC(2023, i, 28)).toISOString().slice(0, 10)},${(Math.sin(i) * 3 + 0.5).toFixed(2)},${(Math.cos(i * 1.3) * 2 + 0.3).toFixed(2)}`).join("\n");
  const seats = "party,seats\nAlpha,40\nBeta,35\nGamma,15\nDelta,10\n";
  const file = (name: string, text: string) => ({ name, mimeType: "text/csv", buffer: Buffer.from(text) });

  async function upload(kind: string, name: string, csv: string, extra?: () => Promise<void>) {
    await page.goto("/dashboard/data");
    await page.getByLabel("What is it?").selectOption({ label: kind });
    await page.getByLabel("Name", { exact: true }).fill(name);
    if (extra) await extra();
    await page.getByLabel(/CSV file/).setInputFiles(file(`${name}.csv`, csv));
    await page.getByRole("button", { name: "Check the file" }).click();
    await expect(page.getByText("The file is valid.")).toBeVisible();
    await page.getByRole("button", { name: "Save dataset" }).click();
    await expect(page.getByRole("status").filter({ hasText: `Saved “${name}”` })).toBeVisible();
  }

  await test.step("sign in", async () => {
    await page.goto("/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  await test.step("a bad file is explained line by line and cannot be saved", async () => {
    await page.goto("/dashboard/data");
    await page.getByLabel("Name", { exact: true }).fill("Broken");
    await page.getByLabel(/CSV file/).setInputFiles(file("broken.csv", "date,home_team,away_team,home_goals,away_goals\nnot-a-date,A,B,1,1\n2024-01-02,A,A,1,1"));
    await page.getByRole("button", { name: "Check the file" }).click();
    await expect(page.getByText("Fix these problems and check again:")).toBeVisible();
    await expect(page.getByText(/Line 2: date 'not-a-date'/)).toBeVisible();
    await expect(page.getByText(/Line 3: home and away are both 'A'/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Save dataset" })).toBeDisabled();
  });

  await test.step("sports results become a forecast on the user's own data", async () => {
    await upload("Football match results", "E2E league", sports);
    await expect(page.getByLabel("Datasets").getByText("E2E league")).toBeVisible();
    await page.goto("/dashboard/sports");
    await page.getByRole("tab", { name: "Your data" }).click();
    await page.getByLabel("Dataset", { exact: true }).selectOption({ label: "E2E league" });
    await page.getByLabel("Home team").selectOption("Ash");
    await page.getByLabel("Away team").selectOption("Birch");
    await page.getByRole("button", { name: "Forecast" }).click();
    await expect(page.getByText("Model projection · not saved")).toBeVisible();
    await expect(page.getByText(/Ratings fitted on \d+ matches from “E2E league”/)).toBeVisible();
    await page.getByRole("button", { name: "Save forecast" }).click();
    await expect(page.getByText(/^Saved at/)).toBeVisible();
    // The model is replayed over past matches and scored against a baseline, with the caveats shown.
    await page.getByRole("button", { name: "Test on my data" }).click();
    await expect(page.getByRole("rowheader", { name: "Log loss" })).toBeVisible();
    await expect(page.getByRole("rowheader", { name: "Brier score" })).toBeVisible();
    await expect(page.getByText(/Scored \d+ matches from/)).toBeVisible();
    await expect(page.getByText(/not a promise about any league/)).toBeVisible();
    await page.goto("/dashboard/history");
    await expect(page.getByText("Ash vs Birch").first()).toBeVisible();
  });

  await test.step("a series fits a distribution for a SimLab variable", async () => {
    await upload("Numeric series", "E2E demand", series);
    await page.goto("/dashboard/simulations");
    await page.getByRole("button", { name: "Fit to my data" }).first().click();
    await page.getByLabel("Dataset", { exact: true }).selectOption({ label: "E2E demand" });
    await page.getByLabel("Column").selectOption("demand");
    await page.getByRole("button", { name: "Fit", exact: true }).click();
    await expect(page.getByText(/Fitted (normal|lognormal) to 30 observations of “demand”/)).toBeVisible();
  });

  await test.step("a returns file feeds the historical risk tool", async () => {
    await upload("Market prices / returns", "E2E funds", returns);
    await page.goto("/dashboard/finance");
    await page.getByRole("tab", { name: "Historical returns" }).click();
    await page.getByLabel("Or use a dataset you uploaded").selectOption({ label: "E2E funds · 30 rows" });
    await page.getByRole("button", { name: "Use this data" }).click();
    await expect(page.getByLabel(/^Returns \(CSV/)).toHaveValue(/^Alpha Fund,Beta Fund\n/);
    await expect(page.getByText("Value at Risk and Expected Shortfall")).toBeVisible();
  });

  await test.step("party seats fill the coalition tool", async () => {
    await upload("Party seats", "E2E parliament", seats);
    await page.goto("/dashboard/politics");
    await page.getByLabel("Or use a dataset you uploaded").selectOption({ label: "E2E parliament · 4 rows" });
    await page.getByRole("button", { name: "Use this data" }).click();
    await expect(page.getByLabel("Party 1 name")).toHaveValue("Alpha");
    await expect(page.getByLabel("Gamma seats")).toHaveValue("15");
  });

  await test.step("a dataset can be deleted", async () => {
    page.on("dialog", (d) => d.accept());
    await page.goto("/dashboard/data");
    await page.getByRole("button", { name: "Delete E2E parliament" }).click();
    await expect(page.getByLabel("Datasets").getByText("E2E parliament")).toHaveCount(0);
  });
});

test("historical football data: import season files, see them checked, browse, export, and use them for forecasts", async ({ page }) => {
  // Two SYNTHETIC seasons (real club names, invented scores) generated here; no provider data is involved.
  const clubs = ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Burnley", "Chelsea", "Crystal Palace", "Everton", "Fulham",
    "Leeds", "Leicester", "Liverpool", "Man City", "Man United", "Newcastle", "Southampton", "Tottenham", "West Ham", "Wolves"];
  const season = (year: number, dropLast = 0) => {
    const rows = ["Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR"];
    let i = 0;
    for (const h of clubs) for (const a of clubs) {
      if (h === a) continue;
      const d = new Date(Date.UTC(year, 7, 12) + 86_400_000 * 7 * Math.floor(i / 10));
      const dd = `${String(d.getUTCDate()).padStart(2, "0")}/${String(d.getUTCMonth() + 1).padStart(2, "0")}/${d.getUTCFullYear()}`;
      rows.push(`E0,${dd},15:00,${h},${a},${(i * 7 + year) % 4},${(i * 5 + year) % 3},H`);
      i++;
    }
    return rows.slice(0, rows.length - dropLast).join("\n") + "\n";
  };
  const file = (name: string, text: string) => ({ name, mimeType: "text/csv", buffer: Buffer.from(text) });

  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.goto("/dashboard/data");
  const section = page.getByRole("region", { name: "Historical Football Data" });
  await expect(section.getByText("Nothing imported")).toBeVisible();

  await test.step("a complete season and a season missing one match are both imported, and only one is called complete", async () => {
    await page.getByLabel(/Season files/).setInputFiles([file("E0_2022.csv", season(2022)), file("E0_2023.csv", season(2023, 1))]);
    await page.getByRole("button", { name: "Import Historical Data" }).click();
    await expect(section.getByText(/380 accepted/)).toBeVisible();
    await expect(section.getByText(/379 accepted/)).toBeVisible();
    await expect(section.getByText("2022/23 Complete")).toBeVisible();
    await expect(section.getByText("2023/24 Incomplete")).toBeVisible();
    await expect(section.getByText("Data quality: Needs review")).toBeVisible();
    await expect(section.getByText("759", { exact: true })).toBeVisible();
  });

  await test.step("repeating an import adds nothing", async () => {
    await page.getByLabel(/Season files/).setInputFiles(file("E0_2022_again.csv", season(2022)));
    await page.getByRole("button", { name: "Import Historical Data" }).click();
    await expect(section.getByText(/0 new, 380 already stored/)).toBeVisible();
    await expect(section.getByText("759", { exact: true })).toBeVisible();
  });

  await test.step("the validation report names what is missing", async () => {
    await page.getByRole("button", { name: "Data Validation Report" }).click();
    await expect(section.getByText(/Missing \(1\)/)).toBeVisible();
    await expect(section.getByText("Failed:").first()).toBeAttached();
  });

  await test.step("matches can be browsed and filtered by club", async () => {
    await page.getByRole("button", { name: "View Matches" }).click();
    await section.getByLabel("Club").selectOption("Arsenal");
    await expect(section.getByText("All seasons · 76 matches")).toBeVisible();
    await section.getByLabel("Season", { exact: true }).selectOption("2022/23");
    await expect(section.getByText("2022/23 · 38 matches")).toBeVisible();
  });

  await test.step("the export is the exact five-column CSV", async () => {
    await section.getByLabel("Season", { exact: true }).selectOption("all");
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
    expect(download.suggestedFilename()).toBe("velqorin_epl_all-seasons.csv");
    const chunks: Buffer[] = [];
    for await (const c of (await download.createReadStream())!) chunks.push(c as Buffer);
    const lines = Buffer.concat(chunks).toString().trim().split("\n");
    expect(lines[0]).toBe("date,home_team,away_team,home_goals,away_goals");
    expect(lines).toHaveLength(760);
    expect(lines.every((l) => l.split(",").length === 5)).toBe(true);
    expect(lines.some((l) => l.includes("Man United") || l.includes("Man City"))).toBe(false);          // club names are standardised
    expect(lines.some((l) => l.includes("Manchester United"))).toBe(true);
  });

  await test.step("the history becomes a dataset and shows what the model sees before a fixture", async () => {
    await page.getByRole("button", { name: "Use in forecasts" }).click();
    await section.getByLabel("Dataset name for forecasts").fill("E2E Premier League");
    await section.getByRole("button", { name: "Create dataset" }).click();
    await expect(section.getByRole("status").filter({ hasText: "Saved “E2E Premier League” (759 matches)" })).toBeVisible();
    await section.getByLabel("Home club").selectOption("Arsenal");
    await section.getByLabel("Away club").selectOption("Chelsea");
    await section.getByRole("button", { name: "Show", exact: true }).click();
    await expect(section.getByText(/Elo-style rating/).first()).toBeVisible();
    await expect(section.getByText(/not provider-supplied expected goals|not provider expected goals/).first()).toBeVisible();
    await expect(section.getByText(/Model projection: Arsenal/)).toBeVisible();
    await page.goto("/dashboard/sports");
    await page.getByRole("tab", { name: "Your data" }).click();
    await page.getByLabel("Dataset", { exact: true }).selectOption({ label: "E2E Premier League" });
  });
});

test("football intelligence: each data type shows its own requirements, then forecasts, scenarios and performance are explained", async ({ page }) => {
  test.setTimeout(360_000);
  // Six SYNTHETIC seasons (real club names, invented scores) in the five-column format, imported as one combined file.
  const clubs = ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton & Hove Albion", "Burnley", "Chelsea", "Crystal Palace", "Everton", "Fulham",
    "Leeds United", "Leicester City", "Liverpool", "Manchester City", "Manchester United", "Newcastle United", "Southampton", "Tottenham", "West Ham United", "Wolves"];
  const rows = ["date,home_team,away_team,home_goals,away_goals"];
  for (let year = 2016; year <= 2021; year++) {
    let i = 0;
    for (const h of clubs) for (const a of clubs) {
      if (h === a) continue;
      const d = new Date(Date.UTC(year, 7, 12) + 86_400_000 * 7 * Math.floor(i / 10));
      const strength = (c: string) => 1 + ((clubs.indexOf(c) * 7 + year) % 5) / 4;
      const hg = Math.floor(((i * 7 + year) % 5) * strength(h) / strength(a) / 2.2);
      const ag = Math.floor(((i * 5 + year) % 4) * strength(a) / strength(h) / 2);
      rows.push(`${d.toISOString().slice(0, 10)},${h},${a},${hg},${ag}`);
      i++;
    }
  }
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await test.step("every Data Workspace type shows only its own upload requirements", async () => {
    await page.goto("/dashboard/data");
    const kind = page.getByLabel("What is it?");
    await expect(kind.locator("option")).toHaveText(["Football match results", "Football advanced statistics", "Market prices / returns", "Party seats", "Numeric series"]);
    const note = page.getByRole("note").first();
    const history = page.getByRole("region", { name: "Historical Football Data" });
    await expect(note).toContainText("home_team, away_team, home_goals, away_goals");
    await expect(history).toBeVisible();
    for (const [label, has, hasNot] of [
      ["Football advanced statistics", "home_xg", "home_goals"], ["Market prices / returns", "one column per asset", "home_team"],
      ["Party seats", "party, seats", "home_team"], ["Numeric series", "one column per variable", "home_team"],
    ] as const) {
      await kind.selectOption({ label });
      await expect(note).toContainText(has);
      await expect(note).not.toContainText(hasNot);
      await expect(history).toBeHidden();                      // the football template and history section only belong to football match results
    }
    await kind.selectOption({ label: "Football match results" });
    await expect(history).toBeVisible();
  });

  await test.step("six seasons are imported as one combined file", async () => {
    const history = page.getByRole("region", { name: "Historical Football Data" });
    await page.getByLabel(/Season files/).setInputFiles({ name: "six_seasons.csv", mimeType: "text/csv", buffer: Buffer.from(rows.join("\n") + "\n") });
    await history.getByLabel(/Combined file/).check();
    await page.getByRole("button", { name: "Import Historical Data" }).click();
    await expect(history.getByText(/2,280 accepted/)).toBeVisible();
  });

  await page.goto("/dashboard/sports");
  await page.getByRole("tab", { name: "Football intelligence" }).click();
  const intel = page.getByRole("tabpanel");

  await test.step("factors are listed with what is unavailable", async () => {
    await page.getByRole("tab", { name: "Data & factors" }).click();
    await expect(intel.getByRole("rowheader", { name: /Player availability/ })).toBeVisible();
    await expect(intel.getByText("Nothing is filled in")).toBeVisible();
    await expect(intel.getByText("Unavailable").first()).toBeVisible();
  });

  await test.step("today's matches explains how to get fixtures", async () => {
    await page.getByRole("tab", { name: "Today's matches" }).click();
    await expect(intel.getByText(/Import a fixtures file/)).toBeVisible();
  });

  await test.step("match intelligence shows forecasts, drivers, reliability and warnings", async () => {
    await page.getByRole("tab", { name: "Match intelligence" }).click();
    await intel.getByLabel("Home team").selectOption("Arsenal");
    await intel.getByLabel("Away team").selectOption("Chelsea");
    await intel.getByRole("button", { name: "Analyse match" }).click();
    await expect(intel.getByText("Model forecast").first()).toBeVisible();
    await expect(intel.getByRole("rowheader", { name: "Dixon-Coles" })).toBeVisible();
    await expect(intel.getByRole("rowheader", { name: "Elo rating" })).toBeVisible();
    await expect(intel.getByText("Key prediction drivers")).toBeVisible();
    await expect(intel.getByText("Four separate measures")).toBeVisible();
    await expect(intel.getByText(/A 75% probability is not a 75% confidence score/)).toBeVisible();
    await expect(intel.getByText("Unavailable and not used:", { exact: false })).toBeVisible();
    await expect(intel.getByText(/Not a certainty, and not betting or financial advice/)).toBeVisible();
    await intel.getByRole("button", { name: "Save forecast" }).click();
    await expect(intel.getByText(/Saved\. It will be scored/)).toBeVisible();
  });

  await test.step("the simulator labels a scenario as hypothetical and disables unsupported inputs", async () => {
    await page.getByRole("tab", { name: "Simulator" }).click();
    await intel.getByLabel("Home team").selectOption("Arsenal");
    await intel.getByLabel("Away team").selectOption("Chelsea");
    await intel.getByLabel(/Home: attack lost to absent key players/).fill("0.3");
    await expect(intel.getByLabel("Rest days")).toBeDisabled();
    await expect(intel.getByLabel("Expected lineups")).toBeDisabled();
    await intel.getByRole("button", { name: "Recalculate" }).click();
    await expect(intel.getByText("Hypothetical scenario (not a forecast)")).toBeVisible();
    await expect(intel.getByText("Forecast from the data")).toBeVisible();
    await expect(intel.getByText(/HYPOTHETICAL: what the models would say/)).toBeVisible();
  });

  await test.step("a backtest measures every model against the baselines", async () => {
    await page.getByRole("tab", { name: "Model performance" }).click();
    await expect(intel.getByText(/No backtest has been run yet/)).toBeVisible();
    await intel.getByRole("button", { name: "Run chronological backtest" }).click();
    await expect(intel.getByText("Chronological backtest", { exact: true })).toBeVisible({ timeout: 180_000 });
    await expect(intel.getByText(/All chosen on validation only/)).toBeVisible();
    await expect(intel.getByRole("rowheader", { name: "Historical frequencies" }).first()).toBeVisible();
    await expect(intel.getByText(/the frequency baseline/).first()).toBeVisible();
    await expect(intel.getByText("By prediction market")).toBeVisible();
    await intel.getByLabel("Period").selectOption("validation");
    await expect(intel.getByText("Calibration", { exact: true })).toBeVisible();
    await expect(intel.getByText(/Nothing was tuned on the test period/)).toBeVisible();
    await expect(intel.getByRole("rowheader", { name: "Boosted trees" }).first()).toBeVisible();
    await expect(intel.getByRole("rowheader", { name: "Calibrated ensemble" }).first()).toBeVisible();
    await expect(intel.getByText(/(Boosted trees|Calibrated ensemble) (clearly|was)/).first()).toBeVisible();
  });

  await test.step("model operations: drift is not claimed without evidence, and the policy is explained", async () => {
    await page.getByRole("tab", { name: "Model operations" }).click();
    await expect(intel.getByText("Model health")).toBeVisible();
    await expect(intel.getByText("Not enough results yet")).toBeVisible();
    await expect(intel.getByText(/No scheduler is configured, so nothing runs by itself/)).toBeVisible();
    await expect(intel.getByText(/Policy: retrain when 100 or more matches/)).toBeVisible();
    await intel.getByRole("button", { name: "Check now" }).click();
    await expect(intel.getByText(/Checked\. \d+ finished forecasts? (was|were) scored/)).toBeVisible();
    await expect(intel.getByRole("cell", { name: "Checked, 0 scored" }).or(intel.getByRole("cell", { name: /Checked, \d+ scored/ })).first()).toBeVisible();
  });
});

test("the dashboard is usable on a phone without horizontal scrolling", async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true });
  const page = await ctx.newPage();
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "VELQORIN Strategy" }).click();
  await expect(page).toHaveURL(/\/dashboard\/business/);
  await expect(page.getByText(/only pure Nash equilibrium/)).toBeVisible();
  for (const path of ["/", "/dashboard", "/dashboard/business", "/dashboard/politics", "/dashboard/finance", "/dashboard/simulations", "/dashboard/workspace", "/dashboard/data"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const { overflow, culprits } = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth;
      const culprits: string[] = [];
      document.querySelectorAll("body *").forEach((el) => {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.right > vw + 1 && !el.closest(".overflow-x-auto") && getComputedStyle(el).position !== "fixed" && getComputedStyle(el).position !== "absolute") {
          culprits.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 60)} right=${Math.round(r.right)}`);
        }
      });
      return { overflow: document.documentElement.scrollWidth - vw, culprits: culprits.slice(0, 6) };
    });
    expect(overflow, `${path} overflows horizontally. Widest elements: ${culprits.join(" | ")}`).toBeLessThanOrEqual(1);
  }
  await ctx.close();
});
