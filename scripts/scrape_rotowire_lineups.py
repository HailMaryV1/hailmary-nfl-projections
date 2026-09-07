"""
scrape_rotowire_lineups.py
----------------------------
Scrapes RotoWire's real NFL starting-lineups page: per-fixture starters/
inactives with real per-player status ("Q" etc.), real game odds (spread/
moneyline/O-U) and real weather. DOM structure confirmed live 2026-09-07
via manual inspection (see docs/data-and-weights.md) - one `.lineup.is-nfl`
wrapper per real fixture, containing `.lineup__box` (teams/players/odds/
weather).

Real Cloudflare Bot Management + reCAPTCHA cookies are present on this site
(confirmed live) - this scraper uses a real browser (Playwright) rather than
a plain HTTP request, and should be run at a modest cadence (a few times a
day), never tight polling.

RUN:
    python scripts/scrape_rotowire_lineups.py
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://www.rotowire.com/football/lineups.php/1000"
RAW_OUT = Path(__file__).resolve().parent.parent / "rotowire_lineups_raw.json"

EXTRACT_JS = """
() => {
  function extractList(ul){
    if (!ul) return [];
    return Array.from(ul.querySelectorAll('li')).map(li => {
      if (li.classList.contains('lineup__no')) return {placeholder: true};
      const pos = li.querySelector('.lineup__pos')?.textContent.trim();
      const a = li.querySelector('a');
      const name = a?.textContent.trim();
      const title = a?.getAttribute('title');
      const span = li.querySelector('span');
      const statusText = span ? span.textContent.trim() : '';
      return {placeholder: false, pos, name, title, statusText};
    });
  }

  function extractGame(wrap){
    const box = wrap.querySelector('.lineup__box');
    if (!box) return null;
    const abbrVisit = box.querySelector('.lineup__team.is-visit .lineup__abbr')?.textContent.trim();
    const abbrHome = box.querySelector('.lineup__team.is-home .lineup__abbr')?.textContent.trim();

    const mains = box.querySelectorAll('.lineup__main');
    const startersMain = mains[0];
    const inactivesMain = mains[1];

    const weatherEl = box.querySelector('.lineup__weather');
    const isDome = weatherEl ? /dome/i.test(weatherEl.querySelector('.lineup__weather-icon')?.getAttribute('src') || '') : false;
    const weatherBold = weatherEl?.querySelector('b')?.textContent.trim() || null;
    const weatherFullText = weatherEl?.querySelector('.lineup__weather-text')?.textContent.trim() || null;

    const oddsItems = Array.from(box.querySelectorAll('.lineup__odds-item')).map(d => {
      const label = d.querySelector('b')?.textContent.trim();
      const full = d.textContent.trim();
      return {label, value: full.replace(label, '').trim()};
    });

    return {
      abbrVisit, abbrHome,
      startersVisit: extractList(startersMain?.querySelector('.lineup__list.is-visit')),
      startersHome: extractList(startersMain?.querySelector('.lineup__list.is-home')),
      inactivesVisit: extractList(inactivesMain?.querySelector('.lineup__list.is-visit')),
      inactivesHome: extractList(inactivesMain?.querySelector('.lineup__list.is-home')),
      isDome, weatherBold, weatherFullText, oddsItems,
    };
  }

  return Array.from(document.querySelectorAll('.lineup.is-nfl')).map(extractGame).filter(Boolean);
}
"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(1500)
        games = page.evaluate(EXTRACT_JS)
        browser.close()

    if not games:
        raise SystemExit("No games found on RotoWire lineups page - page structure may have changed.")

    RAW_OUT.write_text(json.dumps(games, indent=2))
    print(f"  {len(games)} games -> {RAW_OUT}")


if __name__ == "__main__":
    main()
