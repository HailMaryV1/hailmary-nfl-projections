"""
plan_optimal_playbook.py
---------------------------
A second, independent playbook alongside plan_squad_strategy.py's
team-preference-driven one - this one starts with no team list at all.
Every pick, every week, is whatever the real projections + real fixture
data say is best across the FULL player board (~600 real players, all
positions), not a shortlist built around teams the user picked. The idea
(per the user's own framing): "recreate a playbook from your projections
and fixture difficulty... and I will play the team you pick each week" -
a direct, real comparison against the hand-picked-teams playbook.

Same real FanTeam rules as plan_squad_strategy.py: 9 slots (QB1/RB2/WR3/
TE1/FLEX1/DST1), no bench, GBP140M budget, max 2 players per real team
(the tested-better rule from the earlier 2-vs-3 comparison), 2 free
transfers/gameweek (bankable up to 34, -8pts per transfer beyond that),
one real season Wildcard.

GW1 squad is solved fresh from the whole board via a standard fantasy-
optimizer heuristic, not picked by hand: build the real best-XI ignoring
budget (top real scorer per slot, full board, team-cap respected), then
repeatedly downgrade whichever single swap loses the fewest real points
per pound saved until the real GBP140M cap is met. Every later gameweek's
transfer decision reuses the exact same real fixture-adjusted-estimate
methodology as plan_squad_strategy.py (see that file's docstring for the
full rationale) - the only real difference here is the candidate pool is
the entire board, every week, not a 19-name shortlist.

RUN:
    python scripts/plan_optimal_playbook.py
"""
import sys
import json
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect
import plan_squad_strategy as pss
import psycopg2.extras

MAX_PER_TEAM = 2
BUDGET_CAP = 140.0
pss.MAX_PER_TEAM = MAX_PER_TEAM
pss.BUDGET_CAP = BUDGET_CAP

SLOT_POSITIONS = {
    "QB": "quarterback", "RB1": "running_back", "RB2": "running_back",
    "WR1": "wide_receiver", "WR2": "wide_receiver", "WR3": "wide_receiver",
    "TE": "tight_end",
}


def load_full_board(cur, algo_id):
    cur.execute(
        """
        select p.id, p.full_name, p.position, p.price, p.team_id, t.abbr as team_abbr, pr.total_points
        from players p
        join teams t on t.id = p.team_id
        join projections pr on pr.player_id = p.id
        where pr.horizon = 1 and pr.algorithm_version_id = %s
          and p.position in ('quarterback','running_back','wide_receiver','tight_end','defense_special')
        """,
        (algo_id,),
    )
    by_position, players = {}, {}
    for r in cur.fetchall():
        rec = {"full_name": r["full_name"], "position": r["position"], "price": float(r["price"]),
               "team_id": r["team_id"], "team_abbr": r["team_abbr"], "total_points": float(r["total_points"])}
        players[r["full_name"]] = rec
        by_position.setdefault(r["position"], []).append(rec)
    for pos in by_position:
        by_position[pos].sort(key=lambda p: p["total_points"], reverse=True)
    return players, by_position


def pick_best(pool, used, team_counts):
    for p in pool:
        if p["full_name"] in used or team_counts.get(p["team_abbr"], 0) >= MAX_PER_TEAM:
            continue
        return p
    return None


