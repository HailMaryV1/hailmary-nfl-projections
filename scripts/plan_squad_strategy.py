"""
plan_squad_strategy.py
-------------------------
One-off strategy planner for the user's real "concentrate on teams with the
best fixture runs" approach: given a handful of teams and the real gameweek
window each one looks good for (user's own read, cross-checked against real
team_schedule_difficulty data - see docs/data-and-weights.md's 2026-09-08
entry), work out a real week-by-week squad plan for the full real 18-week
season - who to roster, when to swap, whether a swap needs paying for -
against FanTeam's real rules for this tournament (confirmed live
2026-09-08): 9 total slots (QB1/RB2/WR3/TE1/FLEX1[RB-WR-TE]/DST1), no bench,
GBP140M budget, max 3 players per real team, 2 free transfers/gameweek
(bankable up to 34), -8pts per transfer beyond that.

IMPORTANT - trust FanTeam's own team tags over this assistant's own
knowledge: an early version of this script excluded a couple of names
(Kenneth Walker, A.J. Brown) as supposed "data errors" because their real
team in this assistant's own training data didn't match FanTeam's. That was
wrong to assume - a live 2026/27-season data source reflects real roster
moves (trades, free agency) this assistant has no way of knowing about from
older training data. FanTeam's team assignment is the one this script
trusts; nothing is excluded on the assistant's own say-so.

Methodology for "what would this player score in a future gameweek":
each candidate's horizon-1 (GW1) total_points already has that week's real
fixture-quality multiplier baked in (per_layer.fixture_quality). Dividing it
back out by that GW1 multiplier recovers a real "fixture-neutral" baseline
for the player (their normal level, before this specific opponent), which
is then re-multiplied by the SAME real fixture_quality_multiplier() used
throughout the engine (stat_math.py) for whatever future gameweek is being
evaluated - the identical mechanism compute_projections.py already uses for
horizons 2/3/5, just applied gameweek-by-gameweek instead of averaged over a
window. A team's real bye week zeroes that week outright.

This is a real, load-bearing simplification worth stating plainly: it holds
each player's underlying role/target-share fixed at its GW1 level for the
whole season (no in-season breakout/decline/injury modelled) - the best
available answer this early in a real season with no in-season form history
yet, not a claim of precision beyond that. The further a gameweek is from
GW1, the more this assumption is worth treating skeptically.

Transfer decisions are made by an explicit, printed greedy pass (not a
hand-typed plan, and not a hidden optimiser): every gameweek, a player whose
team is on a real bye is swapped out from a shortlist of realistic targets
first; if the shortlist can't afford a legal replacement, a real full-board
search (every eligible player in the DB, not just the shortlist) runs
automatically for whatever's still stuck. Any remaining free transfers are
then spent on the single highest real point-gain shortlist swap available,
one at a time, only if it doesn't break the GBP140M cap or the 3-per-team
cap. Every swap is printed with its reason, so the plan can be sanity-
checked line by line rather than trusted blind.

RUN:
    python scripts/plan_squad_strategy.py
"""
import sys
import statistics
import itertools
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect
from stat_math import fixture_quality_multiplier
import psycopg2.extras

BUDGET_CAP = 140.0
MAX_PER_TEAM = 3
FREE_TRANSFERS_PER_GW = 2
BANK_CAP = 34
EXTRA_TRANSFER_COST = 8
UPGRADE_THRESHOLD = 2.0  # minimum real point gain to justify spending a free transfer on a non-forced swap
SEASON_LENGTH = 18  # FanTeam's own real rule: "This tournament is played over 18 Gameweeks."
GAMEWEEKS = list(range(1, SEASON_LENGTH + 1))

