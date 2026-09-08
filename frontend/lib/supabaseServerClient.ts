import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

// Auth-aware server client - reads/writes the real Supabase Auth session
// via cookies, so RLS's "admin write" policies (scoring_rules,
// layer_weights - see migrations 0005/0006) see the request as the real
// logged-in admin, not the anonymous role.
export async function createAuthServerClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
          } catch {
            // Called from a Server Component that can't set cookies - fine,
            // the middleware/proxy already refreshes the session.
          }
        },
      },
    }
  );
}
