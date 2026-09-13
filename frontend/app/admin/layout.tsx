import Link from "next/link";
import { redirect } from "next/navigation";
import SiteHeader from "../SiteHeader";
import SignOutButton from "./SignOutButton";
import { createAuthServerClient } from "@/lib/supabaseServerClient";
import { isAdminEmail } from "@/lib/adminAccess";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  // proxy.ts already redirects a non-admin visitor before this ever
  // renders - this is defense in depth, not the only gate (every admin
  // write action below also checks this independently, since a Server
  // Action is a directly-callable POST endpoint, not protected by page
  // gating alone).
  const supabase = await createAuthServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user || !isAdminEmail(user.email)) {
    redirect("/login");
  }

  return (
    <>
      <SiteHeader />
      <div className="mx-auto flex w-full min-w-0 max-w-5xl flex-1 flex-col gap-6 p-4 sm:flex-row sm:p-6">
        <nav className="flex shrink-0 flex-row gap-1 overflow-x-auto sm:w-44 sm:flex-col">
          <Link href="/admin/scoring-rules" className="whitespace-nowrap rounded-md px-3 py-2 text-sm text-navy-300 hover:bg-navy-900 hover:text-sky-300">
            Scoring Rules
          </Link>
          <Link href="/admin/layer-weights" className="whitespace-nowrap rounded-md px-3 py-2 text-sm text-navy-300 hover:bg-navy-900 hover:text-sky-300">
            Layer Weights
          </Link>
          <div className="my-1 border-t border-navy-800" />
          <Link href="/admin/playbook" className="whitespace-nowrap rounded-md px-3 py-2 text-sm text-navy-300 hover:bg-navy-900 hover:text-sky-300">
            My Playbook
          </Link>
          <Link href="/admin/playbook/auto-draft" className="whitespace-nowrap rounded-md px-3 py-2 text-sm text-navy-300 hover:bg-navy-900 hover:text-sky-300">
            Auto-Draft
          </Link>
          <div className="mt-auto hidden sm:block">
            <SignOutButton />
          </div>
        </nav>
        <div className="min-w-0 flex-1">{children}</div>
        <div className="sm:hidden">
          <SignOutButton />
        </div>
      </div>
    </>
  );
}