# Shortlist: everyone in the GW1 squad, plus realistic later transfer
# targets for KC/SF/Rams once their real window opens (per the user's own
# team list). This is a shortlist for speed/readability, not a claim that
# it's the only real option - the full-board fallback below covers
# whatever this list misses.
CANDIDATES_BY_POSITION = {
    "quarterback": ["Lamar Jackson", "Patrick Mahomes", "Brock Purdy", "Matthew Stafford"],
    "running_back": ["Jahmyr Gibbs", "MarShawn Lloyd", "Omarion Hampton", "Christian McCaffrey", "Kyren Williams", "Kenneth Walker"],
    "wide_receiver": ["Amon-Ra St. Brown", "Zay Flowers", "Ladd McConkey", "Rashee Rice", "Mike Evans", "Puka Nacua", "Davante Adams", "A.J. Brown"],
    "tight_end": ["Isaiah Likely", "Travis Kelce", "George Kittle"],
}
DST_CANDIDATES = ["Los Angeles Chargers D/ST", "Las Vegas Raiders D/ST", "Denver Broncos D/ST"]

SLOTS = {
    "QB": {"positions": ["quarterback"]},
    "RB1": {"positions": ["running_back"]},
    "RB2": {"positions": ["running_back"]},
    "WR1": {"positions": ["wide_receiver"]},
    "WR2": {"positions": ["wide_receiver"]},
    "WR3": {"positions": ["wide_receiver"]},
    "TE": {"positions": ["tight_end"]},
    "FLEX": {"positions": ["running_back", "wide_receiver", "tight_end"]},
}

# GW1 squad, as agreed with the user - fixed starting point, not re-derived.
INITIAL_ROSTER = {
    "QB": "Lamar Jackson", "RB1": "Jahmyr Gibbs", "RB2": "MarShawn Lloyd",
    "WR1": "Amon-Ra St. Brown", "WR2": "Zay Flowers", "WR3": "Ladd McConkey",
    "TE": "Isaiah Likely", "FLEX": "Omarion Hampton",
}


def load_candidate_data(cur, algo_id, names):
    cur.execute(
        """
        select p.id, p.full_name, p.position, p.price, p.team_id, t.abbr as team_abbr,
               pr.total_points
        from players p
        join teams t on t.id = p.team_id
        join projections pr on pr.player_id = p.id
        where pr.horizon = 1 and pr.algorithm_version_id = %s and p.full_name = any(%s)
        """,
        (algo_id, names),
    )
    return {r["full_name"]: r for r in cur.fetchall()}


def load_schedule(cur, team_ids):
    cur.execute(
        """
        select team_id, gameweek, is_bye, opponent_win_total
        from team_schedule_difficulty
        where team_id = any(%s) and gameweek between 1 and %s
        """,
        (list(team_ids), SEASON_LENGTH),
    )
    by_team = {}
    for r in cur.fetchall():
        by_team.setdefault(r["team_id"], {})[r["gameweek"]] = r
    return by_team


def neutral_baseline(total_points_gw1, team_id, schedule, league_mean, league_std):
    gw1_row = schedule.get(team_id, {}).get(1)
    gw1_wt = float(gw1_row["opponent_win_total"]) if gw1_row and gw1_row["opponent_win_total"] is not None else league_mean
    gw1_mult = fixture_quality_multiplier(gw1_wt, league_mean, league_std)
    return total_points_gw1 / gw1_mult if gw1_mult else total_points_gw1


def estimate_for_gw(base, team_id, gw, schedule, league_mean, league_std):
    row = schedule.get(team_id, {}).get(gw)
    if row is None:
        return None
    if row["is_bye"]:
        return 0.0
    wt = float(row["opponent_win_total"]) if row["opponent_win_total"] is not None else league_mean
    return round(base * fixture_quality_multiplier(wt, league_mean, league_std), 1)


def build_estimates(players, schedule, league_mean, league_std):
    """Real fixture-neutral baseline per candidate (backed out of their
    real GW1 number), re-applied to every future gameweek's real opponent
    strength. Returns est[name][gw] -> points (0.0 on a real bye)."""
    est = {}
    for name, p in players.items():
        base = neutral_baseline(float(p["total_points"]), p["team_id"], schedule, league_mean, league_std)
        est[name] = {gw: estimate_for_gw(base, p["team_id"], gw, schedule, league_mean, league_std) for gw in GAMEWEEKS}
    return est


