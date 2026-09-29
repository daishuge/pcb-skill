# -*- coding: utf-8 -*-
"""Shared 2D geometry primitives for the PCB checkers.

WHAT THIS MEASURES
    Exact planar distances between the outlines that PCB primitives really have:
    rectangles, rounded rectangles, obrounds (stadiums), circles, capsules (a stroked
    track) and arbitrary polygons.  Distances are edge-to-edge in millimetres, with
    full containment reported as 0.0.

WHAT THIS CANNOT SEE
    * Nothing about layers, nets, or electrical meaning -- callers decide which pairs
      are even worth measuring.
    * Nothing 3D.  Everything here is a flat outline at z = 0.
    * Curves are flattened into polygons before they get here, so a reported distance
      carries the flattening error of whoever built the polygon (see `circle_poly`'s
      `n` argument: 48 segments on a 0.5 mm circle is ~0.5 um of chord sag).
    * `poly_distance` is O(len(P) * len(Q)).  It is exact, not fast.  Callers must do
      their own bounding-box rejection first; every caller in this toolkit does.

HOW IT WAS VALIDATED
    Ported from the clearance sweep of a released 4-layer board, where these routines
    reproduced the EDA's own DRC minimum (0.1020 mm over 3248 measured pairs) and,
    separately, its three hole-to-hole findings exactly.  `--selftest` re-checks the
    containment fix and the analytic cases below on synthetic input.

FAULT FIXED HERE (fault 2 of 4 -- "polygon distance blind to full containment")
    The original `poly_dist` computed edge-to-edge distance only.  When one polygon
    lies WHOLLY INSIDE another, no pair of edges crosses, so it returned a positive,
    confident, and completely wrong clearance: a large tantalum land that had entirely
    swallowed an 0805 pad still reported 0.22 mm of clearance, and the placement gate
    that consumed the number passed the board.  `poly_distance` below tests containment
    explicitly, in BOTH directions, before it measures any edges.
"""
from __future__ import print_function

import math
import sys

__all__ = [
    "rot", "mirror_point", "bbox_of", "rect_gap", "boxes_overlap",
    "point_in_poly", "dist_point_segment", "dist_segment_segment",
    "poly_distance", "poly_area", "poly_centroid",
    "rect_poly", "circle_poly", "capsule_poly", "roundrect_poly", "obround_poly",
    "pad_outline",
]


# --------------------------------------------------------------------------- transforms

def rot(x, y, deg):
    """Rotate a footprint-local point COUNTER-CLOCKWISE by `deg` degrees.

    CCW is the convention measured on the reference toolchain against four differently
    rotated TOP-side parts.  A bottom-side-only test cannot tell CW from CCW, so if you
    port this to another EDA, re-measure with a rotated top-side part.
    """
    a = math.radians(deg or 0.0)
    c, s = math.cos(a), math.sin(a)
    return (x * c - y * s, x * s + y * c)


def mirror_point(x, y, axis="x"):
    """Mirror a footprint-local point for a bottom-side placement.

    MEASURED: EasyEDA Pro mirrors a bottom-side part in Y (negate y, then rotate).
    ARK CARD R1, 2026-09-28 (6 layers, 64 bottom-side parts, EasyEDA Pro 3.2 .epro
    export): with "x" route_accept reported 223 different-net overlaps (every one on a
    bottom part, all -0.25 mm) and 48 split nets; with "y" 145/146 nets whole and the
    clearance gate passed, matching EasyEDA's own DRC. This agrees with references
    02-review.md section 2d and 05-easyeda-mcp.md T9. The reference project's older
    board models negated X; if an export ever disagrees, re-measure on an ASYMMETRIC
    bottom part -- `layers.mirror_axis` stays a config key for exactly that. Get it
    wrong and every bottom-side part is 180 degrees out, which looks plausible on a
    symmetric footprint.
    """
    if axis == "x":
        return (-x, y)
    if axis == "y":
        return (x, -y)
    raise ValueError("mirror axis must be 'x' or 'y', got %r" % (axis,))


