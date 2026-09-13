// Ported from the sibling dreamteam-projections/EFL-Projections projects.
// Real gap this closes: every admin gate here used to treat "is anyone
// logged in" as good enough - fine while this Supabase project had exactly
// one real account, but /playbook/builder and /playbook/custom already
// give real customers their own accounts on this exact project, so any of
// those accounts would otherwise also count as "logged in" for /admin.
// Single source of truth so proxy.ts, the admin layout, every admin write
// action, and the login form all agree on who "the admin" actually is.
const ADMIN_EMAILS = new Set(["info@footyfits.co.uk", "tony@dreamteamtonic.co.uk"]);

export function isAdminEmail(email: string | null | undefined): boolean {
  if (!email) return false;
  return ADMIN_EMAILS.has(email.trim().toLowerCase());
}