def squad_cost(roster, dst_name, players):
    return sum(float(players[n]["price"]) for n in roster.values()) + float(players[dst_name]["price"])


def team_counts(roster, dst_name, players):
    counts = {}
    for n in list(roster.values()) + [dst_name]:
        abbr = players[n]["team_abbr"]
        counts[abbr] = counts.get(abbr, 0) + 1
    return counts


def valid_after_swap(roster, dst_name, players, slot, new_name):
    trial = dict(roster)
    trial[slot] = new_name
    if len(set(trial.values())) < len(trial):
        return False  # would duplicate a player already in another slot
    if squad_cost(trial, dst_name, players) > BUDGET_CAP + 1e-9:
        return False
    if any(c > MAX_PER_TEAM for c in team_counts(trial, dst_name, players).values()):
        return False
    return True


def best_alternative(slot, roster, dst_name, players, est, gw, exclude):
    positions = SLOTS[slot]["positions"]
    pool = [n for pos in positions for n in CANDIDATES_BY_POSITION[pos] if n in players]
    current = roster[slot]
    scored = []
    for n in pool:
        if n == current or n in exclude:
            continue
        pts = est.get(n, {}).get(gw)
        if pts is None:
            continue
        if not valid_after_swap(roster, dst_name, players, slot, n):
            continue
        scored.append((pts, n))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0]  # (points, name)


def full_board_joint_search(cur, stuck_slots, roster, dst_name, players, gw, algo_id, league_mean, league_std):
    """Real full-board (every eligible player in the DB, not just the
    shortlist) search for slot(s) the shortlist couldn't afford to fix.
    Searches every stuck slot JOINTLY against the real shared budget freed
    by dropping the stuck players, since two slots decided independently
    can each assume the other's freed money - the exact mistake that would
    silently break the real GBP140M cap. Returns (combo, total_pts) or
    (None, 0) if nothing legal exists even with the whole board."""
    other_players_in_roster = {n for slot, n in roster.items() if slot not in stuck_slots} | {dst_name}
    counts_without_stuck = {}
    for n in other_players_in_roster:
        abbr = players[n]["team_abbr"]
        counts_without_stuck[abbr] = counts_without_stuck.get(abbr, 0) + 1

    freed_budget = sum(float(players[roster[slot]]["price"]) for slot in stuck_slots)
    budget_for_stuck = BUDGET_CAP - (squad_cost(roster, dst_name, players) - freed_budget)

    exclude_names = other_players_in_roster | {roster[s] for s in stuck_slots}

    pool_by_slot = {}
    for slot in stuck_slots:
        positions = SLOTS[slot]["positions"]
        cur.execute(
            """
            select p.id, p.full_name, p.position, p.price, p.team_id, t.abbr as team_abbr, pr.total_points
            from players p
            join teams t on t.id = p.team_id
            join projections pr on pr.player_id = p.id
            left join team_schedule_difficulty tsd on tsd.team_id = p.team_id and tsd.gameweek = %s
            where pr.horizon = 1 and pr.algorithm_version_id = %s and p.position = any(%s)
              and p.full_name not in %s
              and (tsd.is_bye is null or tsd.is_bye = false)
            """,
            (gw, algo_id, positions, tuple(exclude_names)),
        )
        rows = cur.fetchall()
        team_ids = {r["team_id"] for r in rows}
        sched = load_schedule(cur, team_ids)

        candidates = []
        for r in rows:
            base = neutral_baseline(float(r["total_points"]), r["team_id"], sched, league_mean, league_std)
            pts = estimate_for_gw(base, r["team_id"], gw, sched, league_mean, league_std)
            if pts is None or pts == 0.0:
                continue
            candidates.append({
                "name": r["full_name"], "price": float(r["price"]), "team_abbr": r["team_abbr"],
                "team_id": r["team_id"], "pts": pts, "gw1_total_points": float(r["total_points"]),
            })
        candidates.sort(key=lambda c: c["pts"], reverse=True)
        pool_by_slot[slot] = candidates[:40]  # top 40 by points is plenty for a joint search

    best_combo, best_total = None, -1
    for combo in itertools.product(*(pool_by_slot[s] for s in stuck_slots)):
        names = [c["name"] for c in combo]
        if len(set(names)) < len(names):
            continue
        if sum(c["price"] for c in combo) > budget_for_stuck + 1e-9:
            continue
        team_add = {}
        for c in combo:
            team_add[c["team_abbr"]] = team_add.get(c["team_abbr"], 0) + 1
        if any(counts_without_stuck.get(t, 0) + n > MAX_PER_TEAM for t, n in team_add.items()):
            continue
        total_pts = sum(c["pts"] for c in combo)
        if total_pts > best_total:
            best_total, best_combo = total_pts, combo

    if not best_combo:
        return None, 0

    # Build a FULL season-long estimate for each winner (not just this one
    # gameweek) so if they stay rostered afterward, later weeks aren't
    # silently scored as 0 for lack of data.
    winner_full_estimates = {}
    for c in best_combo:
        full_sched = load_schedule(cur, [c["team_id"]])
        base = neutral_baseline(c["gw1_total_points"], c["team_id"], full_sched, league_mean, league_std)
        winner_full_estimates[c["name"]] = {
            g: estimate_for_gw(base, c["team_id"], g, full_sched, league_mean, league_std) for g in GAMEWEEKS
        }

    return (best_combo, winner_full_estimates), best_total


