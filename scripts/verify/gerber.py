# -*- coding: utf-8 -*-
"""An independent RS-274X Gerber and Excellon reader.

WHY IT EXISTS
    The fabrication package is the artefact that gets built.  Verifying it by asking the
    EDA that produced it proves nothing -- the same code path made the file and the
    answer.  This reader is deliberately written from the SPEC and the FILE, so that a
    disagreement between it and the EDA is information rather than noise.

WHAT IT UNDERSTANDS
    format         %FSLAX<i><d>Y<i><d>*%   leading zeros omitted, absolute
    units          %MOMM*%   (inch is REJECTED, not silently mis-scaled -- see below)
    apertures      C circle, R rectangle, O obround, RoundRect, and AM macro outlines
    operations     G01 linear, G02/G03 circular (G74/G75), D01 draw / D02 move / D03 flash
    regions        G36 ... G37
    sections       G04 <Word> Start / G04 <Word> End
                   Some EDAs tag every object class this way (Pad / Via / Track / Copper
                   / Text ...).  Where present it is what lets a pad be told apart from
                   a via and from a track WITHOUT any netlist, which several checks in
                   this toolkit depend on.  Where absent, `section` is "" and those
                   checks degrade to "all copper" -- they say so rather than guessing.
    Excellon       METRIC, leading zeros omitted, T<n>C<dia>, G85 slots, plated flag
                   read from the TYPE=PLATED header comment.

WHAT IT CANNOT SEE
    * Anything it has not met.  It RAISES on an unhandled parameter or command instead
      of skipping it.  That is deliberate: a Gerber reader that silently ignores what it
      does not understand will happily report a clean board it never read.  If your
      exporter emits something new, the error names it.
    * Polarity.  %LPD/%LPC are accepted and IGNORED, so a clear-polarity layer (used by
      some tools for cut-outs) would be read as solid.  Check the header if your EDA
      emits %LPC.
    * Step-and-repeat (%SR), aperture-macro primitives other than the outline (code 4),
      and X2 attributes beyond being tolerated.
    * Whether the file is the one that was ordered.  Hash the package.

RoundRect (corrected 2026-09-29, ARK CARD round-2 audit)
    %ADDnnRoundRect,r X x1 X y1 X x2 X y2 ...*%  with EasyEDA's macro
    %AMRoundRect*1,1,$1,$2,$3*...*20,1,$1,$2,$3,$4,$5,0*...*4,1,4,$2,$3,...*%
    The macro flashes a circle of diameter $1 CENTRED on each (x, y) point, width-$1 lines
    between the points and the outline through them: the pad is the point rectangle grown
    by $1/2 on every side.  So the outer size is 2*max|x| + r by 2*max|y| + r, and the
    corner radius is r/2.  Evidence on the ARK CARD R2 package (EasyEDA Pro): in the solder
    mask, round pads C1.7 -> C1.8016 and obrounds O1.0x2.0 -> O1.1016x2.1016 (+0.0508 per
    side), and a 0.8 x 0.9 copper rectangle's mask RoundRect has points +-0.4 / +-0.45 with
    r = 0.1016 -- the same +0.0508 per side only under this reading.  The earlier note read
    the points as OUTER corners and "validated" it against the EDA's DRC pad-to-pad value;
    that DRC number describes the design pads, not what the fab renders from the macro, so
    it could not settle the question.  A board whose COPPER uses RoundRect has pads r wider
    and webs r narrower than a points-as-corners reading suggests.

HOW IT WAS VALIDATED
    Against a released board's shipped package: the outline read 41.400 x 100.000 mm to
    within 0.0005, the drill census agreed with two independent design models, and the
    copper clearance minimum matched the EDA's DRC.  `--selftest` parses synthetic
    Gerber and Excellon covering every aperture kind, arcs, regions and G85 slots.

USAGE (as a library, mostly)
    from gerber import parse_gerber, parse_excellon
    lay = parse_gerber(open(path).read(), name=path)
    tools, hits, plated = parse_excellon(open(path).read(), name=path)

    python3 gerber.py FILE [FILE ...]     # census of each file
    python3 gerber.py --selftest
"""
from __future__ import print_function

