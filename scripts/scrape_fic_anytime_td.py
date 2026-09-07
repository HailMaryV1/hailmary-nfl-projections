"""
scrape_fic_anytime_td.py
---------------------------
Real, live "Score Any TD" prop odds from fantasyinfocentral.com - found
after Oddschecker and Midnite (both real, live anytime-TD markets)
actively Cloudflare/AWS-WAF-blocked a standard headless browser (confirmed
live 2026-09-07), and a historical-rate site (jedibets.com) was correctly
rejected as not being real odds at all (see docs/data-and-weights.md for
the full trail). This site displays a real, live Caesars sportsbook line
(confirmed live - every row's bookmaker logo/title reads "Caesars") as
editorial content, has no bot-protection cookies, and works cleanly with
plain Playwright.

One page load covers every real Week 1 fixture - no per-fixture navigation
needed (confirmed live: 106 rows across all 16 games on one "All Games"
table). Real, clean DOM: player name + position in column 1, both real
team abbreviations via the row's own `.team` span classes (first = away,
second carries an extra "after" class = home), a real American-odds price
in `.mline`, and the site's own "Proj" expected-TD-count column (NOT
stored - this project derives its own expected count from the real odds,
via the same Poisson anytime-count formula used for passing_touchdowns
elsewhere in this project, for methodological consistency across sources
rather than trusting a second, unverifiable model).

RUN:
    python scripts/scrape_fic_anytime_td.py
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://www.fantasyinfocentral.com/betting/nfl/props/score-anytime-td"
RAW_OUT = Path(__file__).resolve().parent.parent / "fic_anytime_td_raw.json"

EXTRACT_JS = """
() => {
  const rows = [...document.querySelectorAll('table tbody tr')];
  return rows.map(tr => {
    const nameLink = tr.querySelector('td:nth-child(1) a');
    const name = nameLink ? nameLink.textContent.trim() : null;
    const pos = tr.querySelector('.pos')?.textContent.trim() || null;
    const teamSpans = [...tr.querySelectorAll('.game_row .team')];
    const abbrOf = span => [...span.classList].find(c => c !== 'team' && c !== 'after') || null;
    const away = teamSpans[0] ? abbrOf(teamSpans[0]) : null;
    const home = teamSpans[1] ? abbrOf(teamSpans[1]) : null;
    const mline = tr.querySelector('.mline')?.childNodes[0]?.textContent.trim() || null;
    const bookmaker = tr.querySelector('.tdbklgo')?.getAttribute('title') || null;
    return { name, pos, away, home, mline, bookmaker };
  }).filter(r => r.name && r.away && r.home && r.mline);
}
"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        rows = page.evaluate(EXTRACT_JS)
        browser.close()

    if not rows:
        raise SystemExit("No rows parsed - page structure may have changed.")

    RAW_OUT.write_text(json.dumps(rows, indent=2))
    print(f"{len(rows)} real anytime-TD prop rows -> {RAW_OUT}")


if __name__ == "__main__":
    main()