def solve_gw1_squad(by_position):
    """Real fantasy-optimizer heuristic: best-XI-ignoring-budget, then
    repeatedly downgrade whichever swap loses the fewest real points per
    pound saved until under the real budget cap."""
    roster, used, team_counts = {}, set(), {}
    for slot, pos in SLOT_POSITIONS.items():
        p = pick_best(by_position[pos], used, team_counts)
        roster[slot] = p
        used.add(p["full_name"])
        team_counts[p["team_abbr"]] = team_counts.get(p["team_abbr"], 0) + 1

    flex_pool = sorted(
        [p for pos in ("running_back", "wide_receiver", "tight_end") for p in by_position[pos]],
        key=lambda p: p["total_points"], reverse=True,
    )
    p = pick_best(flex_pool, used, team_counts)
    roster["FLEX"] = p
    used.add(p["full_name"])
    team_counts[p["team_abbr"]] = team_counts.get(p["team_abbr"], 0) + 1

    dst = pick_best(by_position["defense_special"], used, team_counts)

    def total_cost():
        return sum(v["price"] for v in roster.values()) + dst["price"]

    def slot_pool(slot):
        return by_position[SLOT_POSITIONS[slot]] if slot in SLOT_POSITIONS else flex_pool

    while total_cost() > BUDGET_CAP:
        best = None  # (ratio, slot, replacement)
        for slot, current in roster.items():
            for cand in slot_pool(slot):
                if cand["full_name"] in used or cand["price"] >= current["price"]:
                    continue
                trial_counts = dict(team_counts)
                trial_counts[current["team_abbr"]] -= 1
                if trial_counts.get(cand["team_abbr"], 0) >= MAX_PER_TEAM and cand["team_abbr"] != current["team_abbr"]:
                    continue
                loss = current["total_points"] - cand["total_points"]
                saved = current["price"] - cand["price"]
                ratio = loss / saved
                if best is None or ratio < best[0]:
                    best = (ratio, slot, cand)
        if best is None:
            raise RuntimeError("No legal downgrade found - can't reach budget even with the cheapest real options.")
        _, slot, cand = best
        old = roster[slot]
        used.discard(old["full_name"])
        team_counts[old["team_abbr"]] -= 1
        roster[slot] = cand
        used.add(cand["full_name"])
        team_counts[cand["team_abbr"]] = team_counts.get(cand["team_abbr"], 0) + 1

    return roster, dst


def full_board_alternative(slot, roster, dst_name, players, by_position, est, gw, exclude):
    """Same shape as plan_squad_strategy.best_alternative, but the pool is
    the ENTIRE real board for that slot's position(s), not a shortlist."""
    positions = pss.SLOTS[slot]["positions"]
    pool = [p["full_name"] for pos in positions for p in by_position[pos]]
    current = roster[slot]
    scored = []
    for n in pool:
        if n == current or n in exclude:
            continue
        pts = est.get(n, {}).get(gw)
        if pts is None:
            continue
        if not pss.valid_after_swap(roster, dst_name, players, slot, n):
            continue
        scored.append((pts, n))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0]


def run_full_board_scenario(players, by_position, est, dst_name, initial_roster, label, wildcard_gw, verbose=True):
    if verbose:
        print(f"\n{'=' * 70}\n{label}  (wildcard at GW{wildcard_gw or '-'})\n{'=' * 70}")

    roster = dict(initial_roster)
    banked = 0
    total_points = 0.0
    extra_transfer_weeks = []
    weekly_records = []

    for gw in pss.GAMEWEEKS:
        moves = []
        exclude_this_week = set()
        is_wildcard = gw == wildcard_gw

        if gw == 1:
            available = 0
        elif is_wildcard:
            available = 10_000
        else:
            available = min(pss.BANK_CAP, banked) + pss.FREE_TRANSFERS_PER_GW

        used = 0

        if gw > 1:
            for slot, name in list(roster.items()):
                if est.get(name, {}).get(gw) == 0.0:
                    alt = full_board_alternative(slot, roster, dst_name, players, by_position, est, gw, exclude_this_week)
                    if alt:
                        pts, new_name = alt
                        moves.append((slot, name, new_name, "real bye - forced out", pts))
                        roster[slot] = new_name
                        exclude_this_week.add(new_name)
                        used += 1
                    else:
                        moves.append((slot, name, name, "STUCK - no legal replacement anywhere on the board", 0))

            threshold = 0.0 if is_wildcard else pss.UPGRADE_THRESHOLD
            while used < available:
                best = None
                for slot in roster:
                    current_pts = est.get(roster[slot], {}).get(gw) or 0.0
                    alt = full_board_alternative(slot, roster, dst_name, players, by_position, est, gw, exclude_this_week)
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
        banked = 0 if is_wildcard else (min(pss.BANK_CAP, max(0, available - used)) if gw > 1 else 0)
        if extra:
            extra_transfer_weeks.append(gw)

        week_points = sum(est.get(n, {}).get(gw) or 0.0 for n in roster.values())
        week_points += est.get(dst_name, {}).get(gw) or 0.0
        week_points -= extra * pss.EXTRA_TRANSFER_COST
        total_points += week_points

        cost = pss.squad_cost(roster, dst_name, players)
        counts = pss.team_counts(roster, dst_name, players)

        weekly_records.append({
            "gw": gw, "is_wildcard": is_wildcard,
            "roster": {slot: {"name": n, "team": players[n]["team_abbr"], "price": float(players[n]["price"]),
                               "pts": est.get(n, {}).get(gw)} for slot, n in roster.items()},
            "dst": {"name": dst_name, "team": players[dst_name]["team_abbr"], "price": float(players[dst_name]["price"]),
                    "pts": est.get(dst_name, {}).get(gw)},
            "moves": [{"slot": s, "old": o, "new": nn, "reason": r, "pts": p} for s, o, nn, r, p in moves],
            "transfers_used": used, "transfers_available": available if (gw > 1 and not is_wildcard) else None,
            "extra_paid": extra, "banked_after": banked, "cost": cost, "team_counts": counts,
            "week_points": week_points, "running_total": total_points,
        })

        if verbose:
            tag = " [WILDCARD]" if is_wildcard else ""
            print(f"--- GW{gw}{tag} --- transfers used: {used}, extra paid: {extra}, banked after: {banked}")
            for slot, old, new, reason, pts in moves:
                if old == new:
                    print(f"    !! {slot}: {old}  ({reason})")
                else:
                    print(f"    SWAP {slot}: {old} -> {new}  ({reason})")
            if not moves:
                print("    no changes")
            print(f"    squad cost: £{cost:.1f}m / £{BUDGET_CAP:.1f}m  |  team counts: {counts}")
            print(f"    week points: {week_points:.1f}   running total: {total_points:.1f}\n")

    if verbose:
        print(f"=== {label}: {pss.SEASON_LENGTH}-week total = {total_points:.1f} pts (paid weeks: {extra_transfer_weeks or 'none'}) ===")
    return total_points, extra_transfer_weeks, weekly_records