def run_scenario(cur, algo_id, players, est, dst_name, league_mean, league_std,
                  label, max_per_team, wildcard_gw, verbose=True):
    """Runs the full-season greedy plan under a given (max_per_team,
    wildcard_gw) rule set. wildcard_gw=None means never use the real
    once-per-season Wildcard; otherwise that gameweek gets unlimited real
    transfers for free (still bound by budget/team-cap - a Wildcard lifts
    the transfer-count limit only, not those two), and per FanTeam's own
    real rule ("Once a Wildcard is activated, any saved up transfers from
    previous Gameweeks are reset to zero") any banked transfers are wiped
    immediately after that week."""
    global MAX_PER_TEAM
    MAX_PER_TEAM = max_per_team

    if verbose:
        print(f"\n{'=' * 70}\nSCENARIO: {label}  (max {max_per_team}/team, wildcard at GW{wildcard_gw or '-'})\n{'=' * 70}")

    roster = dict(INITIAL_ROSTER)
    banked = 0
    total_points = 0.0
    extra_transfer_weeks = []
    weekly_records = []

    for gw in GAMEWEEKS:
        moves = []
        exclude_this_week = set()
        is_wildcard = gw == wildcard_gw

        if gw == 1:
            available = 0
        elif is_wildcard:
            available = 10_000  # real rule: unlimited transfers this one week
        else:
            available = min(BANK_CAP, banked) + FREE_TRANSFERS_PER_GW

        used = 0

        if gw > 1:
            still_stuck = []
            for slot, name in list(roster.items()):
                if est.get(name, {}).get(gw) == 0.0:
                    alt = best_alternative(slot, roster, dst_name, players, est, gw, exclude_this_week)
                    if alt:
                        pts, new_name = alt
                        moves.append((slot, name, new_name, "real bye - forced out (shortlist)", pts))
                        roster[slot] = new_name
                        exclude_this_week.add(new_name)
                        used += 1
                    else:
                        still_stuck.append(slot)

            if still_stuck:
                result, _ = full_board_joint_search(cur, still_stuck, roster, dst_name, players, gw, algo_id, league_mean, league_std)
                if result:
                    combo, winner_full_estimates = result
                    for slot, c in zip(still_stuck, combo):
                        old_name = roster[slot]
                        players[c["name"]] = {"full_name": c["name"], "position": SLOTS[slot]["positions"][0],
                                               "price": c["price"], "team_id": c["team_id"], "team_abbr": c["team_abbr"],
                                               "total_points": c["gw1_total_points"]}
                        est[c["name"]] = winner_full_estimates[c["name"]]
                        moves.append((slot, old_name, c["name"], "real bye - forced out (full-board search)", c["pts"]))
                        roster[slot] = c["name"]
                        exclude_this_week.add(c["name"])
                        used += 1
                else:
                    for slot in still_stuck:
                        moves.append((slot, roster[slot], roster[slot], "STUCK - real bye, no affordable/legal replacement found anywhere on the board (scores 0 this week)", 0))

            # Discretionary upgrades: on a normal week, spend remaining free
            # transfers on real gains above the threshold; on a Wildcard
            # week, unlimited transfers means ANY positive real gain is
            # worth taking (still budget/team-cap legal, just free).
            threshold = 0.0 if is_wildcard else UPGRADE_THRESHOLD
            while used < available:
                best = None
                for slot in roster:
                    current_pts = est.get(roster[slot], {}).get(gw) or 0.0
                    alt = best_alternative(slot, roster, dst_name, players, est, gw, exclude_this_week)
                    if not alt:
                        continue
                    pts, new_name = alt
                    gain = pts - current_pts
                    if gain > threshold and (best is None or gain > best[0]):
                        best = (gain, slot, new_name, pts)
                if not best:
                    break
                gain, slot, new_name, pts = best
                reason = "Wildcard - free reshuffle" if is_wildcard else f"real upgrade (+{gain:.1f}pts)"
                moves.append((slot, roster[slot], new_name, reason, pts))
                roster[slot] = new_name
                exclude_this_week.add(new_name)
                used += 1

        extra = 0 if is_wildcard else (max(0, used - available) if gw > 1 else 0)
        if is_wildcard:
            banked = 0  # real rule: Wildcard wipes any banked transfers
        else:
            banked = min(BANK_CAP, max(0, available - used)) if gw > 1 else 0
        if extra:
            extra_transfer_weeks.append(gw)

        week_points = sum(est.get(n, {}).get(gw) or 0.0 for n in roster.values())
        week_points += est.get(dst_name, {}).get(gw) or 0.0
        week_points -= extra * EXTRA_TRANSFER_COST
        total_points += week_points

        cost = squad_cost(roster, dst_name, players)
        counts = team_counts(roster, dst_name, players)

        weekly_records.append({
            "gw": gw,
            "is_wildcard": is_wildcard,
            "roster": {slot: {
                "name": n, "team": players[n]["team_abbr"], "price": float(players[n]["price"]),
                "pts": est.get(n, {}).get(gw),
            } for slot, n in roster.items()},
            "dst": {"name": dst_name, "team": players[dst_name]["team_abbr"],
                    "price": float(players[dst_name]["price"]), "pts": est.get(dst_name, {}).get(gw)},
            "moves": [{"slot": slot, "old": old, "new": new, "reason": reason, "pts": pts} for slot, old, new, reason, pts in moves],
            "transfers_used": used,
            "transfers_available": available if (gw > 1 and not is_wildcard) else None,
            "extra_paid": extra,
            "banked_after": banked,
            "cost": cost,
            "team_counts": counts,
            "week_points": week_points,
            "running_total": total_points,
        })

        if verbose:
            tag = " [WILDCARD]" if is_wildcard else ""
            print(f"--- GW{gw}{tag} --- transfers used: {used} (available: {available if gw > 1 and not is_wildcard else '-'}), extra paid: {extra}, banked after: {banked}")
            if moves:
                for slot, old, new, reason, pts in moves:
                    if old == new:
                        print(f"    !! {slot}: {old}  ({reason})")
                    else:
                        print(f"    SWAP {slot}: {old} -> {new}  ({reason})")
            else:
                print("    no changes")
            for slot, n in roster.items():
                pts = est.get(n, {}).get(gw)
                pts_s = "BYE" if pts == 0.0 else (f"{pts:.1f}" if pts is not None else "?")
                print(f"    {slot:5s} {n:22s} £{float(players[n]['price']):5.1f}m  {pts_s}")
            print(f"    DST   {dst_name:22s} £{float(players[dst_name]['price']):5.1f}m  {est.get(dst_name, {}).get(gw):.1f}")
            print(f"    squad cost: £{cost:.1f}m / £{BUDGET_CAP:.1f}m  |  team counts: {counts}")
            if cost > BUDGET_CAP + 1e-9:
                print("    WARNING - over budget cap")
            if any(c > max_per_team for c in counts.values()):
                print("    WARNING - over the per-team cap")
            print(f"    week points (after any -8 penalties): {week_points:.1f}   running total: {total_points:.1f}\n")

    if verbose:
        print(f"=== {label}: {SEASON_LENGTH}-week total = {total_points:.1f} real projected points "
              f"(paid-transfer weeks: {extra_transfer_weeks or 'none'}) ===")
    return total_points, extra_transfer_weeks, weekly_records


