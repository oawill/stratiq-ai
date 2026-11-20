import { brand } from "./brand";

/**
 * Transactional email through the Resend HTTP API. Provider-agnostic at the call sites: swap `deliver` to change provider.
 * Disabled (a harmless no-op) until RESEND_API_KEY and EMAIL_FROM are set, so nothing is sent from environments without them.
 */
export type Mail = { to: string; subject: string; text: string; html: string };
export type SendResult = { sent: true } | { sent: false; reason: string };

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function layout(bodyHtml: string) {
  return `<div style="font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;padding:24px;color:#0b1020;line-height:1.55">
<p style="font-size:18px;font-weight:700;letter-spacing:.12em;margin:0 0 16px">${brand.name}</p>${bodyHtml}
<p style="color:#667;font-size:12px;margin-top:28px">${brand.name} provides probabilistic analysis, not certainty, and not financial, legal, or betting advice. You received this because you registered at ${brand.domain}.</p></div>`;
}

export function earlyAccessEmail(to: string, fullName: string): Mail {
  const first = fullName.trim().split(/\s+/)[0] || "there";
  return {
    to,
    subject: `You're on the ${brand.name} early-access list`,
    text: `Hi ${first},\n\nThanks for registering your interest in ${brand.name}. You're on the early-access list, and we'll email you when access opens. We only use your details for that purpose.\n\n${brand.tagline}\n${brand.website}\n`,
    html: layout(`<p>Hi ${esc(first)},</p><p>Thanks for registering your interest in ${brand.name}. You're on the early-access list, and we'll email you when access opens. We only use your details for that purpose.</p><p><a href="${brand.website}">${brand.domain}</a></p>`),
  };
}

export function welcomeEmail(to: string, name: string): Mail {
  const first = name.trim().split(/\s+/)[0] || "there";
  return {
    to,
    subject: `Welcome to ${brand.name}`,
    text: `Hi ${first},\n\nYour ${brand.name} account is ready. Sign in to explore Sports, Strategy, Politics, Markets and SimLab:\n${brand.website}/login\n\nResults are model projections under stated assumptions, not predictions of certainty.\n`,
    html: layout(`<p>Hi ${esc(first)},</p><p>Your ${brand.name} account is ready. Sign in to explore Sports, Strategy, Politics, Markets and SimLab.</p><p><a href="${brand.website}/login">Sign in</a></p><p>Results are model projections under stated assumptions, not predictions of certainty.</p>`),
  };
}

export async function sendEmail(mail: Mail): Promise<SendResult> {
  const key = process.env.RESEND_API_KEY;
  const from = process.env.EMAIL_FROM;
  if (!key || !from) return { sent: false, reason: "email not configured" };
  // .test is a reserved TLD: addresses used by automated tests are never real.
  if (/\.test$/i.test(mail.to)) return { sent: false, reason: "test address" };
  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ from, to: [mail.to], subject: mail.subject, text: mail.text, html: mail.html }),
    });
    if (!res.ok) return { sent: false, reason: `provider status ${res.status}` };
    return { sent: true };
  } catch (e) {
    return { sent: false, reason: e instanceof Error ? e.message : "send failed" };
  }
}

/** Fire-and-forget wrapper: email failure must never fail a signup. */
export async function sendQuietly(mail: Mail) {
  const r = await sendEmail(mail);
  if (!r.sent && r.reason !== "email not configured" && r.reason !== "test address") console.error("email not sent:", r.reason);
}