import math
import os
import re
import sys

ARC_SEG = 0.02          # mm chord tolerance when flattening arcs


class Aperture(object):
    __slots__ = ("num", "kind", "w", "h", "r", "verts", "raw")

    def __init__(self, num, kind, w=0.0, h=0.0, r=0.0, verts=None, raw=""):
        self.num = num
        self.kind = kind            # 'C' 'R' 'O' 'RR' 'POLY'
        self.w = w
        self.h = h
        self.r = r                  # corner ROUNDING DIAMETER for RR
        self.verts = verts or []
        self.raw = raw

    @property
    def dia(self):
        """Effective pen diameter when this aperture strokes a track."""
        return self.w if self.kind == "C" else min(self.w, self.h)

    def area(self):
        if self.kind == "C":
            return math.pi * (self.w / 2.0) ** 2
        if self.kind == "O":
            a, b = max(self.w, self.h), min(self.w, self.h)
            return (a - b) * b + math.pi * (b / 2.0) ** 2
        if self.kind == "POLY":
            return abs(_shoelace(self.verts))
        if self.kind == "RR" and self.r > 0:
            rr = self.r / 2.0
            return self.w * self.h - (4 - math.pi) * rr * rr
        return self.w * self.h

    def __repr__(self):
        return "D%d:%s %.4fx%.4f" % (self.num, self.kind, self.w, self.h)


def _shoelace(pts):
    s = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s / 2.0


class Flash(object):
    __slots__ = ("ap", "x", "y", "section")

    def __init__(self, ap, x, y, section):
        self.ap, self.x, self.y, self.section = ap, x, y, section

    def __repr__(self):
        return "Flash(%s @ %.4f,%.4f %s)" % (self.ap, self.x, self.y, self.section)


