"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { connectFanteamTeam } from "./actions";

export default function ConnectTeamForm() {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      const result = await connectFanteamTeam(value);
      if ("error" in result) setError(result.error);
      else router.refresh();
    });
  }

  return (
    <form onSubmit={submit} className="flex max-w-xl flex-col gap-2.5 sm:flex-row">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="FanTeam entry id, or your team's dashboard URL"
        className="flex-1 rounded-md border border-navy-700 bg-navy-950 px-3.5 py-2.5 text-sm text-navy-100 placeholder:text-navy-600 focus:outline-none focus:ring-2 focus:ring-sky-400/40"
      />
      <button
        type="submit"
        disabled={pending || !value.trim()}
        className="rounded-md bg-sky-500 px-5 py-2.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide text-navy-950 hover:bg-sky-300 disabled:opacity-50"
      >
        {pending ? "Looking up…" : "Import team"}
      </button>
      {error && <p className="text-xs text-rose-400 sm:basis-full">{error}</p>}
    </form>
  );
}
