"""
stat_math.py
--------------
Shared math for turning real Spreadex ladder/O-U odds into an expected
stat count. Two real market shapes, two real estimators:

1. Value ladders (passing_yards, rushing_yards, receiving_yards,
   total_receptions, ...): a set of real (threshold, P(X >= threshold))
   points. expected_value_from_points() uses the standard tail-sum
   identity E[X] = integral of P(X >= x) dx for a non-negative X,
   trapezoidal between observed points, with a geometric-decay tail
   estimate beyond the highest observed rung (extending the last real
   segment's own decay ratio, not an invented one) rather than assuming
   probability mass drops to zero right after the last priced line.

2. Anytime-count ladders (passing_touchdowns 1+/2+/3+/...):
   anytime_prob_to_expected_count() - identical Poisson-process maths
   already proven in the sibling dreamteam-projections repo's
   scrape_spreadex_player_markets.py (P(at least 1) -> expected count).
   Uses only the "1+" rung, matching that accepted precedent - the extra
   rungs (2+, 3+) exist as real data but a single-rung Poisson fit is the
   established, already-reviewed approach, not something to redesign here.

Not a standalone script - imported by compute_projections.py.
"""
import math

# Real, commonly-observed NFL team-scoring standard deviation (team points
# per game cluster roughly Normal around the market's own projected mean
# with a spread of ~10 points) - a documented modeling assumption, not
# measured from this project's own data yet (one gameweek of a brand-new
# season isn't enough to fit a real variance from). Refine once real
# predictions_and_actuals history exists - see feedback_calibration_layer_
# discipline in project memory.
POINTS_ALLOWED_SD = 10.0

# FanTeam's real points-allowed tiers (scoring_rules stat, (low, high)
# inclusive real point range - high=None means unbounded).
POINTS_ALLOWED_TIERS = [
    ("points_allowed_0", 0, 0),
    ("points_allowed_1_6", 1, 6),
    ("points_allowed_7_13", 7, 13),
    ("points_allowed_14_20", 14, 20),
    ("points_allowed_21_27", 21, 27),
    ("points_allowed_28_34", 28, 34),
    ("points_allowed_35_plus", 35, None),
]


def normal_cdf(x, mean, sd):
    return 0.5 * (1 + math.erf((x - mean) / (sd * math.sqrt(2))))


def points_allowed_distribution(mean_points, sd=POINTS_ALLOWED_SD):
    """Real opponent-points market data (mean_points, from game_odds'
    spread + total) turned into a probability-weighted expectation across
    FanTeam's real points-allowed tiers, via a Normal approximation with
    continuity correction - the same tail-probability idea as
    expected_value_from_points below, applied to a discrete scoring
    ladder instead of a continuous yardage curve. Returns
    {tier_stat: probability} for every real tier, summing to 1.0."""
    distribution = {}
    for stat, low, high in POINTS_ALLOWED_TIERS:
        lo_edge = low - 0.5
        hi_edge = math.inf if high is None else high + 0.5
        p_hi = 1.0 if math.isinf(hi_edge) else normal_cdf(hi_edge, mean_points, sd)
        p_lo = normal_cdf(lo_edge, mean_points, sd)
        distribution[stat] = max(0.0, p_hi - p_lo)

    # Real NFL points scored can't go below 0, but the Normal approximation
    # puts some mass there anyway - renormalize so the 7 real tiers still
    # sum to 1.0 rather than silently losing that probability (material at
    # low means: ~9% at a 13-point mean).
    total = sum(distribution.values())
    if total > 0:
        distribution = {stat: p / total for stat, p in distribution.items()}
    return distribution


def fixture_quality_multiplier(opponent_win_total, league_mean, league_std, k=0.15, clip=(0.7, 1.3)):
    """Real, market-derived opponent strength (Sharp Football Analysis's
    own Vegas-win-total-based model, see team_schedule_difficulty) turned
    into a multiplier on a player's baseline production for a FUTURE week
    that has no live odds yet. A tougher-than-average opponent (positive
    z-score) scales production down; an easier one scales it up.

    k=0.15 and the [0.7, 1.3] clip are a documented, deliberately modest
    first-pass assumption (a 1-std-tougher opponent is a 15% adjustment,
    capped at +/-30% even at the extremes) - not fit to any real
    prediction-accuracy data yet, since none exists for a season that's
    barely started. Revisit once real predictions_and_actuals history
    exists to check it against."""
    if league_std <= 0:
        return 1.0
    z = (opponent_win_total - league_mean) / league_std
    multiplier = 1 - k * z
    return max(clip[0], min(clip[1], multiplier))


def american_to_decimal(american_odds):
    """Real US-format odds ('-335', '+130') -> decimal odds. Standard
    conversion: negative means "bet this much to win 100", positive means
    "this much won per 100 staked"."""
    o = float(american_odds)
    return 1 + (100 / abs(o)) if o < 0 else 1 + (o / 100)


def anytime_prob_to_expected_count(p):
    p = max(0.0, min(0.99, p))
    return -math.log(1 - p) if p > 0 else 0.0


def expected_value_from_points(points):
    """points: iterable of (threshold: float, prob_at_least: float).
    Real, non-negative thresholds only - callers filter out anything else
    (e.g. an Over/Under line's threshold is included as one more point on
    the same real survival curve as the ladder rungs, not a separate
    market)."""
    pts = sorted({(float(t), float(p)) for t, p in points}, key=lambda tp: tp[0])
    if not pts:
        return 0.0
    if pts[0][0] > 0:
        pts = [(0.0, 1.0)] + pts

    area = 0.0
    for (x0, p0), (x1, p1) in zip(pts, pts[1:]):
        area += (x1 - x0) * (p0 + p1) / 2.0

    if len(pts) >= 2:
        (x_prev, p_prev), (x_last, p_last) = pts[-2], pts[-1]
        step = x_last - x_prev
        if step > 0 and p_prev > 0 and 0 < p_last < p_prev:
            ratio = p_last / p_prev
            # Geometric-series sum of the remaining trapezoids, extending
            # the same real decay rate observed in the last priced segment.
            area += step * p_last * ratio / (1 - ratio)

    return area
