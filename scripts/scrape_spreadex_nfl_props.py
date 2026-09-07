"""
scrape_spreadex_nfl_props.py
-------------------------------
Real player-prop odds from Spreadex's real "Weekly Player Markets" page -
confirmed live 2026-09-07 to carry every one of the week's 16 real
fixtures' player markets on ONE aggregated page, split across 5 real tabs
(Passing, Rushing + Receiving, Rushing, Receiving, Sacks). Unlike Dream
Team's per-fixture Spreadex scrape, there's no per-fixture navigation here
- just switch tabs and read.

IMPORTANT - same live retail UI caveats as Dream Team's Spreadex scraper
(scrape_spreadex_player_markets.py in the sibling dreamteam-projections
repo): Angular SPA, no JSON snapshot, auto-generated class names EXCEPT the
handful this script actually relies on (`sc-panel`,
`.p-panel-container__header-name`, the real `fo-price-wrapper-button`
aria-label convention, `.pp-panel-groups__group-name` tabs) - all confirmed
live by direct DOM inspection, not guessed. EXPECT this to need repair the
next time Spreadex redesigns the page.

Two real aria-label shapes, confirmed live across both the Passing and
Rushing tabs (same shape holds for Receiving/Sacks - not independently
verified per-tab, but same component library):
  - Ladder:      "{Player} - {N}+ Price Button"       -> market "{base}_{N}plus"
  - Over/Under:  "{Player} Over {X} Price Button"      -> market "{base}_over_{X}"
                 "{Player} Under {X} Price Button"     -> market "{base}_under_{X}"
An unrecognised label shape is skipped and counted, never guessed.

Each rung is stored as its OWN row (implied probability = 1/decimal odds) -
Phase 2 is data ingestion only; fitting an expected-yardage/TD-count value
from the stored ladder is Phase 3's job (see docs/data-and-weights.md), not
this script's.

RUN:
    python scripts/scrape_spreadex_nfl_props.py
"""
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect  # noqa: E402
from name_matching import resolve_player_id  # noqa: E402

URL = "https://www.spreadex.com/sports/en-GB/spread-betting/american-football/nfl/weekly-player-markets/fo/p9852595"

# "Sacks" deliberately excluded: confirmed live (2026-09-07) this market
# prices INDIVIDUAL defensive players, but this project's player pool only
# rosters the team-level defense_special unit (FanTeam's own real ruleset -
# no individual defenders at all). A name-only match against this market
# produced a real false positive (an individual defender's "Kyle Williams"
# silently matched our unrelated offensive WR of the same name, scoped
# match unable to tell them apart since neither is genuinely present).
# Scraping it risks wrong attributions, not just gaps - worse than skipping
# it outright.
TABS = ["Passing", "Rushing + Receiving", "Rushing", "Receiving"]

LADDER_RE = re.compile(r"^(.*) - (\d+)\+ Price Button$")
OU_RE = re.compile(r"^(.*) (Over|Under) ([\d.]+) Price Button$")

# Real, confirmed-live quirk (2026-09-07): Spreadex renders SOME team codes
# in Title Case ("Atl @ Pit", "Bal @ Ind") and others fully capitalised
# ("NE @ Sea" - wait, "Sea" is also Title Case; "TB @ Cin", "NYJ @ Ten") in
# the SAME header text, no consistent rule - matched case-insensitively and
# upper-cased before comparing against our all-caps teams.abbr.
HEADER_RE = re.compile(r"^([A-Za-z]{2,4}) @ ([A-Za-z]{2,4}): Player (.+)$")

EXTRACT_TAB_JS = """
() => {
  const panels = [...document.querySelectorAll('sc-panel')].filter(p => p.querySelectorAll('sc-panel').length === 0);
  return panels.map(panel => {
    const headerEl = panel.querySelector('.p-panel-container__header-name');
    const header = headerEl ? headerEl.textContent.trim() : null;
    const buttons = [...panel.querySelectorAll('fo-price-wrapper-button')].map(b => ({
      label: b.getAttribute('aria-label'),
      text: b.textContent.trim(),
    }));
    return { header, buttons };
  }).filter(p => p.header);
}
"""


def slugify(text):
    text = text.lower().replace("/", " ")
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def fractional_to_decimal(fractional_odds):
    text = (fractional_odds or "").strip()
    if text.lower() == "evs":
        numerator, denominator = 1.0, 1.0
    else:
        parts = text.split("/")
        if len(parts) != 2:
            return None
        try:
            numerator, denominator = float(parts[0]), float(parts[1])
        except ValueError:
            return None
    if denominator <= 0:
        return None
    return 1 + numerator / denominator


