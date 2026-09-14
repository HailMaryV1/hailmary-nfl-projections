"""
api_sports_feature_engineering.py
------------------------------------
Builds real candidate opportunity features from the API-Sports historical
backfill (migrations 0016/0017), for every currently-tracked offensive
player (QB/RB/WR/TE), across every real regular-season game found
(2022-2025 backfill + 2026 GW1). Read-only, diagnostic only - does NOT
train, tune, or touch the live projection model in any way.

Per-game rate stats (computed only where the real denominator is present
and non-zero - never divided by zero, never fabricated):
  receptions_per_target, yards_per_target, yards_per_carry,
  passing_yards_per_attempt, td_per_opportunity (position-specific
  denominator - pass_attempts for QB, rush_attempts for RB,
  targets for WR/TE), interceptions_per_pass_attempt,
  target_share / carry_share (player's real count / real team total for
  that game, from api_sports_team_game_stats - a real approximation for
  target_share specifically, since team pass_attempts is used as a proxy
  for "team's real total targets" - close in practice but not identical,
  noted here rather than presented as exact).

Rolling/expanding/EWM opportunity - computed on each position's own real
PRIMARY opportunity stat (QB: pass_attempts, RB: rush_attempts, WR/TE:
targets), using only that player's own real prior games in strict
chronological order (never including the current game - no lookahead,
same discipline as this session's own D/ST Form fix):
  roll3_opportunity, roll5_opportunity (simple trailing mean),
  season_opportunity (expanding mean, current season only),
  ewm_opportunity (exponentially weighted mean, alpha=0.3, real decay -
  chosen as a reasonable default, not fit/tuned against anything).

Role stability/volatility - one row per player (not per game): real
coefficient of variation (stdev / mean) of the player's own primary
opportunity stat across their own full available real game log. Lower =
more stable role; higher = more volatile usage. Reported alongside n
(games) - a volatility number from very few games deserves the same
small-sample caution this project's Accuracy page already applies.

Outputs two real CSVs (not committed - diagnostic artifacts):
  api_sports_features_by_game.csv   - one row per (player, real game)
  api_sports_role_volatility.csv    - one row per player (stability score)

RUN:
    python scripts/api_sports_feature_engineering.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402

POSITION_LABEL = {"quarterback": "QB", "running_back": "RB", "wide_receiver": "WR", "tight_end": "TE"}
PRIMARY_STAT = {"quarterback": "pass_attempts", "running_back": "rush_attempts", "wide_receiver": "targets", "tight_end": "targets"}
EWM_ALPHA = 0.3


def week_sort_key(week_label):
    try:
        return int(week_label.replace("Week", "").strip())
    except ValueError:
        return 99  # any non-"Week N" label (shouldn't occur - Regular Season only) sorts last


def safe_div(n, d):
    if n is None or d is None or d == 0:
        return None
    return n / d


def load_rows(cur):
    cur.execute(
        """
        select
            p.id as player_id, p.full_name, p.position,
            g.season, g.week, g.api_sports_game_id,
            a.pass_attempts, a.pass_completions, a.pass_yards, a.pass_td, a.interceptions_thrown,
            a.rush_attempts, a.rush_yards, a.rush_td,
            a.targets, a.receptions, a.receiving_yards, a.receiving_td,
            t.pass_attempts as team_pass_attempts, t.rush_attempts as team_rush_attempts
        from api_sports_player_game_stats a
        join players p on p.id = a.our_player_id
        join api_sports_games g on g.id = a.api_sports_game_id
        left join api_sports_team_game_stats t on t.api_sports_game_id = a.api_sports_game_id and t.team_name = a.team_name
        where p.position in ('quarterback','running_back','wide_receiver','tight_end')
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        r["_week_num"] = week_sort_key(r["week"])
    rows.sort(key=lambda r: (r["player_id"], r["season"], r["_week_num"]))
    return rows


