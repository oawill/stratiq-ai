import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { LegalPage } from "@/components/pages/LegalPage";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: `How ${brand.name} collects, uses and protects personal information.`,
  alternates: { canonical: "/privacy" },
};

export default function Page() {
  return (
    <LegalPage title="Privacy Policy" updated="[date]">
      <p>
        This policy explains what personal information {brand.name} ([legal entity name], &ldquo;we&rdquo;) collects through {brand.domain} and the {brand.name} application, why, and the choices you have.
        Contact: [privacy contact email].
      </p>
      <h2>Information we collect</h2>
      <ul>
        <li><strong className="text-ink">Early-access registration:</strong> full name, email address, country, primary interest, intended use, your consent, and the page you registered from.</li>
        <li><strong className="text-ink">Account:</strong> name, email address and a salted password hash (we never store your password). We also keep a record of account events such as sign-up in an audit log.</li>
        <li><strong className="text-ink">Your work:</strong> the forecasts, scenarios, simulations, inputs and workspace names you save. Saved forecasts are kept as an immutable record by design.</li>
        <li><strong className="text-ink">Technical data:</strong> standard server logs (such as IP address, request path and errors) and aggregate, cookieless page-view analytics.</li>
      </ul>
      <h2>How we use it</h2>
      <ul>
        <li>To provide and secure your account and workspaces.</li>
        <li>To contact you about early access, and to send transactional emails such as a registration confirmation or welcome message.</li>
        <li>To keep the service reliable and to diagnose errors.</li>
      </ul>
      <p>We do not sell personal information. [Confirm before launch, including any use of saved work.]</p>
      <h2>Cookies and local storage</h2>
      <ul>
        <li>A strictly necessary session cookie keeps you signed in; it is removed when you sign out or it expires.</li>
        <li>Your browser&rsquo;s local storage remembers a display preference (advanced view). It stays on your device.</li>
        <li>We do not use advertising or cross-site tracking cookies.</li>
      </ul>
      <h2>Service providers</h2>
      <p>
        We use providers to run the service: hosting and analytics ([Vercel]), database ([Neon]) and email delivery ([Resend], once enabled). They process data on our instructions. [Complete with the final provider list, locations and transfer mechanisms.]
      </p>
      <h2>Retention</h2>
      <p>We keep account and workspace data while your account is active. Early-access registrations are kept until access opens or you ask us to remove them. [Define periods.]</p>
      <h2>Your rights</h2>
      <p>Depending on where you live, you may have the right to access, correct, export or delete your personal information, to withdraw consent, and to complain to a regulator. You can export your workspace from the application. To exercise any right, write to [privacy contact email].</p>
      <h2>Children</h2>
      <p>{brand.name} is not directed to children under [age] and we do not knowingly collect their information.</p>
      <h2>Changes</h2>
      <p>We will update this page when our practices change and revise the date above.</p>
    </LegalPage>
  );
}
