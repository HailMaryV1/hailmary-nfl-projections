"""
name_matching.py
-------------------
Shared surname-matching helpers for cross-source player matching (Spreadex/
RotoWire scrapes need to match a scraped name against players.full_name -
FanTeam's own import doesn't, since realPlayerId is a stable key there).

Ported as-is from dreamteam-projections/scripts/name_matching.py - proven,
game-agnostic (it operates on plain strings, not any project's schema).

RUN: not a script - imported by scraper/import scripts.
"""
import re
import unicodedata

_MANUAL_TRANSLITERATIONS = str.maketrans({
    "ø": "o", "Ø": "O",
    "æ": "ae", "Æ": "AE",
    "œ": "oe", "Œ": "OE",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "þ": "th", "Þ": "Th",
    "ß": "ss",
})


def transliterate(name: str) -> str:
    name = name.translate(_MANUAL_TRANSLITERATIONS)
    normalized = unicodedata.normalize("NFKD", name)
    return normalized.encode("ascii", "ignore").decode("ascii")


def compact(name: str) -> str:
    return re.sub(r"[^a-z]", "", transliterate(name).lower())


def first_letter_matches(a: str, b: str) -> bool:
    ca, cb = compact(a[:1]), compact(b[:1])
    return bool(ca) and ca == cb


_GENERATIONAL_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _strip_generational_suffix(full_name: str) -> str:
    """Real, confirmed-live gap (2026-09-07): FanTeam's real names carry a
    generational suffix ("Marvin Harrison Jr.", "Deebo Samuel Sr.", "James
    Cook III") that RotoWire's display names drop entirely ("Marvin
    Harrison"). Left unstripped, the surname key becomes "harrisonjr" vs
    "harrison" - a silent one-token mismatch, same class of bug the module
    docstring already calls out for accented letters. NFL-specific (Dream
    Team/football has no equivalent convention), so this lives only in
    this project's copy of the file."""
    parts = full_name.split(" ")
    if len(parts) > 1 and parts[-1].rstrip(".").lower() in _GENERATIONAL_SUFFIXES:
        return " ".join(parts[:-1])
    return full_name


def _raw_surname(full_name: str) -> str:
    full_name = _strip_generational_suffix(full_name)
    if ". " in full_name:
        return full_name.split(". ", 1)[1]
    parts = full_name.split(" ")
    return " ".join(parts[1:]) if len(parts) > 1 else full_name


def surname_key(full_name: str) -> str:
    return compact(_raw_surname(full_name))


def resolve_player_id(cur, name, team_ids):
    """Exact full_name match first; falls back to a surname-key match
    scoped to team_ids, then a first-initial tiebreak if that's still
    ambiguous - real, confirmed-live case (2026-09-07): Minnesota rosters
    both "Aaron Jones Sr." and "Jeshaun Jones", same surname_key "jones",
    same team - a bare surname match can't tell them apart, but their
    first initials ("A" vs "J") do."""
    team_ids = list(team_ids)
    cur.execute("select id from players where full_name = %s and team_id = any(%s)", (name, team_ids))
    rows = cur.fetchall()
    if len(rows) == 1:
        return rows[0][0]
    if rows:
        return None
    key = surname_key(name)
    if not key:
        return None
    cur.execute("select id, full_name from players where team_id = any(%s)", (team_ids,))
    matches = [(pid, full_name) for pid, full_name in cur.fetchall() if surname_key(full_name) == key]
    if len(matches) == 1:
        return matches[0][0]
    if len(matches) > 1:
        narrowed = [(pid, fn) for pid, fn in matches if first_letter_matches(fn, name)]
        if len(narrowed) == 1:
            return narrowed[0][0]
    return None


def full_name_key(full_name: str) -> str:
    """Whole-name (first+last, generational suffix stripped) normalized
    key - unlike surname_key, requires the FULL name to align, not just
    the surname. Used where team-scoping alone is too weak to trust a
    bare surname match - see resolve_player_id_strict."""
    return compact(_strip_generational_suffix(full_name))


def resolve_player_id_strict(cur, name, team_ids):
    """Exact full_name match, then a normalized-whole-name match (handles
    real punctuation/accent/generational-suffix differences) - both
    scoped to team_ids. Deliberately NO bare-surname fallback.

    Real, confirmed-live bug (2026-09-14) found while backfilling
    historical NFL seasons via API-Sports: resolve_player_id's own
    surname+team fallback is safe when matching against a real CURRENT
    roster (RotoWire's own use case - this project's players table IS
    that season's real roster), but produces real false positives when
    matching against an OLD historical season's real roster, which
    includes players no longer in our current ~603-player reference set.
    Confirmed example: "DeSean Jackson" (2022 Baltimore Ravens, no longer
    tracked) wrongly resolved to the CURRENT "Lamar Jackson" (also a real
    Raven) - different real people, same surname, same team, only one of
    them still in our reference table. Returns None rather than guess
    whenever more than one real player matches - a real miss is always
    preferred over a real misattribution here."""
    team_ids = list(team_ids)
    cur.execute("select id from players where full_name = %s and team_id = any(%s)", (name, team_ids))
    rows = cur.fetchall()
    if len(rows) == 1:
        return rows[0][0]
    if rows:
        return None
    key = full_name_key(name)
    if not key:
        return None
    cur.execute("select id, full_name from players where team_id = any(%s)", (team_ids,))
    matches = [pid for pid, full_name in cur.fetchall() if full_name_key(full_name) == key]
    if len(matches) == 1:
        return matches[0]
    return None


def surname_variants(full_name: str) -> set:
    parts = _raw_surname(full_name).split("-")
    return {compact("-".join(parts[i:])) for i in range(len(parts))}