def build_game_features(rows):
    out = []
    by_player = {}
    for r in rows:
        by_player.setdefault(r["player_id"], []).append(r)

    for player_id, games in by_player.items():
        pos = games[0]["position"]
        primary = PRIMARY_STAT[pos]
        history_all, history_season = [], {}

        for r in games:
            season = r["season"]
            history_season.setdefault(season, [])

            roll3 = sum(history_all[-3:]) / len(history_all[-3:]) if history_all else None
            roll5 = sum(history_all[-5:]) / len(history_all[-5:]) if history_all else None
            season_hist = history_season[season]
            season_opp = sum(season_hist) / len(season_hist) if season_hist else None
            if history_all:
                ewm = history_all[0]
                for v in history_all[1:]:
                    ewm = EWM_ALPHA * v + (1 - EWM_ALPHA) * ewm
            else:
                ewm = None

            row = {
                "player": r["full_name"], "position": POSITION_LABEL[pos], "season": season, "week": r["week"],
                "targets": r["targets"], "receptions": r["receptions"], "receiving_yards": r["receiving_yards"], "receiving_td": r["receiving_td"],
                "rush_attempts": r["rush_attempts"], "rush_yards": r["rush_yards"], "rush_td": r["rush_td"],
                "pass_attempts": r["pass_attempts"], "pass_completions": r["pass_completions"], "pass_yards": r["pass_yards"],
                "pass_td": r["pass_td"], "interceptions_thrown": r["interceptions_thrown"],
                "receptions_per_target": safe_div(r["receptions"], r["targets"]),
                "yards_per_target": safe_div(r["receiving_yards"], r["targets"]),
                "yards_per_carry": safe_div(r["rush_yards"], r["rush_attempts"]),
                "passing_yards_per_attempt": safe_div(r["pass_yards"], r["pass_attempts"]),
                "interceptions_per_pass_attempt": safe_div(r["interceptions_thrown"], r["pass_attempts"]),
                "td_per_opportunity": safe_div(
                    r["pass_td"] if pos == "quarterback" else (r["rush_td"] if pos == "running_back" else r["receiving_td"]),
                    r.get(primary),
                ),
                "target_share": safe_div(r["targets"], r["team_pass_attempts"]),
                "carry_share": safe_div(r["rush_attempts"], r["team_rush_attempts"]),
                "roll3_opportunity": round(roll3, 2) if roll3 is not None else None,
                "roll5_opportunity": round(roll5, 2) if roll5 is not None else None,
                "season_opportunity": round(season_opp, 2) if season_opp is not None else None,
                "ewm_opportunity": round(ewm, 2) if ewm is not None else None,
                "primary_opportunity_stat": primary,
                "primary_opportunity_value": r.get(primary),
            }
            out.append(row)

            val = r.get(primary)
            if val is not None:
                history_all.append(val)
                history_season[season].append(val)
    return out


def build_volatility(rows):
    by_player = {}
    for r in rows:
        by_player.setdefault(r["player_id"], {"name": r["full_name"], "position": r["position"], "values": []})
        primary = PRIMARY_STAT[r["position"]]
        val = r.get(primary)
        if val is not None:
            by_player[r["player_id"]]["values"].append(val)

    out = []
    for player_id, info in by_player.items():
        values = info["values"]
        n = len(values)
        if n < 2:
            out.append({"player": info["name"], "position": POSITION_LABEL[info["position"]], "n_games": n, "mean_opportunity": values[0] if values else None, "stdev": None, "coefficient_of_variation": None})
            continue
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        stdev = variance ** 0.5
        cv = (stdev / mean) if mean > 0 else None
        out.append({"player": info["name"], "position": POSITION_LABEL[info["position"]], "n_games": n, "mean_opportunity": round(mean, 2), "stdev": round(stdev, 2), "coefficient_of_variation": round(cv, 3) if cv is not None else None})
    out.sort(key=lambda r: (r["coefficient_of_variation"] is None, -(r["coefficient_of_variation"] or 0)))
    return out


def main():
    conn = db_connect()
    cur = conn.cursor()
    try:
        rows = load_rows(cur)
        print(f"Loaded {len(rows)} real (player, game) rows across {len(set(r['player_id'] for r in rows))} distinct offensive players.")

        game_features = build_game_features(rows)
        out1 = ROOT / "api_sports_features_by_game.csv"
        with out1.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(game_features[0].keys()))
            writer.writeheader()
            writer.writerows(game_features)
        print(f"Per-game feature dataset -> {out1} ({len(game_features)} rows)")

        volatility = build_volatility(rows)
        out2 = ROOT / "api_sports_role_volatility.csv"
        with out2.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(volatility[0].keys()))
            writer.writeheader()
            writer.writerows(volatility)
        print(f"Role volatility dataset -> {out2} ({len(volatility)} players)")

        print("\n=== Most VOLATILE roles (highest coefficient of variation, n>=8 real games) ===")
        shown = 0
        for row in volatility:
            if row["n_games"] >= 8 and row["coefficient_of_variation"] is not None:
                print(f"  {row['player']} ({row['position']}): CV={row['coefficient_of_variation']}, mean={row['mean_opportunity']}, n={row['n_games']}")
                shown += 1
                if shown >= 15:
                    break

        print("\n=== Most STABLE roles (lowest coefficient of variation, n>=8 real games) ===")
        stable_sorted = sorted([r for r in volatility if r["n_games"] >= 8 and r["coefficient_of_variation"] is not None], key=lambda r: r["coefficient_of_variation"])
        for row in stable_sorted[:15]:
            print(f"  {row['player']} ({row['position']}): CV={row['coefficient_of_variation']}, mean={row['mean_opportunity']}, n={row['n_games']}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
