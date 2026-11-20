import { afterEach, describe, expect, it, vi } from "vitest";
import { earlyAccessEmail, sendEmail, welcomeEmail } from "./email";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("email", () => {
  it("does nothing until configured", async () => {
    vi.stubEnv("RESEND_API_KEY", "");
    vi.stubEnv("EMAIL_FROM", "");
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    expect(await sendEmail(welcomeEmail("a@example.com", "Ada"))).toEqual({ sent: false, reason: "email not configured" });
    expect(f).not.toHaveBeenCalled();
  });

  it("never sends to reserved .test addresses", async () => {
    vi.stubEnv("RESEND_API_KEY", "k");
    vi.stubEnv("EMAIL_FROM", "VELQORIN <hello@velqorin.ai>");
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    expect((await sendEmail(welcomeEmail("e2e@stratiq.test", "E"))).sent).toBe(false);
    expect(f).not.toHaveBeenCalled();
  });

  it("posts to the provider when configured, and reports provider errors", async () => {
    vi.stubEnv("RESEND_API_KEY", "k");
    vi.stubEnv("EMAIL_FROM", "VELQORIN <hello@velqorin.ai>");
    const f = vi.fn().mockResolvedValueOnce({ ok: true }).mockResolvedValueOnce({ ok: false, status: 422 });
    vi.stubGlobal("fetch", f);
    expect(await sendEmail(welcomeEmail("a@example.com", "Ada"))).toEqual({ sent: true });
    expect(await sendEmail(welcomeEmail("a@example.com", "Ada"))).toEqual({ sent: false, reason: "provider status 422" });
  });

  it("escapes names in HTML and uses the VELQORIN brand only", () => {
    const m = earlyAccessEmail("a@example.com", "<b>Eve</b> Smith");
    expect(m.html).not.toContain("<b>Eve");
    expect(m.html).toContain("&lt;b&gt;Eve&lt;/b&gt;");
    for (const mail of [m, welcomeEmail("a@example.com", "Ada")]) {
      expect(mail.subject + mail.text + mail.html).not.toMatch(/VELQORIN\.ai|STRATIQ|Stratiq/); // the lowercase website address velqorin.ai is allowed
    }
  });
});