def main():
    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("select id from algorithm_versions order by id desc limit 1")
    algo_id = cur.fetchone()["id"]

    cur.execute(
        "select opponent_win_total from team_schedule_difficulty where opponent_win_total is not null and is_bye = false"
    )
    win_totals = [float(r["opponent_win_total"]) for r in cur.fetchall()]
    league_mean, league_std = statistics.mean(win_totals), statistics.pstdev(win_totals)

    all_names = [n for names in CANDIDATES_BY_POSITION.values() for n in names] + DST_CANDIDATES
    players = load_candidate_data(cur, algo_id, all_names)
    missing = [n for n in all_names if n not in players]
    if missing:
        print(f"WARNING - not found in projections (skipped): {missing}")

    team_ids = {p["team_id"] for p in players.values()}
    schedule = load_schedule(cur, team_ids)
    est = build_estimates(players, schedule, league_mean, league_std)

    print(f"=== Real fixture-adjusted point estimates, GW1-{SEASON_LENGTH} ===")
    header = "Player".ljust(24) + "Team".ljust(6) + "".join(f"GW{g}".rjust(7) for g in GAMEWEEKS)
    print(header)
    for name in all_names:
        if name not in players:
            continue
        p = players[name]
        cells = []
        for g in GAMEWEEKS:
            v = est[name][g]
            cells.append("   BYE".rjust(7) if v == 0.0 else (f"{v:6.1f} ".rjust(7) if v is not None else "     - "))
        print(f"{name.ljust(24)}{p['team_abbr'].ljust(6)}{''.join(cells)}")

    dst_name = min((n for n in DST_CANDIDATES if n in players), key=lambda n: float(players[n]["price"]))
    print(f"\nDST held all season: {dst_name} (£{float(players[dst_name]['price']):.1f}m) - kept fixed, defensive scoring signal is too thin this early to spend transfers rotating it.\n")

    # Three scenarios compared:
    #  1) baseline - max 3/team, no Wildcard (the plan from the previous run)
    #  2) capped at 2/team, no Wildcard (this session's ask: does capping avoid the GW11 bye-collision squeeze?)
    #  3) max 3/team, but the real Wildcard is spent at GW11 - the pinch week the baseline run already found
    results = {}
    for label, max_per_team, wildcard_gw in [
        ("A: max 3/team, no Wildcard", 3, None),
        ("B: max 2/team, no Wildcard", 2, None),
        ("C: max 3/team, Wildcard at GW11", 3, 11),
    ]:
        # Fresh roster/points each run; players/est are shared and only ever
        # grow additively (full-board finds), so reuse across scenarios is safe.
        total, extra_weeks, _ = run_scenario(cur, algo_id, players, est, dst_name, league_mean, league_std,
                                              label, max_per_team, wildcard_gw, verbose=True)
        results[label] = (total, extra_weeks)

    print(f"\n{'=' * 70}\nCOMPARISON\n{'=' * 70}")
    for label, (total, extra_weeks) in results.items():
        print(f"{label:38s} {total:8.1f} pts   paid-transfer weeks: {extra_weeks or 'none'}")


if __name__ == "__main__":
    main()
