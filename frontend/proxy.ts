import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

// Next.js 16 renamed middleware.ts -> proxy.ts (same convention already
// used in the sibling dreamteam-projections repo). Gates /admin/* behind
// a real Supabase Auth session - everything else (the public projections
// pool, player pages) stays open, no gate.
export default async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    }
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Custom pools/playbooks are a real person's own saved data (see
  // supabase/migrations/0013_custom_playbooks.sql) - gated the same way
  // as /admin, not public like the two fixed playbooks at /playbook and
  // /playbook/auto-draft.
  const isProtectedRoute = request.nextUrl.pathname.startsWith("/admin") || request.nextUrl.pathname.startsWith("/playbook/builder") || request.nextUrl.pathname.startsWith("/playbook/custom");
  if (isProtectedRoute && !user) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

export const config = {
  matcher: ["/admin/:path*", "/playbook/builder/:path*", "/playbook/custom/:path*"],
};