# --------------------------------------------------------------------------- boxes

def bbox_of(pts):
    """Axis-aligned bounding box [x0, y0, x1, y1] of a point list."""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def rect_gap(b1, b2):
    """Edge-to-edge separation of two axis-aligned boxes.

    Positive: the true corner/edge distance.  Negative: the overlap depth (the smaller
    of the two axis penetrations, expressed as a negative number), so callers can rank
    "how badly" two courtyards intersect.
    """
    dx = max(b1[0] - b2[2], b2[0] - b1[2])
    dy = max(b1[1] - b2[3], b2[1] - b1[3])
    if dx >= 0 and dy >= 0:
        return math.hypot(dx, dy)
    if dx >= 0:
        return dx
    if dy >= 0:
        return dy
    return max(dx, dy)


def boxes_overlap(b1, b2, slack=0.0):
    """True when two boxes are within `slack` of each other (a cheap pre-filter)."""
    return not (b1[0] > b2[2] + slack or b2[0] > b1[2] + slack or
                b1[1] > b2[3] + slack or b2[1] > b1[3] + slack)


# --------------------------------------------------------------------------- polygons

def point_in_poly(px, py, poly):
    """Even-odd point-in-polygon test.  Only meaningful for a closed ring (len >= 3).

    A point exactly on an edge is undefined (it may report either side).  Every caller
    here uses it as a containment test where a micrometre either way does not change
    the verdict, because a genuinely-contained polygon is contained by a lot.
    """
    if len(poly) < 3:
        return False
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py):
            xint = xi + (py - yi) * (xj - xi) / (yj - yi)
            if px < xint:
                inside = not inside
        j = i
    return inside


