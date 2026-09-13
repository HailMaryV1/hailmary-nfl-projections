"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";
import { disconnectFanteamTeam } from "./actions";

export default function DisconnectButton() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  function disconnect() {
    startTransition(async () => {
      await disconnectFanteamTeam();
      router.refresh();
    });
  }

  return (
    <button
      type="button"
      disabled={pending}
      onClick={disconnect}
      className="rounded-full bg-navy-800 px-3.5 py-1.5 text-xs font-semibold text-navy-300 hover:bg-navy-700 disabled:opacity-50"
    >
      Disconnect
    </button>
  );
}
