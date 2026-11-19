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
const withoutTestEmails = (t: string) => t.replace(/[\w.+-]+@stratiq\.test/g, "");

/** Every page a visitor can see must carry the VELQORIN.ai brand and never the previous name. */
async function expectBranded(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  await expect(page, `${path} title`).toHaveTitle(/VELQORIN/);
  const text = withoutTestEmails(await page.evaluate(() => document.body.innerText));
  expect(text, `${path} shows the previous brand name`).not.toMatch(/stratiq/i);
  const html = await page.content();
  const leftover = withoutTestEmails(html).replace(/(src|href|action|name|id|content)="[^"]*"/g, "").match(/.{0,50}stratiq.{0,50}/gi) ?? [];
  expect(leftover, `${path} markup mentions the previous brand`).toEqual([]);
}

test.describe.configure({ mode: "serial" });

test("public pages, metadata and assets carry the VELQORIN.ai brand", async ({ page, request }) => {
  for (const path of ["/", "/login", "/signup", "/pricing", "/about", "/sports", "/business", "/politics", "/finance", "/how-it-works", "/early-access", "/no-such-page"]) {
    await expectBranded(page, path);
  }
  await page.goto("/");
  await expect(page.getByRole("link", { name: "VELQORIN.ai" }).first()).toBeVisible();
  await expect(page.getByText("Intelligence Beyond Prediction").first()).toBeVisible();
  await expect(page.getByText("Predict. Simulate. Strategize.").first()).toBeVisible();
  await expect(page.locator('meta[property="og:site_name"]')).toHaveAttribute("content", "VELQORIN.ai");
  await expect(page.locator('meta[property="og:image"]')).toHaveCount(1);
  const ld = JSON.parse((await page.locator('script[type="application/ld+json"]').first().textContent()) ?? "{}");
  expect(ld.name).toBe("VELQORIN.ai");
  expect(ld.slogan).toBe("Intelligence Beyond Prediction");
  const manifest = await (await request.get("/manifest.webmanifest")).json();
  expect(manifest.name).toBe("VELQORIN.ai");
  expect(manifest.short_name).toBe("VELQORIN");
  for (const asset of ["/icon.svg", "/favicon.ico", "/apple-icon.png", "/opengraph-image.png", "/icons/icon-192.png", "/icons/icon-512.png"]) {
    const res = await request.get(asset);
    expect(res.status(), asset).toBe(200);
  }
  // The product names appear in the marketing navigation.
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
});

test("landing page leads to a working account and every module", async ({ page }) => {
  await test.step("landing page", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Predict Outcomes.");
    await page.getByRole("link", { name: "Log In" }).first().click();
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
    for (const path of ["/dashboard", "/dashboard/sports", "/dashboard/business", "/dashboard/politics", "/dashboard/finance", "/dashboard/simulations", "/dashboard/history", "/dashboard/workspace", "/dashboard/settings"]) {
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
  for (const path of ["/dashboard", "/dashboard/business", "/dashboard/politics", "/dashboard/finance", "/dashboard/simulations", "/dashboard/workspace"]) {
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
