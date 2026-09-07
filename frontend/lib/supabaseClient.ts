import { createClient } from "@supabase/supabase-js";

// Public, read-only access (RLS: every table this app reads from is
// "public read" - see supabase/migrations). No auth/session handling
// needed yet - that's Phase 4 (admin settings), not the public pool view.
export function createPublicClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  );
}
