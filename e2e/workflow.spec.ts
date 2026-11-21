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
  for (const path of ["/", "/login", "/signup", "/pricing", "/about", "/sports", "/business", "/politics", "/finance", "/how-it-works", "/early-access", "/terms", "/privacy", "/no-such-page"]) {
    await expectBranded(page, path);
  }
  await page.goto("/");
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
  // Billing endpoints: anonymous checkout is refused, and the webhook never accepts unsigned requests.
  expect((await request.post("/api/billing/checkout", { data: { plan: "strategy_pro", interval: "month" } })).status()).toBe(401);
  expect((await request.post("/api/billing/portal", { data: {} })).status()).toBe(401);
  expect((await request.post("/api/team/invites", { data: { email: "x@example.com", role: "member" } })).status()).toBe(401);
  expect([400, 503]).toContain((await request.post("/api/stripe/webhook", { data: "{}" })).status());
});

test("landing page leads to a working account and every module", async ({ page }) => {
  await test.step("landing page", async () => {
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Predict Outcomes.");
    await expect(page.getByRole("link", { name: "Explore VELQORIN", exact: true })).toHaveAttribute("href", "#demo");
    await page.getByRole("link", { name: "See How It Works" }).first().click();
    await expect(page).toHaveURL(/\/how-it-works/);
    await page.goto("/");
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
    await upload("Sports results", "E2E league", sports);
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
