import type { Metadata } from "next";
import { brand } from "@/lib/brand";
import { LegalPage } from "@/components/pages/LegalPage";

export const metadata: Metadata = {
  title: "Terms of Use",
  description: `The terms that apply when you use ${brand.name}.`,
  alternates: { canonical: "/terms" },
};

export default function Page() {
  return (
    <LegalPage title="Terms of Use" updated="[date]">
      <p>
        These terms govern your use of {brand.domain} and the {brand.name} application, provided by [legal entity name] (&ldquo;we&rdquo;). By creating an account or using the service you agree to them.
      </p>
      <h2>The service</h2>
      <p>{brand.name} provides probabilistic models, simulations and explanations for sports, business strategy, politics and financial markets. The service is in early access and may change or be interrupted.</p>
      <h2>Not advice</h2>
      <p>
        Outputs are model projections under stated assumptions. They are not predictions of certainty and are not financial, investment, legal, political or betting advice. Demonstration data is labeled as such. You are responsible for your decisions and for checking that your use complies with the law where you live.
      </p>
      <h2>Your account</h2>
      <ul>
        <li>Provide accurate information and keep your password secure; you are responsible for activity under your account.</li>
        <li>Tell us promptly at [support email] if you suspect unauthorized access.</li>
      </ul>
      <h2>Acceptable use</h2>
      <ul>
        <li>No attempts to disrupt, probe or overload the service, or to access other users&rsquo; data.</li>
        <li>No unlawful use, and no use to deceive voters or to target individuals. Political modeling is aggregate and nonpartisan.</li>
        <li>No automated scraping or resale of outputs without our written permission.</li>
      </ul>
      <h2>Your content</h2>
      <p>You keep ownership of the inputs and scenarios you save. You grant us the limited right to host and process them to run the service. Saved forecasts are stored as an immutable record.</p>
      <h2>Our property</h2>
      <p>The service, models, software, and the {brand.name} name and logo belong to us or our licensors. These terms do not transfer them to you.</p>
      <h2>Disclaimers and liability</h2>
      <p>The service is provided &ldquo;as is&rdquo; without warranties of accuracy or availability. To the extent the law allows, we are not liable for indirect or consequential losses or for decisions made using outputs. [Counsel to finalize the limitation of liability.]</p>
      <h2>Termination</h2>
      <p>You may stop using the service at any time and export your workspace. We may suspend accounts that breach these terms.</p>
      <h2>Governing law</h2>
      <p>[Jurisdiction and governing law.] Contact: [support email].</p>
    </LegalPage>
  );
}
