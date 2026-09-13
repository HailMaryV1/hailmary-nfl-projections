"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createAuthBrowserClient } from "@/lib/supabaseBrowserClient";
import { isAdminEmail } from "@/lib/adminAccess";

export default function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const supabase = createAuthBrowserClient();
    const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password });

    if (signInError) {
      setLoading(false);
      setError("Incorrect email or password.");
      return;
    }

    const from = searchParams.get("from") || "/admin";
    // Real fix 2026-09-13: a correct password used to be enough to reach
    // /admin, which only checked "signed in" - but /playbook/builder and
    // /playbook/custom are real, any-signed-in-customer routes, so a
    // correct password for one of THOSE must never be rejected just
    // because the email isn't one of the two admin addresses. Only reject
    // when the sign-in is actually destined for /admin.
    if (from.startsWith("/admin") && !isAdminEmail(data.user?.email)) {
      await supabase.auth.signOut();
      setLoading(false);
      setError("This account isn't authorized for admin access.");
      return;
    }

    setLoading(false);
    router.push(from);
    router.refresh();
  }

  return (
    <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm text-navy-300">
        Email
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-navy-100 focus:outline-none focus:ring-2 focus:ring-sky-400/40"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm text-navy-300">
        Password
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-navy-100 focus:outline-none focus:ring-2 focus:ring-sky-400/40"
        />
      </label>
      {error && <p className="text-sm text-rose-400">{error}</p>}
      <button
        type="submit"
        disabled={loading}
        className="mt-2 rounded-md bg-sky-500 px-4 py-2 text-sm font-semibold text-navy-950 hover:bg-sky-400 disabled:opacity-60"
      >
        {loading ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
