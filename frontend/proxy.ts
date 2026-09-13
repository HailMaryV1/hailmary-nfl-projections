import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";
import { isAdminEmail } from "@/lib/adminAccess";

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

  // Real fix 2026-09-13: "is signed in" isn't the same as "is the admin" -
  // /admin (which now also covers the relocated My Playbook/Auto-Draft
  // boards, the site owner's own personal season plans) needs the real
  // admin allowlist, see lib/adminAccess.ts. Custom pools/playbooks are a
  // real CUSTOMER's own saved data (see
  // supabase/migrations/0013_custom_playbooks.sql) - gated on "any real
  // signed-in user" only, same as before; applying the admin allowlist
  // there would lock real customers out of their own saved pool/playbook.
  const isAdminRoute = request.nextUrl.pathname.startsWith("/admin");
  const isUserRoute = request.nextUrl.pathname.startsWith("/playbook/builder") || request.nextUrl.pathname.startsWith("/playbook/custom");
  const isAllowed = isAdminRoute ? isAdminEmail(user?.email) : isUserRoute ? Boolean(user) : true;
  if (!isAllowed) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

export const config = {
  matcher: ["/admin/:path*", "/playbook/builder/:path*", "/playbook/custom/:path*"],
};