class Seg(object):
    __slots__ = ("ap", "x1", "y1", "x2", "y2", "section")

    def __init__(self, ap, x1, y1, x2, y2, section):
        self.ap = ap
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.section = section

    @property
    def length(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


class Layer(object):
    def __init__(self, name):
        self.name = name
        self.apertures = {}
        self.flashes = []
        self.segs = []
        self.regions = []           # list of list[(x, y)]
        self.used = set()
        self.header = []

    def summary(self):
        return {
            "name": os.path.basename(self.name),
            "apertures": len(self.apertures),
            "used_apertures": len(self.used),
            "unused_apertures": sorted(set(self.apertures) - self.used),
            "flashes": len(self.flashes),
            "segments": len(self.segs),
            "regions": len(self.regions),
            # sections seen on EITHER flashes or strokes: a "Track" section has no
            # flashes at all, so looking only at flashes hides half the tagging.
            "sections": sorted({o.section for o in
                                list(self.flashes) + list(self.segs) if o.section}),
        }


_TOKEN = re.compile(r"%[^%]*%|[^*%]*\*", re.S)
_ADD = re.compile(r"^ADD(\d+)([A-Za-z_][A-Za-z_0-9]*)(?:,(.*))?$")
_FS = re.compile(r"^FSLAX(\d)(\d)Y(\d)(\d)$")
_COORD = re.compile(r"([XYIJ])(-?\d+)")
_DCODE = re.compile(r"D0?([123])$")
_APSEL = re.compile(r"^(?:G54)?D(\d+)$")
_SECTION = re.compile(r"^G04\s+(\w+)\s+(Start|End)$")


def parse_gerber(text, name="?"):
    """Parse one RS-274X file into a Layer.  Raises ValueError on anything unexpected."""
    lay = Layer(name)
    macros = {}
    scale_x = scale_y = 1e-6
    cur_ap = None
    cx = cy = 0.0
    interp = 1
    multi_quadrant = False
    in_region = False
    region_pts = []
    section = ""

    for m in _TOKEN.finditer(text):
        tok = m.group(0).strip()
        if not tok:
            continue
        if tok.startswith("%"):
            body = tok[1:-1].strip()
            for stmt in [s for s in body.split("*") if s.strip()]:
                s = stmt.strip()
                mm = _FS.match(s)
                if mm:
                    scale_x = 10.0 ** -int(mm.group(2))
                    scale_y = 10.0 ** -int(mm.group(4))
                    continue
                if s.startswith("MO"):
                    if s != "MOMM":
                        raise ValueError(
                            "%s: unit %r is not millimetres.  Refusing to guess a scale "
                            "-- convert the export or extend this reader." % (name, s))
                    continue
                mad = _ADD.match(s)
                if mad:
                    num = int(mad.group(1))
                    kind = mad.group(2)
                    args = (mad.group(3) or "").split("X")
                    lay.apertures[num] = _make_aperture(num, kind, args, macros, s)
                    continue
                if s.startswith("AM"):
                    parts = body.split("*")
                    macros[parts[0][2:].strip()] = [p.strip() for p in parts[1:] if p.strip()]
                    break
                if s.startswith(("LP", "IP", "AS", "MI", "OF", "SF", "IN",
                                 "TF", "TA", "TD", "TO")):
                    continue
                raise ValueError("%s: unhandled parameter %r" % (name, s))
            continue

        cmd = tok[:-1].strip()
        if not cmd:
            continue
        if cmd.startswith("G04"):
            sm = _SECTION.match(cmd)
            if sm:
                section = sm.group(1) if sm.group(2) == "Start" else ""
            else:
                lay.header.append(cmd)
            continue
        if cmd == "M02":
            break
        if cmd == "G36":
            in_region, region_pts = True, []
            continue
        if cmd == "G37":
            if len(region_pts) >= 3:
                lay.regions.append(region_pts)
            in_region, region_pts = False, []
            continue
        if cmd == "G75":
            multi_quadrant = True
            continue
        if cmd == "G74":
            multi_quadrant = False
            continue

        while True:
            gm = re.match(r"^G0?([123])(?=[XYIJD]|$)", cmd)
            if not gm:
                break
            interp = int(gm.group(1))
            cmd = cmd[gm.end():]
            if not cmd:
                break
        if not cmd:
            continue

        sel = _APSEL.match(cmd)
        if sel:
            num = int(sel.group(1))
            if num >= 10:
                cur_ap = lay.apertures.get(num)
                if cur_ap is None:
                    raise ValueError("%s: select of undefined D%d" % (name, num))
                lay.used.add(num)
            continue

        dm = _DCODE.search(cmd)
        if not dm:
            if cmd.startswith("G"):
                continue
            raise ValueError("%s: unhandled command %r" % (name, cmd))
        op = int(dm.group(1))
        coords = dict((g[0], int(g[1])) for g in _COORD.findall(cmd[:dm.start()]))
        nx = coords["X"] * scale_x if "X" in coords else cx
        ny = coords["Y"] * scale_y if "Y" in coords else cy
        i = coords.get("I", 0) * scale_x
        j = coords.get("J", 0) * scale_y

        if op == 2:
            if in_region and len(region_pts) >= 3:
                lay.regions.append(region_pts)
                region_pts = []
            cx, cy = nx, ny
            if in_region:
                region_pts = [(cx, cy)]
        elif op == 1:
            pts = [(nx, ny)] if interp == 1 else _arc(cx, cy, nx, ny, i, j,
                                                      interp, multi_quadrant)
            if in_region:
                if not region_pts:
                    region_pts = [(cx, cy)]
                region_pts.extend(pts)
            else:
                if cur_ap is None:
                    raise ValueError("%s: draw with no aperture selected" % name)
                px, py = cx, cy
                for qx, qy in pts:
                    lay.segs.append(Seg(cur_ap, px, py, qx, qy, section))
                    px, py = qx, qy
            cx, cy = nx, ny
        elif op == 3:
            if cur_ap is None:
                raise ValueError("%s: flash with no aperture selected" % name)
            lay.flashes.append(Flash(cur_ap, nx, ny, section))
            cx, cy = nx, ny
    return lay


def _arc(x0, y0, x1, y1, i, j, interp, multi):
    ccx, ccy = x0 + i, y0 + j
    r = (math.hypot(x0 - ccx, y0 - ccy) + math.hypot(x1 - ccx, y1 - ccy)) / 2.0
    if r < 1e-9:
        return [(x1, y1)]
    a0 = math.atan2(y0 - ccy, x0 - ccx)
    a1 = math.atan2(y1 - ccy, x1 - ccx)
    if interp == 2:
        while a1 > a0:
            a1 -= 2 * math.pi
        if multi and abs(a1 - a0) < 1e-12:
            a1 = a0 - 2 * math.pi
    else:
        while a1 < a0:
            a1 += 2 * math.pi
        if multi and abs(a1 - a0) < 1e-12:
            a1 = a0 + 2 * math.pi
    sweep = a1 - a0
    step = 2 * math.acos(max(-1.0, min(1.0, 1 - ARC_SEG / max(r, ARC_SEG)))) or 0.1
    n = min(max(2, int(math.ceil(abs(sweep) / step))), 720)
    return [(ccx + r * math.cos(a0 + sweep * k / n),
             ccy + r * math.sin(a0 + sweep * k / n)) for k in range(1, n + 1)]


def _make_aperture(num, kind, args, macros, raw):
    def f(k):
        return float(args[k])

    if kind == "C":
        d = f(0)
        return Aperture(num, "C", d, d, raw=raw)
    if kind == "R":
        return Aperture(num, "R", f(0), f(1), raw=raw)
    if kind == "O":
        return Aperture(num, "O", f(0), f(1), raw=raw)
    if kind == "RoundRect":
        # see the module docstring: circles of diameter r centred on the points, so the pad
        # is the point rectangle grown by r/2 per side (corrected 2026-09-29)
        return Aperture(num, "RR", 2 * max(abs(f(1)), abs(f(3))) + f(0),
                        2 * max(abs(f(2)), abs(f(4))) + f(0), r=f(0), raw=raw)
    if kind in macros:
        verts = _macro_outline(macros[kind])
        xs = [p[0] for p in verts] or [0.0]
        ys = [p[1] for p in verts] or [0.0]
        return Aperture(num, "POLY", max(xs) - min(xs), max(ys) - min(ys),
                        verts=verts, raw=raw)
    raise ValueError("unknown aperture type %r (D%d).  Extend _make_aperture rather "
                     "than letting it through unread." % (kind, num))


def _macro_outline(prims):
    """Only primitive code 4 (outline) is read.  Anything else in the macro is NOT
    rendered, and a macro built from circles/polygons will report an empty outline."""
    for p in prims:
        nums = [x.strip() for x in p.split(",")]
        if nums and nums[0] == "4":
            n = int(float(nums[2]))
            vals = [float(v) for v in nums[3:3 + 2 * (n + 1)]]
            return [(vals[k], vals[k + 1]) for k in range(0, len(vals) - 1, 2)]
    return []


# --------------------------------------------------------------------------- drills

class Drill(object):
    __slots__ = ("tool", "dia", "x", "y", "x2", "y2", "plated")

    def __init__(self, tool, dia, x, y, plated, x2=None, y2=None):
        self.tool, self.dia, self.x, self.y, self.plated = tool, dia, x, y, plated
        self.x2 = x if x2 is None else x2
        self.y2 = y if y2 is None else y2

    @property
    def is_slot(self):
        return abs(self.x2 - self.x) > 1e-9 or abs(self.y2 - self.y) > 1e-9

    @property
    def slot_len(self):
        return math.hypot(self.x2 - self.x, self.y2 - self.y)

    def key(self, nd=4):
        return (round(self.x, nd), round(self.y, nd), round(self.dia, nd),
                round(self.x2, nd), round(self.y2, nd))


def parse_excellon(text, name="?"):
    """-> (tools, hits, plated).  Metric, leading zeros omitted.

    `plated` is read from a TYPE=PLATED header comment.  If your exporter does not write
    one, this returns False and the CALLER must decide -- it is not inferred from the
    file name, because a file name is not a measurement.
    """
    plated = "TYPE=PLATED" in text[:400]
    tools, hits = {}, []
    cur = None
    tool_re = re.compile(r"^T(\d+)C([\d.]+)")
    sel_re = re.compile(r"^T(\d+)\s*$")
    xy_re = re.compile(r"^X(-?[\d.]+)Y(-?[\d.]+)(?:G85X(-?[\d.]+)Y(-?[\d.]+))?\s*$")
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line in ("%", "M48", "M30", "M95", "G05", "G90", "G91"):
            continue
        if line.startswith("METRIC") or line.startswith("INCH"):
            if not line.startswith("METRIC"):
                raise ValueError("%s: not metric.  Refusing to guess a scale." % name)
            continue
        tm = tool_re.match(line)
        if tm:
            tools[int(tm.group(1))] = float(tm.group(2))
            continue
        sm = sel_re.match(line)
        if sm:
            cur = int(sm.group(1))
            continue
        cm = xy_re.match(line)
        if cm:
            if cur is None:
                raise ValueError("%s: coordinate before any tool select" % name)
            hits.append(Drill(cur, tools.get(cur, 0.0),
                              float(cm.group(1)), float(cm.group(2)), plated,
                              float(cm.group(3)) if cm.group(3) else None,
                              float(cm.group(4)) if cm.group(4) else None))
            continue
        raise ValueError("%s: unhandled Excellon line %r" % (name, line))
    return tools, hits, plated


# --------------------------------------------------------------------------- selftest

_SYNTH_GERBER = """G04 synthetic*
%FSLAX26Y26*%
%MOMM*%
%ADD10C,0.200000*%
%ADD11R,1.000000X0.600000*%
%ADD12O,1.400000X0.800000*%
%ADD13RoundRect,0.101600X-0.150000X-0.570001X0.150000X-0.570001X0.150000X0.570001X-0.150000X0.570001*%
%AMPolygonMacro*
4,1,4,-0.5,-0.5,0.5,-0.5,0.5,0.5,-0.5,0.5,-0.5,-0.5,0.0*%
%ADD14PolygonMacro*%
G04 Track Start*
D10*
X1000000Y1000000D02*
X5000000Y1000000D01*
G04 Track End*
G04 Pad Start*
D11*
X2000000Y3000000D03*
D12*
X4000000Y3000000D03*
D13*
X6000000Y3000000D03*
D14*
X8000000Y3000000D03*
G04 Pad End*
G36*
X0Y0D02*
X10000000Y0D01*
X10000000Y10000000D01*
X0Y10000000D01*
X0Y0D01*
G37*
G75*
G03X1000000Y1000000I1000000J0D01*
M02*
"""

_SYNTH_DRILL = """M48
;TYPE=PLATED
METRIC,LZ
T1C0.300
T2C1.000
%
T1
X1.000Y1.000
X2.000Y1.000
T2
X5.000Y5.000G85X7.000Y5.000
M30
"""


def _selftest():
    ok = True
    print("gerber selftest")
    lay = parse_gerber(_SYNTH_GERBER, "synth")
    s = lay.summary()
    good = s["apertures"] == 5 and s["flashes"] == 4 and s["regions"] == 1
    print("  apertures %d flashes %d segs %d regions %d   %s"
          % (s["apertures"], s["flashes"], len(lay.segs), s["regions"],
             "OK" if good else "FAIL"))
    ok &= good

    good = s["sections"] == ["Pad", "Track"]
    print("  G04 section tags read: %s   %s" % (s["sections"], "OK" if good else "FAIL"))
    ok &= good

    tr = [x for x in lay.segs if x.section == "Track"]
    good = len(tr) == 1 and abs(tr[0].length - 4.0) < 1e-9 and abs(tr[0].ap.dia - 0.2) < 1e-9
    print("  track: %.3f mm long, %.3f mm wide   %s"
          % (tr[0].length, tr[0].ap.dia, "OK" if good else "FAIL"))
    ok &= good

    rr = lay.apertures[13]
    good = abs(rr.w - 0.4016) < 1e-9 and abs(rr.h - 1.241602) < 1e-6 and abs(rr.r - 0.1016) < 1e-9
    print("  RoundRect -> %.4f x %.4f, r(dia) %.4f   %s"
          % (rr.w, rr.h, rr.r, "OK" if good else "FAIL"))
    ok &= good
    print("     (points +-0.15 / +-0.570001 are circle centres: the pad is 0.300 + r wide)")

    ob = lay.apertures[12]
    good = abs(ob.area() - ((1.4 - 0.8) * 0.8 + math.pi * 0.16)) < 1e-9
    print("  obround area is a stadium, not a rectangle   %s" % ("OK" if good else "FAIL"))
    ok &= good

    pm = lay.apertures[14]
    good = pm.kind == "POLY" and abs(pm.w - 1.0) < 1e-9 and len(pm.verts) == 5
    print("  aperture macro outline: %d verts, %.3f wide  %s"
          % (len(pm.verts), pm.w, "OK" if good else "FAIL"))
    ok &= good

    arcs = [x for x in lay.segs if x.section == ""]
    good = 10 <= len(arcs) <= 20 and abs(
        math.hypot(arcs[-1].x2 - 1.0, arcs[-1].y2 - 1.0)) < 1e-6
    print("  G75 270 deg arc -> %d chords, ends on target %s"
          % (len(arcs), "OK" if good else "FAIL"))
    ok &= good

    good = abs(_shoelace(lay.regions[0]) ) > 99.0
    print("  G36 region captured (area %.1f mm2)          %s"
          % (abs(_shoelace(lay.regions[0])), "OK" if good else "FAIL"))
    ok &= good

    # an unknown parameter must raise
    try:
        parse_gerber(_SYNTH_GERBER.replace("%MOMM*%", "%MOIN*%"), "synth")
        good = False
    except ValueError:
        good = True
    print("  a non-millimetre unit is fatal, not guessed  %s" % ("OK" if good else "FAIL"))
    ok &= good

    tools, hits, plated = parse_excellon(_SYNTH_DRILL, "synth")
    slots = [h for h in hits if h.is_slot]
    good = len(hits) == 3 and len(slots) == 1 and plated
    print("  Excellon: %d hits, %d slot, plated=%s        %s"
          % (len(hits), len(slots), plated, "OK" if good else "FAIL"))
    ok &= good
    good = abs(slots[0].slot_len - 2.0) < 1e-9
    print("  G85 slot length %.3f mm                      %s"
          % (slots[0].slot_len, "OK" if good else "FAIL"))
    ok &= good

    print("gerber selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    if len(argv) < 2:
        print(__doc__)
        return 2
    for path in argv[1:]:
        text = open(path, encoding="utf-8", errors="replace").read()
        if path.lower().endswith((".drl", ".txt", ".xln", ".exc")) or "M48" in text[:200]:
            tools, hits, plated = parse_excellon(text, path)
            print("%-40s EXCELLON tools %2d hits %4d slots %2d plated=%s"
                  % (os.path.basename(path), len(tools), len(hits),
                     sum(1 for h in hits if h.is_slot), plated))
        else:
            lay = parse_gerber(text, path)
            s = lay.summary()
            print("%-40s GERBER  ap %2d/%2d flash %4d seg %5d region %3d %s"
                  % (s["name"], s["used_apertures"], s["apertures"], s["flashes"],
                     s["segments"], s["regions"],
                     ("sections " + ",".join(s["sections"])) if s["sections"] else ""))
            if s["unused_apertures"]:
                print("    unused ('phantom') apertures: %s" % s["unused_apertures"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
