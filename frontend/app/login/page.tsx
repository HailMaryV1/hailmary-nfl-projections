"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createAuthBrowserClient } from "@/lib/supabaseBrowserClient";

export default function LoginPage() {
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
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });

    setLoading(false);
    if (signInError) {
      setError("Incorrect email or password.");
      return;
    }
    router.push(searchParams.get("from") || "/admin");
    router.refresh();
  }

  return (
    <main className="mx-auto flex w-full min-w-0 max-w-sm flex-1 flex-col justify-center p-6">
      <h1 className="text-xl font-semibold text-navy-100">Admin sign in</h1>
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
    </main>
  );
}
