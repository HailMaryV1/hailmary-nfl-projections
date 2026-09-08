import { createBrowserClient } from "@supabase/ssr";

// Browser-side client, used only by the login form (signInWithPassword) -
// everything else reads via the server client or the public anon client.
export function createAuthBrowserClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
