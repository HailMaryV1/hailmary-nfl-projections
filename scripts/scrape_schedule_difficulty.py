"""
scrape_schedule_difficulty.py
--------------------------------
Real full-season (18-week) matchup + difficulty data from Sharp Football
Analysis's Strength of Schedule tool. Found after the user asked about
planning multiple weeks ahead - confirmed live 2026-09-08 this closes two
real gaps: no fixture/bye data past the current gameweek, and zero Fixture
Quality signal for offense (only defense_special had one, via the real
points-allowed work).

The tool itself lives on a separate Cloudflare Worker
(sfa-strength-of-schedule.raymondsummerlin.workers.dev), embedded via
iframe on the parent article page - plain vanilla JS (`#sos-app`, real
`<select id="f-team">`), no bot-protection cookies observed, confirmed
live with a direct Playwright test.

Real per-team chart structure, confirmed live by direct SVG inspection:
every real SVG `<text>` node in `#panel-bar svg` for a given week shares
the SAME rounded x-coordinate across four parallel series - the win-total
value ("10.2"), the opponent abbreviation ("SEA"), the home/away letter
("H"/"A"), and the week-axis number ("1".."18") - except on a real bye
week, where only the week number (+ a "BYE" label at a different y) exists
at that x, with no win/opponent/home-away text at all. Grouping by x is
what makes this reliable - reading rows top-to-bottom as flattened text
would have silently misaligned the real bye-week position.

RUN:
    python scripts/scrape_schedule_difficulty.py
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://sfa-strength-of-schedule.raymondsummerlin.workers.dev/"
RAW_OUT = Path(__file__).resolve().parent.parent / "schedule_difficulty_raw.json"

EXTRACT_JS = """
() => {
  const svg = document.querySelector('#panel-bar svg');
  if (!svg) return [];
  const texts = [...svg.querySelectorAll('text')].map(t => ({
    x: Math.round(parseFloat(t.getAttribute('x'))),
    text: t.textContent.trim(),
  }));
  const groups = {};
  for (const t of texts) {
    if (t.text === 'WINS' || t.text === 'Wk') continue;
    groups[t.x] = groups[t.x] || {};
    if (t.text === 'BYE') groups[t.x].isBye = true;
    else if (/^\\d+\\.\\d+$/.test(t.text)) groups[t.x].winsValue = parseFloat(t.text);
    else if (/^[AH]$/.test(t.text)) groups[t.x].homeAway = t.text;
    else if (/^\\d+$/.test(t.text)) groups[t.x].week = parseInt(t.text, 10);
    else if (/^[A-Z]{2,4}$/.test(t.text)) groups[t.x].opponentAbbr = t.text;
  }
  return Object.values(groups)
    .filter(g => g.week && (g.opponentAbbr || g.isBye))
    .sort((a, b) => a.week - b.week);
}
"""


def get_team_names(page):
    return page.eval_on_selector_all("#f-team option", "els => els.map(e => e.value)")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1000)

        teams = get_team_names(page)
        print(f"{len(teams)} real teams found in the tool's own dropdown")

        results = []
        for team in teams:
            page.select_option("#f-team", team)
            page.wait_for_timeout(600)
            weeks = page.evaluate(EXTRACT_JS)
            results.append({"team": team, "weeks": weeks})
            print(f"  {team}: {len(weeks)} weeks")

        browser.close()

    RAW_OUT.write_text(json.dumps(results, indent=2))
    print(f"\n{len(results)} teams -> {RAW_OUT}")


if __name__ == "__main__":
    main()
