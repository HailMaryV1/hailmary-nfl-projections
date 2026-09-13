"""
slice_jerseys.py
-------------------
Slices assets/jersey_sheet.png - a single real image the user provided
with a generic jersey for all 32 NFL teams, 8 columns x 4 rows, each cell
1536/8=192px wide x 1024/4=256px tall - into one PNG per team at
frontend/public/jerseys/{ABBR}.png, matching this project's own real
teams.abbr values exactly (confirmed live against the database, not
guessed - e.g. "GB" and "SF" and "LV", not "GNB"/"SFO"/"LVR").

Crops to 190px tall (not the full 256px cell) to exclude the team-name
caption printed under each jersey in the source sheet - confirmed live by
inspection that every row's jersey art sits clear of that line at 190px,
even though the caption's own start position isn't perfectly uniform
row-to-row (an AI-generated sheet, not an engineered sprite grid).

RUN:
    python scripts/slice_jerseys.py
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHEET = ROOT / "assets" / "jersey_sheet.png"
OUT_DIR = ROOT / "frontend" / "public" / "jerseys"

CELL_W, CELL_H = 192, 256
CROP_H = 190

ROWS = [
    ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE"],
    ["DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC"],
    ["LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG"],
    ["NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS"],
]


def main():
    img = Image.open(SHEET)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for r, abbrs in enumerate(ROWS):
        for c, abbr in enumerate(abbrs):
            x0, y0 = c * CELL_W, r * CELL_H
            cell = img.crop((x0, y0, x0 + CELL_W, y0 + CROP_H))
            cell.save(OUT_DIR / f"{abbr}.png")
            count += 1
    print(f"Sliced {count} jerseys -> {OUT_DIR}")


if __name__ == "__main__":
    main()
