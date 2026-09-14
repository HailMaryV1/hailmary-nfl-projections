"""
opportunity_v2_features.py
------------------------------
Real, no-lookahead opportunity features from the API-Sports historical
backfill (2022-2025) + 2026 GW1 - diagnostic/research only. Does NOT read
or write projections/predictions_and_actuals/player_stats. Every feature
for a given (player, game) row is built using ONLY that player's/team's
own real games strictly BEFORE that game, in full (season, week)
chronological order across season boundaries (so a Week 1 game correctly
draws on the end of the PRIOR real season, exactly the case that matters
most for 2026 GW1 - the one game with zero same-season history by
definition). GW1 2026's own outcomes are never used to build features for
ANY row, including other 2026 rows - the loop only ever looks backward.

Scope decisions, stated plainly rather than silently assumed:
  - "Meaningful usage" (for consecutive-usage streaks) is defined here as:
    QB pass_attempts >= 10; RB rush_attempts >= 5 OR targets >= 2;
    WR/TE targets >= 2. A real, reasonable threshold, not a measured one.
  - Team rolling context uses a single roll5 window (cross-season
    chronological, same no-lookahead rule) plus season-to-date - not the
    full last-1/3/5 treatment player features get, to keep scope real and
    finishable; team ROLE is secondary context here, not the main object
    of study.
  - Player shares use matching windows (roll5 target share = player's
    roll5 targets / team's roll5 pass attempts) - never divides by a
    missing/zero denominator; left null rather than fabricated.
  - History group is evaluated AS OF each game (games_played counts only
    real STRICTLY PRIOR games) - the same player can be "none" for their
    first tracked game and "established" by their tenth.

RUN:
    python scripts/opportunity_v2_features.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402

POSITION_LABEL = {"quarterback": "QB", "running_back": "RB", "wide_receiver": "WR", "tight_end": "TE"}
EWM_ALPHA = 0.3
MEANINGFUL_USAGE = {
    "quarterback": lambda r: (r["pass_attempts"] or 0) >= 10,
    "running_back": lambda r: (r["rush_attempts"] or 0) >= 5 or (r["targets"] or 0) >= 2,
    "wide_receiver": lambda r: (r["targets"] or 0) >= 2,
    "tight_end": lambda r: (r["targets"] or 0) >= 2,
}


def week_sort_key(week_label):
    try:
        return int(week_label.replace("Week", "").strip())
    except ValueError:
        return 99


def mean(vals):
    return sum(vals) / len(vals) if vals else None


def stdev(vals):
    if len(vals) < 2:
        return None
    m = mean(vals)
    return (sum((v - m) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5


def ewm(vals):
    if not vals:
        return None
    e = vals[0]
    for v in vals[1:]:
        e = EWM_ALPHA * v + (1 - EWM_ALPHA) * e
    return e


def safe_div(n, d):
    if n is None or d is None or d == 0:
        return None
    return n / d


def load_player_rows(cur):
    cur.execute(
        """
        select
            p.id as player_id, p.full_name, p.position, a.team_name,
            g.season, g.week, g.api_sports_game_id,
            a.pass_attempts, a.pass_completions, a.pass_yards, a.pass_td, a.interceptions_thrown,
            a.rush_attempts, a.rush_yards, a.rush_td,
            a.targets, a.receptions, a.receiving_yards, a.receiving_td
        from api_sports_player_game_stats a
        join players p on p.id = a.our_player_id
        join api_sports_games g on g.id = a.api_sports_game_id
        where p.position in ('quarterback','running_back','wide_receiver','tight_end')
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        r["_week_num"] = week_sort_key(r["week"])
    rows.sort(key=lambda r: (r["player_id"], r["season"], r["_week_num"]))
    return rows