def click_tab_and_expand(page, tab_name):
    page.get_by_text(tab_name, exact=True).first.click(timeout=10000)
    page.wait_for_timeout(1200)
    try:
        expand_all = page.get_by_text("Expand all", exact=True).first
        if expand_all.count():
            expand_all.click(timeout=5000)
            page.wait_for_timeout(1200)
    except Exception:
        pass


def find_fixture(cur, home_abbr, away_abbr):
    cur.execute(
        """
        select f.id, f.home_team_id, f.away_team_id
        from fixtures f
        join teams ht on ht.id = f.home_team_id
        join teams at_ on at_.id = f.away_team_id
        where ht.abbr = %s and at_.abbr = %s and f.kickoff_at > now() - interval '6 hours'
        order by f.kickoff_at asc
        limit 1
        """,
        (home_abbr, away_abbr),
    )
    return cur.fetchone()


def parse_button(label, base_market):
    if not label:
        return None
    m = LADDER_RE.match(label)
    if m:
        player_name, rung = m.group(1).strip(), m.group(2)
        return player_name, f"{base_market}_{rung}plus"
    m = OU_RE.match(label)
    if m:
        player_name, direction, threshold = m.group(1).strip(), m.group(2).lower(), m.group(3)
        base = re.sub(r"_over_under$", "", base_market)
        return player_name, f"{base}_{direction}_{threshold}"
    return None


def import_panel(cur, panel, fixture_cache, seen_headers):
    header = panel["header"]
    if header in seen_headers:
        # Real, confirmed-live overlap (2026-09-07): a handful of panels
        # (e.g. "Player Passing and Rushing Yards") appear under more than
        # one tab (Rushing AND Rushing + Receiving) - same real market,
        # same DOM panel content, not two independent observations. Skip
        # rather than double-insert within a single run; a genuinely new
        # observation from a LATER run still gets its own row as intended.
        return 0, 0, 0
    seen_headers.add(header)

    m = HEADER_RE.match(header or "")
    if not m:
        return 0, 0, 0
    away_abbr, home_abbr, market_text = m.group(1).upper(), m.group(2).upper(), m.group(3)
    base_market = slugify(market_text)

    cache_key = (home_abbr, away_abbr)
    if cache_key not in fixture_cache:
        fixture_cache[cache_key] = find_fixture(cur, home_abbr, away_abbr)
    fixture_row = fixture_cache[cache_key]
    if fixture_row is None:
        return 0, 0, len(panel["buttons"])

    fixture_id, home_team_id, away_team_id = fixture_row
    written, unmatched, unparsed = 0, 0, 0

    for button in panel["buttons"]:
        parsed = parse_button(button.get("label"), base_market)
        if parsed is None:
            unparsed += 1
            continue
        player_name, market = parsed
        player_id = resolve_player_id(cur, player_name, (home_team_id, away_team_id))
        if player_id is None:
            unmatched += 1
            continue
        decimal_odds = fractional_to_decimal(button.get("text"))
        if decimal_odds is None:
            continue
        implied_prob = round(1.0 / decimal_odds, 4)
        cur.execute(
            """
            insert into player_market_odds (player_id, fixture_id, market, value, source, captured_at)
            values (%s, %s, %s, %s, 'spreadex', now())
            """,
            (player_id, fixture_id, market, implied_prob),
        )
        written += 1

    return written, unmatched, unparsed


def main():
    from playwright.sync_api import sync_playwright

    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        fixture_cache = {}
        seen_headers = set()
        totals = {"written": 0, "unmatched": 0, "unparsed": 0, "no_fixture": 0}

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)

            for tab_name in TABS:
                try:
                    click_tab_and_expand(page, tab_name)
                except Exception as e:
                    print(f"  [tab failed] {tab_name}: {e}")
                    continue

                panels = page.evaluate(EXTRACT_TAB_JS)
                tab_written = 0
                tab_buttons = sum(len(p["buttons"]) for p in panels)
                for panel in panels:
                    written, unmatched, unparsed = import_panel(cur, panel, fixture_cache, seen_headers)
                    tab_written += written
                    totals["written"] += written
                    totals["unmatched"] += unmatched
                    totals["unparsed"] += unparsed
                    if written == 0 and unmatched == 0 and unparsed > 0:
                        totals["no_fixture"] += 1
                print(f"  {tab_name}: {len(panels)} panels, {tab_buttons} buttons seen, {tab_written} odds rows written")
                conn.commit()
                time.sleep(1)  # real courtesy delay - a live retail site, not a versioned API

            browser.close()

        print(
            f"\nDone: {totals['written']} player_market_odds rows written, "
            f"{totals['unmatched']} unmatched player name(s), {totals['unparsed']} unrecognised label(s)."
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