def dist_point_segment(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L <= 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def dist_segment_segment(a, b, c, d):
    """Distance between segments a-b and c-d; 0.0 when they cross."""
    (ax, ay), (bx, by) = a, b
    (cx, cy), (dx_, dy_) = c, d
    d1x, d1y = bx - ax, by - ay
    d2x, d2y = dx_ - cx, dy_ - cy
    den = d1x * d2y - d1y * d2x
    if abs(den) > 1e-15:
        t = ((cx - ax) * d2y - (cy - ay) * d2x) / den
        u = ((cx - ax) * d1y - (cy - ay) * d1x) / den
        if -1e-12 <= t <= 1.0 + 1e-12 and -1e-12 <= u <= 1.0 + 1e-12:
            return 0.0
    return min(dist_point_segment(ax, ay, cx, cy, dx_, dy_),
               dist_point_segment(bx, by, cx, cy, dx_, dy_),
               dist_point_segment(cx, cy, ax, ay, bx, by),
               dist_point_segment(dx_, dy_, ax, ay, bx, by))


def poly_distance(P, Q):
    """Minimum distance between two point lists, containment-aware.

    A list of 1 point is a degenerate segment (a via, a round pad core).  Without that
    case the original returned "infinitely far apart" for every via pair -- a second,
    quieter version of the same class of bug as the containment one.
    A list of 2 points is an open segment.  A list of 3+ is treated as a CLOSED ring.

    FAULT 2 FIX: containment is tested first, in both directions, and returns 0.0.
    Edge-to-edge alone cannot see one polygon lying wholly inside another.
    """
    if len(P) > 2 and point_in_poly(Q[0][0], Q[0][1], P):
        return 0.0
    if len(Q) > 2 and point_in_poly(P[0][0], P[0][1], Q):
        return 0.0
    if len(P) == 1:
        P = [P[0], P[0]]
    if len(Q) == 1:
        Q = [Q[0], Q[0]]
    closed_p = len(P) > 2
    closed_q = len(Q) > 2
    ep = list(zip(P, P[1:] + ([P[0]] if closed_p else [])))
    eq = list(zip(Q, Q[1:] + ([Q[0]] if closed_q else [])))
    best = float("inf")
    for a, b in ep:
        for c, d in eq:
            v = dist_segment_segment(a, b, c, d)
            if v < best:
                best = v
                if best <= 0.0:
                    return 0.0
    return best


def poly_area(pts):
    """Unsigned shoelace area."""
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def poly_centroid(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


# --------------------------------------------------------------------------- outlines

def rect_poly(cx, cy, w, h, angle=0.0):
    out = []
    for sx, sy in ((-w / 2.0, -h / 2.0), (w / 2.0, -h / 2.0),
                   (w / 2.0, h / 2.0), (-w / 2.0, h / 2.0)):
        dx, dy = rot(sx, sy, angle)
        out.append((cx + dx, cy + dy))
    return out


def circle_poly(cx, cy, r, n=48):
    return [(cx + r * math.cos(2 * math.pi * k / n),
             cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def capsule_poly(x1, y1, x2, y2, r, n=24):
    """Outline of a stroked segment (a track): every point within r of the segment."""
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L < 1e-12:
        return circle_poly(x1, y1, r, max(n, 8))
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    pts = []
    a0 = math.atan2(ny, nx)
    for k in range(n + 1):
        t = a0 - math.pi * k / n
        pts.append((x2 + r * math.cos(t), y2 + r * math.sin(t)))
    a1 = math.atan2(-ny, -nx)
    for k in range(n + 1):
        t = a1 - math.pi * k / n
        pts.append((x1 + r * math.cos(t), y1 + r * math.sin(t)))
    return pts


def roundrect_poly(cx, cy, w, h, radius, angle=0.0, per_corner=8):
    """w x h rectangle with `radius` corner rounding, rotated CCW by `angle`."""
    r = max(0.0, min(radius, min(w, h) / 2.0))
    if r <= 1e-12:
        return rect_poly(cx, cy, w, h, angle)
    hw, hh = w / 2.0 - r, h / 2.0 - r
    local = []
    for sx, sy, a0 in ((hw, hh, 0.0), (-hw, hh, math.pi / 2),
                       (-hw, -hh, math.pi), (hw, -hh, 1.5 * math.pi)):
        for k in range(per_corner + 1):
            t = a0 + (math.pi / 2) * k / per_corner
            local.append((sx + r * math.cos(t), sy + r * math.sin(t)))
    out = []
    for lx, ly in local:
        dx, dy = rot(lx, ly, angle)
        out.append((cx + dx, cy + dy))
    return out


def obround_poly(cx, cy, w, h, angle=0.0, n=24):
    """A stadium: the rectangle's long axis capped with semicircles of min(w,h)/2.

    An obround modelled as a plain rectangle grows four corners it does not have.  On
    the reference board that single mistake produced every one of eleven phantom
    clearance "violations" around SOIC/TSSOP lands.  Never approximate an obround by
    its bounding rectangle in a clearance check.
    """
    r = min(w, h) / 2.0
    if w >= h:
        p1, p2 = (-(w / 2.0 - r), 0.0), (w / 2.0 - r, 0.0)
    else:
        p1, p2 = (0.0, -(h / 2.0 - r)), (0.0, h / 2.0 - r)
    a = capsule_poly(p1[0], p1[1], p2[0], p2[1], r, n)
    out = []
    for lx, ly in a:
        dx, dy = rot(lx, ly, angle)
        out.append((cx + dx, cy + dy))
    return out


def pad_outline(shape, cx, cy, w, h, angle=0.0, corner_radius=0.0, polygon=None):
    """Dispatch a pad record to its true outline polygon, in board mm.

    `shape` is matched case-insensitively against RECT / ROUNDRECT / OVAL / OBROUND /
    ELLIPSE / CIRCLE / POLYGON.  An unknown shape falls back to RECT and the caller is
    expected to notice: an unrecognised pad shape is a porting bug, not a board fact.
    """
    s = (shape or "RECT").upper()
    if s in ("POLYGON", "POLY") and polygon:
        out = []
        for lx, ly in polygon:
            dx, dy = rot(lx, ly, angle)
            out.append((cx + dx, cy + dy))
        return out
    if s in ("CIRCLE", "ROUND"):
        return circle_poly(cx, cy, max(w, h) / 2.0)
    if s in ("OVAL", "OBROUND", "ELLIPSE"):
        return obround_poly(cx, cy, w, h, angle)
    if s in ("ROUNDRECT", "ROUND_RECT", "RR"):
        return roundrect_poly(cx, cy, w, h, corner_radius, angle)
    return rect_poly(cx, cy, w, h, angle)


# --------------------------------------------------------------------------- selftest

def _selftest():
    ok = True

    def check(name, got, want, tol=1e-6):
        global_ok = abs(got - want) <= tol
        print("  %-52s %-12s %s" % (name, "%.6f" % got, "OK" if global_ok else
                                    "FAIL (want %.6f)" % want))
        return global_ok

    print("geom2d selftest")

    # THE FAULT-2 CASE: a small square wholly inside a big one.
    big = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    small = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]
    ok &= check("contained polygon distance (fault 2, must be 0)",
                poly_distance(big, small), 0.0)
    ok &= check("contained polygon distance, arguments swapped",
                poly_distance(small, big), 0.0)

    # a naive edge-only sweep for comparison, to show the fault is real
    edge_only = float("inf")
    for i in range(4):
        for j in range(4):
            edge_only = min(edge_only, dist_segment_segment(
                big[i], big[(i + 1) % 4], small[j], small[(j + 1) % 4]))
    print("  %-52s %-12s %s" % ("edge-only distance for the same pair",
                                "%.6f" % edge_only,
                                "<- this is the wrong answer the fault produced"))
    ok &= (abs(edge_only - 4.0) < 1e-9)

    # ordinary separated squares
    a = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    b = [(2.5, 0.0), (3.5, 0.0), (3.5, 1.0), (2.5, 1.0)]
    ok &= check("separated squares, gap 1.5", poly_distance(a, b), 1.5)

    # degenerate single points (a via pair)
    ok &= check("point-to-point (via pair)", poly_distance([(0.0, 0.0)], [(3.0, 4.0)]), 5.0)

    # crossing segments
    ok &= check("crossing open segments", poly_distance([(-1.0, 0.0), (1.0, 0.0)],
                                                        [(0.0, -1.0), (0.0, 1.0)]), 0.0)
    # rect gap
    ok &= check("rect_gap diagonal corners", rect_gap([0, 0, 1, 1], [4, 4, 5, 5]),
                math.hypot(3.0, 3.0))
    ok &= check("rect_gap overlap is negative", rect_gap([0, 0, 2, 2], [1, 1, 3, 3]), -1.0)

    # obround must NOT be its bounding rectangle
    ob = obround_poly(0.0, 0.0, 2.0, 1.0)
    corner = [(1.0, 0.5)]
    d_ob = poly_distance(ob, [(1.0, 0.5), (1.0001, 0.5)])
    ok &= (d_ob > 0.05)
    print("  %-52s %-12s %s" % ("obround corner is empty (rect would give 0)",
                                "%.6f" % d_ob, "OK" if d_ob > 0.05 else "FAIL"))
    del corner

    # areas
    ok &= check("poly_area unit square", poly_area(a), 1.0)
    ok &= check("circle_poly area ~ pi r^2 (48 seg, 0.3 % low)",
                poly_area(circle_poly(0, 0, 1.0, 48)), math.pi, 0.01)

    # rotation convention: +90 deg CCW takes +X to +Y
    rx, ry = rot(1.0, 0.0, 90.0)
    ok &= check("rot(+X, 90 deg) -> +Y : x component", rx, 0.0, 1e-12)
    ok &= check("rot(+X, 90 deg) -> +Y : y component", ry, 1.0, 1e-12)

    print("geom2d selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(__doc__)
    print("run with --selftest")
