import { z } from "zod";

export const INTERESTS = ["Sports", "Business", "Politics", "Finance"] as const;
export const USES = ["Personal", "Analyst", "Business", "Enterprise"] as const;

export const signupSchema = z.object({
  fullName: z.string().trim().min(2, "Please enter your full name.").max(120),
  email: z.string().trim().toLowerCase().email("Please enter a valid email address.").max(254),
  country: z.string().trim().min(2, "Please enter your country.").max(80),
  interest: z.enum(INTERESTS, { error: "Please choose a primary interest." }),
  use: z.enum(USES, { error: "Please choose an intended use." }),
  consent: z.literal(true, { error: "Consent is required to register." }),
  source: z.string().trim().max(120).optional(),
  // Honeypot: real users never fill this in.
  website: z.string().max(0).optional(),
  // Timestamp the form rendered at (ms), for a minimum-fill-time check.
  t: z.number().optional(),
});

export type SignupInput = z.infer<typeof signupSchema>;