def load_team_rows(cur):
    cur.execute(
        """
        select t.team_name, g.season, g.week, g.api_sports_game_id,
               t.offensive_plays, t.pass_attempts, t.rush_attempts, t.pass_yards, t.rush_yards
        from api_sports_team_game_stats t
        join api_sports_games g on g.id = t.api_sports_game_id
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        r["_week_num"] = week_sort_key(r["week"])
    rows.sort(key=lambda r: (r["team_name"], r["season"], r["_week_num"]))
    return rows


def build_team_rolling(team_rows):
    """team_name, game_id -> {roll5 fields, season-to-date fields}, using only strictly-prior real games."""
    out = {}
    history_all = {}
    history_season = {}
    for r in team_rows:
        team = r["team_name"]
        history_all.setdefault(team, [])
        history_season.setdefault((team, r["season"]), [])
        prior_all = history_all[team][-5:]
        prior_season = history_season[(team, r["season"])]

        def avg_field(hist, field):
            vals = [h[field] for h in hist if h.get(field) is not None]
            return mean(vals)

        out[(team, r["api_sports_game_id"])] = {
            "team_roll5_plays": avg_field(prior_all, "offensive_plays"),
            "team_roll5_pass_attempts": avg_field(prior_all, "pass_attempts"),
            "team_roll5_rush_attempts": avg_field(prior_all, "rush_attempts"),
            "team_roll5_pass_yards": avg_field(prior_all, "pass_yards"),
            "team_roll5_rush_yards": avg_field(prior_all, "rush_yards"),
            "team_season_plays": avg_field(prior_season, "offensive_plays"),
            "team_season_pass_attempts": avg_field(prior_season, "pass_attempts"),
            "team_season_rush_attempts": avg_field(prior_season, "rush_attempts"),
        }
        snap = {"offensive_plays": r["offensive_plays"], "pass_attempts": r["pass_attempts"], "rush_attempts": r["rush_attempts"], "pass_yards": r["pass_yards"], "rush_yards": r["rush_yards"]}
        history_all[team].append(snap)
        history_season[(team, r["season"])].append(snap)
    return out


def history_group(games_played):
    if games_played == 0:
        return "none"
    if games_played < 8:
        return "limited"
    return "established"


def build_player_features(player_rows, team_rolling):
    out = []
    by_player = {}
    for r in player_rows:
        by_player.setdefault(r["player_id"], []).append(r)

    for player_id, games in by_player.items():
        pos = games[0]["position"]
        opp_stats = ["pass_attempts"] if pos == "quarterback" else (["rush_attempts", "targets"] if pos == "running_back" else ["targets"])
        secondary = {
            "quarterback": ["pass_completions", "pass_yards", "pass_td", "interceptions_thrown", "rush_attempts", "rush_yards", "rush_td"],
            "running_back": ["rush_yards", "receptions", "receiving_yards"],
            "wide_receiver": ["receptions", "receiving_yards"],
            "tight_end": ["receptions", "receiving_yards"],
        }[pos]

        hist_all = {s: [] for s in opp_stats + secondary}
        hist_season = {}
        consecutive_meaningful = 0

        for r in games:
            season = r["season"]
            hist_season.setdefault(season, {s: [] for s in opp_stats + secondary})
            games_played = len(hist_all[opp_stats[0]])

            row = {
                "player": r["full_name"], "position": POSITION_LABEL[pos], "team": r["team_name"],
                "season": season, "week": r["week"], "api_sports_game_id": r["api_sports_game_id"],
                "games_played_prior": games_played, "history_group": history_group(games_played),
                "consecutive_meaningful_usage_prior": consecutive_meaningful,
                # Real actual outcome THIS game - the prediction target, never used to build this row's own features.
                "actual_pass_attempts": r["pass_attempts"], "actual_rush_attempts": r["rush_attempts"], "actual_targets": r["targets"],
            }

            for stat in opp_stats:
                h = hist_all[stat]
                row[f"{stat}_last1"] = h[-1] if h else None
                row[f"{stat}_roll3"] = mean(h[-3:]) if h else None
                row[f"{stat}_roll5"] = mean(h[-5:]) if h else None
                row[f"{stat}_season_avg"] = mean(hist_season[season][stat]) if hist_season[season][stat] else None
                row[f"{stat}_ewm"] = ewm(h) if h else None
                row[f"{stat}_stdev"] = stdev(h) if h else None
                cv = safe_div(row[f"{stat}_stdev"], mean(h)) if h else None
                row[f"{stat}_cv"] = cv
                roll3, season_avg = row[f"{stat}_roll3"], row[f"{stat}_season_avg"]
                row[f"{stat}_role_change_abs"] = (roll3 - season_avg) if (roll3 is not None and season_avg is not None) else None
                row[f"{stat}_role_change_ratio"] = safe_div(roll3, season_avg)

            for stat in secondary:
                h = hist_all[stat]
                row[f"{stat}_season_avg"] = mean(hist_season[season][stat]) if hist_season[season][stat] else None

            team_ctx = team_rolling.get((r["team_name"], r["api_sports_game_id"]), {})
            row.update(team_ctx)
            if pos in ("wide_receiver", "tight_end", "running_back"):
                row["target_share_roll5"] = safe_div(row.get("targets_roll5"), team_ctx.get("team_roll5_pass_attempts"))
            if pos == "running_back":
                row["carry_share_roll5"] = safe_div(row.get("rush_attempts_roll5"), team_ctx.get("team_roll5_rush_attempts"))
                row["rush_plus_target_opportunities_roll5"] = (row.get("rush_attempts_roll5") or 0) + (row.get("targets_roll5") or 0) if (row.get("rush_attempts_roll5") is not None or row.get("targets_roll5") is not None) else None
            if pos in ("wide_receiver", "tight_end"):
                row["catch_rate_season"] = safe_div(row.get("receptions_season_avg"), row.get("targets_season_avg"))
                row["yards_per_target_season"] = safe_div(row.get("receiving_yards_season_avg"), row.get("targets_season_avg"))

            out.append(row)

            # Update history AFTER emitting this row's features - no lookahead.
            for stat in opp_stats + secondary:
                v = r.get(stat)
                if v is not None:
                    hist_all[stat].append(v)
                    hist_season[season][stat].append(v)
            if MEANINGFUL_USAGE[pos](r):
                consecutive_meaningful += 1
            else:
                consecutive_meaningful = 0

    return out


def main():
    conn = db_connect()
    cur = conn.cursor()
    try:
        player_rows = load_player_rows(cur)
        team_rows = load_team_rows(cur)
        print(f"Loaded {len(player_rows)} real player-game rows, {len(team_rows)} real team-game rows.")

        team_rolling = build_team_rolling(team_rows)
        features = build_player_features(player_rows, team_rolling)

        out_path = ROOT / "opportunity_v2_features.csv"
        # Different positions compute different column sets (QB gets
        # pass_attempts_*, RB gets both rush_attempts_* and targets_*,
        # etc.) - union of all real keys seen, first-seen order preserved,
        # not just the first row's own keys.
        fieldnames = list(dict.fromkeys(k for row in features for k in row.keys()))
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
            writer.writeheader()
            writer.writerows(features)
        print(f"-> {out_path} ({len(features)} rows, {len(fieldnames)} columns)")

        from collections import Counter
        print("\nHistory group distribution (as of each game):")
        print(Counter(r["history_group"] for r in features))
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
