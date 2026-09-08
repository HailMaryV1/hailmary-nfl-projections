"use client";

import { useRouter } from "next/navigation";
import { createAuthBrowserClient } from "@/lib/supabaseBrowserClient";

export default function SignOutButton() {
  const router = useRouter();

  async function handleSignOut() {
    const supabase = createAuthBrowserClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={handleSignOut}
      className="rounded-md px-3 py-2 text-left text-sm text-navy-400 hover:bg-navy-900 hover:text-rose-300"
    >
      Sign out
    </button>
  );
}
