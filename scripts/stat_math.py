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