def main():
    conn = db_connect()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("select id from algorithm_versions order by id desc limit 1")
    algo_id = cur.fetchone()["id"]

    cur.execute("select opponent_win_total from team_schedule_difficulty where opponent_win_total is not null and is_bye = false")
    win_totals = [float(r["opponent_win_total"]) for r in cur.fetchall()]
    league_mean, league_std = statistics.mean(win_totals), statistics.pstdev(win_totals)

    players, by_position = load_full_board(cur, algo_id)
    roster, dst = solve_gw1_squad(by_position)

    print("=== Real optimal GW1 squad (full board, no shortlist) ===")
    initial_roster = {}
    for slot, p in roster.items():
        initial_roster[slot] = p["full_name"]
        print(f"  {slot:5s} {p['full_name']:22s} {p['team_abbr']:4s} £{p['price']:5.1f}m  {p['total_points']:.1f}pts")
    dst_name = dst["full_name"]
    print(f"  DST   {dst['full_name']:22s} {dst['team_abbr']:4s} £{dst['price']:5.1f}m  {dst['total_points']:.1f}pts")
    cost = sum(p["price"] for p in roster.values()) + dst["price"]
    print(f"  squad cost: £{cost:.1f}m / £{BUDGET_CAP:.1f}m\n")

    team_ids = {p["team_id"] for p in players.values()}
    schedule = pss.load_schedule(cur, team_ids)
    est = pss.build_estimates(players, schedule, league_mean, league_std)

    baseline, _, _ = run_full_board_scenario(players, by_position, est, dst_name, initial_roster,
                                              "Baseline (no wildcard)", None, verbose=False)
    print(f"Baseline, no wildcard: {baseline:.1f} pts\n")

    print("Sweeping every gameweek for the best real Wildcard timing...")
    sweep = []
    for gw in range(2, pss.SEASON_LENGTH + 1):
        total, extra, _ = run_full_board_scenario(players, by_position, est, dst_name, initial_roster,
                                                    f"wildcard@{gw}", gw, verbose=False)
        sweep.append((gw, total, total - baseline))
    sweep.sort(key=lambda r: -r[2])
    print("Top 5 real wildcard weeks by gain:")
    for gw, total, gain in sweep[:5]:
        print(f"  GW{gw:<3d} total {total:8.1f}  gain {gain:+.1f}")
    best_wildcard_gw = sweep[0][0]
    print(f"\nBest real week: GW{best_wildcard_gw}\n")

    total, extra_weeks, records = run_full_board_scenario(players, by_position, est, dst_name, initial_roster,
                                                            f"FINAL: full-board playbook, wildcard@GW{best_wildcard_gw}",
                                                            best_wildcard_gw, verbose=True)

    with open("plan_optimal.json", "w") as f:
        json.dump({"total_points": total, "extra_transfer_weeks": extra_weeks, "weeks": records}, f, indent=2)
    print(f"\nSaved plan_optimal.json, {len(records)} weeks, {total:.1f} total points")


if __name__ == "__main__":
    main()
