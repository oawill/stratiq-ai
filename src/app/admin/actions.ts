"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { adminConfigured, checkPassword, COOKIE, makeToken } from "@/lib/adminAuth";

export async function login(_: { error?: string } | undefined, form: FormData) {
  if (!adminConfigured()) return { error: "Admin is not configured on this server." };
  if (!checkPassword(String(form.get("password") ?? ""))) return { error: "Incorrect password." };
  (await cookies()).set(COOKIE, makeToken(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/admin",
    maxAge: 8 * 60 * 60,
  });
  redirect("/admin");
}

export async function logout() {
  (await cookies()).delete({ name: COOKIE, path: "/admin" });
  redirect("/admin");
}
