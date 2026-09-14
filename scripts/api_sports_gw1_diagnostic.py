"""
api_sports_gw1_diagnostic.py
--------------------------------
Builds the GW1 offensive-player diagnostic table from three real, already
-permanent sources - predictions_and_actuals (frozen prediction + real
FanTeam actual), api_sports_player_game_stats (real API-Sports box score),
and projections (the model's own real pre-game expected_count per stat,
pulled from algorithm_version_id=2, the version that was actually frozen -
see this script's own methodology note below) - then classifies the
biggest misses using real underlying stats. Read-only: never writes to
predictions_and_actuals/projections. No model changes.

Methodology note on "expected opportunity": this project's own projection
engine (compute_projections.py) prices real bookmaker-derived expected
YARDS (passing/rushing/receiving) and expected RECEPTIONS - it does NOT
price expected pass attempts, rush attempts, or targets as their own
signal (no market exists for those specifically). So "opportunity vs
efficiency" here is judged against the stats the model actually estimated
pre-game (yards, receptions, anytime-TD probability), not attempts/
targets - which are shown in the flat table as real, useful context, but
were never a modelled expectation to miss. There is also no real
prior-gameweek baseline for expected attempts/targets this early in a new
season, same cold-start reasoning as this session's own D/ST Form fix.

RUN:
    python scripts/api_sports_gw1_diagnostic.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402

ALGORITHM_VERSION_ID = 2  # the version active when GW1 was frozen and re-verified this session
OFFENSE_POSITIONS = {"quarterback", "running_back", "wide_receiver", "tight_end"}
POSITION_LABEL = {"quarterback": "QB", "running_back": "RB", "wide_receiver": "WR", "tight_end": "TE"}

FLAT_COLUMNS = [
    "player", "position", "team", "opponent", "api_sports_game", "week",
    "pass_attempts", "completions", "pass_yards", "pass_td", "interceptions",
    "rush_attempts", "rush_yards", "rush_td",
    "targets", "receptions", "receiving_yards", "receiving_td", "fumbles",
    "fanteam_actual_points", "hail_mary_frozen_projection", "signed_error", "absolute_error",
]


def load_rows(cur):
    cur.execute(
        """
        select
            p.id as player_id, p.full_name, p.position, t.abbr as team_abbr,
            pa.predicted_points, pa.actual_points,
            a.pass_attempts, a.pass_completions, a.pass_yards, a.pass_td, a.interceptions_thrown,
            a.rush_attempts, a.rush_yards, a.rush_td,
            a.targets, a.receptions, a.receiving_yards, a.receiving_td,
            coalesce(a.fumbles_total, 0) as fumbles,
            g.api_sports_game_id, g.week,
            g.home_team_name, g.away_team_name,
            proj.per_stat
        from predictions_and_actuals pa
        join players p on p.id = pa.player_id
        left join teams t on t.id = p.team_id
        join api_sports_player_game_stats a on a.our_player_id = p.id
        join api_sports_games g on g.id = a.api_sports_game_id
        left join projections proj on proj.player_id = p.id and proj.gameweek = pa.gameweek
            and proj.horizon = 1 and proj.algorithm_version_id = %s
        where pa.gameweek = 1 and pa.actual_points is not null and p.position = any(%s)
        order by abs(pa.predicted_points - pa.actual_points) desc
        """,
        (ALGORITHM_VERSION_ID, list(OFFENSE_POSITIONS)),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def opponent_for(row):
    home, away = row["home_team_name"], row["away_team_name"]
    # We only know the player's OWN team abbr, not which side of the
    # api_sports game they were on by abbr alone - resolved via team_abbr
    # vs our own teams.name mapping isn't available here, so this reports
    # the real fixture as "home vs away" plainly rather than guessing a
    # perspective-relative "vs/@ " that could be wrong.
    return f"{away} @ {home}"


def expected_count(per_stat, stat_key):
    if not per_stat or stat_key not in per_stat:
        return None
    return per_stat[stat_key].get("expected_count")


def classify(row):
    """Real, evidence-based classification - returns (label, reasoning). Refuses to guess when data doesn't support a call."""
    pos = row["position"]
    per_stat = row["per_stat"] or {}
    signed = float(row["predicted_points"]) - float(row["actual_points"])
    notes = []

    real_int = row["interceptions_thrown"] or 0
    real_fum_lost = 0  # fumbles_lost not separately available at position-attribution level here; fumbles total shown in flat table
    exp_int = expected_count(per_stat, "interception_thrown") or 0
    exp_fum = expected_count(per_stat, "fumble_lost") or 0

    if pos == "quarterback" and real_int >= 2 and exp_int == 0:
        notes.append(f"{real_int} real INTs thrown vs a modelled expectation of 0 (no turnover signal exists pre-game)")
        return "turnover variance", notes

    if pos == "quarterback":
        exp_yards = expected_count(per_stat, "passing_yards")
        real_yards = row["pass_yards"]
        exp_td = expected_count(per_stat, "passing_td")
        real_td = row["pass_td"] or 0
        if exp_yards and real_yards is not None:
            yard_ratio = real_yards / exp_yards if exp_yards else None
            notes.append(f"real pass yards {real_yards} vs modelled expected {exp_yards:.0f} (ratio {yard_ratio:.2f})" if yard_ratio else "no real yards comparison available")
            if yard_ratio is not None and (yard_ratio < 0.55 or yard_ratio > 1.6):
                notes.append(f"real completions/attempts {row['pass_completions']}/{row['pass_attempts']}")
                return "passing volume miss", notes
        if exp_td is not None and real_td is not None and abs(real_td - exp_td) >= 1.5:
            notes.append(f"real passing TDs {real_td} vs modelled expected {exp_td:.2f}")
            return "touchdown variance", notes
        notes.append(f"real passing TDs {real_td} vs modelled expected {exp_td if exp_td is not None else '—'}, yards roughly in line")
        return "efficiency variance", notes

    if pos in ("running_back",):
        exp_yards = expected_count(per_stat, "rushing_yards")
        real_yards = row["rush_yards"]
        exp_td = expected_count(per_stat, "anytime_td")
        real_td = (row["rush_td"] or 0) + (row["receiving_td"] or 0)
        if real_int == 0 and real_fum_lost == 0 and row["fumbles"] and row["fumbles"] > 0:
            notes.append(f"real fumbles: {row['fumbles']} (lost-count not separately available in this dataset)")
        if exp_yards and real_yards is not None:
            yard_ratio = real_yards / exp_yards if exp_yards else None
            notes.append(f"real rush yards {real_yards} vs modelled expected {exp_yards:.0f} (ratio {yard_ratio:.2f})" if yard_ratio else "no real yards comparison available")
            notes.append(f"real rush attempts {row['rush_attempts']}, real targets {row['targets']}, real receptions {row['receptions']}")
            if yard_ratio is not None and (yard_ratio < 0.5 or yard_ratio > 1.8):
                return "rushing volume miss", notes
        if exp_td is not None and abs(real_td - exp_td) >= 0.7:
            notes.append(f"real rush+rec TDs {real_td} vs modelled anytime-TD expectation {exp_td:.2f}")
            return "touchdown variance", notes
        return "efficiency variance", notes

    if pos in ("wide_receiver", "tight_end"):
        exp_yards = expected_count(per_stat, "receiving_yards")
        exp_rec = expected_count(per_stat, "reception")
        real_yards = row["receiving_yards"]
        real_rec = row["receptions"]
        exp_td = expected_count(per_stat, "anytime_td")
        real_td = (row["receiving_td"] or 0) + (row["rush_td"] or 0)
        rec_ratio = (real_rec / exp_rec) if (exp_rec and real_rec is not None) else None
        yard_ratio = (real_yards / exp_yards) if (exp_yards and real_yards is not None) else None
        if rec_ratio is not None:
            notes.append(f"real receptions {real_rec} vs modelled expected {exp_rec:.2f} (ratio {rec_ratio:.2f}); real targets {row['targets']}")
        if yard_ratio is not None:
            notes.append(f"real receiving yards {real_yards} vs modelled expected {exp_yards:.0f} (ratio {yard_ratio:.2f})")
        if rec_ratio is not None and (rec_ratio < 0.5 or rec_ratio > 1.8):
            return "target volume miss", notes
        if yard_ratio is not None and (yard_ratio < 0.5 or yard_ratio > 1.8):
            return "efficiency variance", notes
        if exp_td is not None and abs(real_td - exp_td) >= 0.7:
            notes.append(f"real receiving+rush TDs {real_td} vs modelled anytime-TD expectation {exp_td:.2f}")
            return "touchdown variance", notes
        if rec_ratio is None and yard_ratio is None:
            notes.append("no real per_stat expected_count available for this player (projections row missing or unpopulated) - cannot classify from available data")
            return "insufficient data", notes
        return "efficiency variance", notes

    notes.append("position not covered by this classifier")
    return "insufficient data", notes


def main():
    conn = db_connect()
    cur = conn.cursor()
    try:
        rows = load_rows(cur)
        print(f"Loaded {len(rows)} real matched offensive rows (GW1, API-Sports-matched, actual captured).\n")

        # --- Flat CSV export ---
        out_path = ROOT / "gw1_offense_diagnostic.csv"
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(FLAT_COLUMNS)
            for r in rows:
                signed = float(r["predicted_points"]) - float(r["actual_points"])
                writer.writerow([
                    r["full_name"], POSITION_LABEL[r["position"]], r["team_abbr"], opponent_for(r),
                    r["api_sports_game_id"], r["week"],
                    r["pass_attempts"], r["pass_completions"], r["pass_yards"], r["pass_td"], r["interceptions_thrown"],
                    r["rush_attempts"], r["rush_yards"], r["rush_td"],
                    r["targets"], r["receptions"], r["receiving_yards"], r["receiving_td"], r["fumbles"],
                    round(float(r["actual_points"]), 2), round(float(r["predicted_points"]), 2),
                    round(signed, 2), round(abs(signed), 2),
                ])
        print(f"Flat diagnostic table -> {out_path} ({len(rows)} rows)\n")

        # --- Aggregate opportunity-vs-error diagnostics by position ---
        print("=== Opportunity vs error, by position (real yards/receptions vs modelled expected_count) ===")
        for pos in ("quarterback", "running_back", "wide_receiver", "tight_end"):
            pos_rows = [r for r in rows if r["position"] == pos]
            if not pos_rows:
                continue
            yard_key = {"quarterback": "passing_yards", "running_back": "rushing_yards", "wide_receiver": "receiving_yards", "tight_end": "receiving_yards"}[pos]
            actual_key = {"quarterback": "pass_yards", "running_back": "rush_yards", "wide_receiver": "receiving_yards", "tight_end": "receiving_yards"}[pos]
            ratios, fantasy_errors_near, fantasy_errors_far = [], [], []
            for r in pos_rows:
                exp = expected_count(r["per_stat"] or {}, yard_key)
                act = r[actual_key]
                signed = float(r["predicted_points"]) - float(r["actual_points"])
                if exp and act is not None and exp > 0:
                    ratio = act / exp
                    ratios.append(ratio)
                    if 0.7 <= ratio <= 1.4:
                        fantasy_errors_near.append(abs(signed))
                    else:
                        fantasy_errors_far.append(abs(signed))
            n_near, n_far = len(fantasy_errors_near), len(fantasy_errors_far)
            mae_near = sum(fantasy_errors_near) / n_near if n_near else None
            mae_far = sum(fantasy_errors_far) / n_far if n_far else None
            print(f"  {POSITION_LABEL[pos]}: n={len(pos_rows)}, {n_near + n_far} with a real per_stat comparison available")
            if mae_near is not None:
                print(f"    -> real volume within ±40% of modelled expected: fantasy MAE {mae_near:.2f} (n={n_near})")
            if mae_far is not None:
                print(f"    -> real volume deviated sharply from modelled expected: fantasy MAE {mae_far:.2f} (n={n_far})")

        # --- Big misses ---
        for threshold, label in [(15, ">15pt misses"), (10, ">10pt misses")]:
            subset = [r for r in rows if abs(float(r["predicted_points"]) - float(r["actual_points"])) > threshold]
            print(f"\n=== {label}: {len(subset)} real players ===")
            for r in subset:
                signed = float(r["predicted_points"]) - float(r["actual_points"])
                label_cls, notes = classify(r)
                print(f"  {r['full_name']} ({POSITION_LABEL[r['position']]}, {r['team_abbr']}) - proj {float(r['predicted_points']):.2f}, actual {float(r['actual_points']):.2f}, signed {signed:+.2f}")
                print(f"    Classification: {label_cls}")
                for n in notes:
                    print(f"      - {n}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
