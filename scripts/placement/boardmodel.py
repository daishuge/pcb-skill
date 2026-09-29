# -*- coding: utf-8 -*-
"""The neutral board model every checker in this toolkit consumes.

WHAT THIS MEASURES
    Nothing on its own.  It defines one EDA-independent JSON document ("board JSON"),
    loads it, validates it, and derives the placed geometry the gates need:
      * each part's PAD outlines in board coordinates,
      * each part's BODY polygon (the assembly outline -- what physically sits there),
      * each part's COURTYARD box = union(assembly outline, real pad boxes, hole boxes),
      * every drilled hole on the board, plated and not.

WHAT THIS CANNOT SEE
    * Anything the exporter did not write.  If a footprint has no assembly outline this
      falls back to silkscreen, then to the pad bounding box, and says which it used in
      `court_source`.  A silk-derived body can be wrong by whatever the librarian drew.
    * The 3D solid.  A courtyard is NOT the part: on the reference board a barrel jack's
      layer-48 courtyard stopped 3.05 mm short of its own moulded body, and three
      passives were legally placed inside that overhang.  Use `verify/mesh3d.py` for the
      real solid; this module only knows the 2D library drawing.
    * Copper pours.  `pours` is carried through for the Gerber-side tools but the
      placement gates ignore it -- placement happens before the pour exists.
    * Net *intent*.  `pad_nets` is what the PCB holds; `nets` is what the schematic
      says.  Comparing them is `verify/pad_reconcile.py`'s job, not this module's.

HOW IT WAS VALIDATED
    The schema is a distillation of two independently written board models from a
    released 4-layer board (one by the designer, one by an independent reviewer), whose
    pad positions agreed to 0.0004 mm and whose drill counts agreed exactly.  The
    courtyard-union rule below is the one that caught a module whose pads span 26.114 mm
    while its nominal body outline claims 25.0 mm.  `--selftest` builds a synthetic
    board in memory and checks the derived geometry against hand-computed numbers.

COURTYARD RULE -- the important one
    court = bbox( assembly-outline points  U  real pad boxes  U  hole/slot boxes )
    Taking the nominal outline alone is ACTIVELY WRONG.  Two measured cases:
      * a castellated module whose outline says 25.0 mm and whose pads span 26.114 mm;
      * a USB-C receptacle whose 1.7 mm drilled slots are WIDER than the 1.0 mm pads
        that carry them, so the hole outline has to be in the union too.
    A tantalum's land (9.23 mm) being longer than its body (7.30 mm) is the same class
    of error seen from the other side, and is why `envelope` exists.

UNITS AND CONVENTIONS
    Millimetres everywhere.  Angles are degrees, counter-clockwise, applied to
    footprint-local coordinates.  A bottom-side part is mirrored before rotation, on the
    axis named by `layers.mirror_axis` (see geom2d.mirror_point for why that is a config
    key and not a constant).
"""
from __future__ import print_function

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom2d as G                                                    # noqa: E402

SCHEMA_VERSION = 1

DEFAULT_RULES = {
    # every one of these is a board rule, not a law of nature -- override them in the
    # board JSON.  The values shown are only the example project's.
    "clearance": 0.102,          # copper-to-copper, different nets
    "hole_to_hole": 0.2997,      # ANY two holes, same net or not (see padgap checks)
    "edge_clearance": 0.30,      # copper / drill to board outline
    "via_pad": 0.50,
    "via_drill": 0.30,
    "pad_to_outline": 0.30,
    "min_courtyard_gap": 0.0,    # 0 = "must not overlap"; raise it to demand air
}

DEFAULT_LAYERS = {
    "copper": [1, 15, 16, 2],
    "top": 1,
    "bottom": 2,
    "solid_planes": [15],        # never routed on; a router must be told
    "assembly_outline": 48,
    "silkscreen": [3, 4],
    "multi": 12,                 # through-hole / NPTH feature layer
    "board_outline": 11,
    "mirror_axis": "y",          # measured on EasyEDA Pro exports, see geom2d.mirror_point
}


class BoardError(Exception):
    pass


# --------------------------------------------------------------------------- loading

def load(path):
    """Read a board JSON file and return a validated Board."""
    with open(path, encoding="utf-8") as fh:
        return Board(json.load(fh), source=path)


class Placed(object):
    """One placed component, with everything derived once."""

    __slots__ = ("des", "fpid", "x", "y", "angle", "side", "pads", "holes",
                 "body", "court", "court_source", "envelope")

    def __repr__(self):
        return "<Placed %s %s @(%.3f,%.3f) %.0f deg>" % (
            self.des, self.fpid, self.x, self.y, self.angle)


class Board(object):
    def __init__(self, doc, source="<memory>"):
        self.source = source
        self.doc = doc
        self.rules = dict(DEFAULT_RULES)
        self.rules.update(doc.get("rules") or {})
        self.layers = dict(DEFAULT_LAYERS)
        self.layers.update(doc.get("layers") or {})
        self.footprints = doc.get("footprints") or {}
        self.pad_nets = doc.get("pad_nets") or {}
        self.nets = doc.get("nets") or {}
        self.tracks = doc.get("tracks") or []
        self.vias = doc.get("vias") or []
        self.pours = doc.get("pours") or []
        self.outline = (doc.get("outline") or {}).get("polygon") or []
        self._validate(doc)
        self.parts = {}
        for c in doc.get("components") or []:
            p = self._place(c)
            if p.des in self.parts:
                raise BoardError("duplicate designator %r" % p.des)
            self.parts[p.des] = p

    # ------------------------------------------------------------------ validation
    def _validate(self, doc):
        if doc.get("units", "mm") != "mm":
            raise BoardError("only millimetre board JSON is supported, got units=%r"
                             % doc.get("units"))
        for des_i, c in enumerate(doc.get("components") or []):
            for k in ("des", "footprint", "x", "y"):
                if k not in c:
                    raise BoardError("component #%d is missing %r" % (des_i, k))
            if c["footprint"] not in self.footprints:
                raise BoardError("component %s references unknown footprint %r"
                                 % (c["des"], c["footprint"]))
        if self.outline and len(self.outline) < 3:
            raise BoardError("outline polygon needs at least 3 points")

    # ------------------------------------------------------------------ placement
    def _local_to_board(self, lx, ly, part_x, part_y, angle, side):
        if side == "bottom":
            lx, ly = G.mirror_point(lx, ly, self.layers.get("mirror_axis", "y"))
        dx, dy = G.rot(lx, ly, angle)
        return (part_x + dx, part_y + dy)

    def _place(self, c):
        p = Placed()
        p.des = str(c["des"])
        p.fpid = c["footprint"]
        p.x = float(c["x"])
        p.y = float(c["y"])
        p.angle = float(c.get("angle") or 0.0)
        p.side = c.get("side") or "top"
        fp = self.footprints[p.fpid]

        # --- pads
        p.pads = []
        for pad in fp.get("pads") or []:
            cx, cy = self._local_to_board(float(pad["x"]), float(pad["y"]),
                                          p.x, p.y, p.angle, p.side)
            # A pad's own rotation adds to the part's.  Use the pad's RENDER angle, not
            # any "relative" angle the format may also carry: on the reference project
            # reading the relative angle made half a module's pads overlap.
            pang = p.angle + float(pad.get("angle") or 0.0)
            if p.side == "bottom":
                pang = (180.0 - float(pad.get("angle") or 0.0) - p.angle) % 360.0
            poly = G.pad_outline(pad.get("shape", "RECT"), cx, cy,
                                 float(pad.get("w") or 0.0), float(pad.get("h") or 0.0),
                                 pang, float(pad.get("corner_radius") or 0.0),
                                 pad.get("polygon"))
            num = str(pad.get("num", ""))
            rec = {
                "des": p.des, "num": num, "elem": pad.get("elem"),
                "x": cx, "y": cy, "angle": pang,
                "w": float(pad.get("w") or 0.0), "h": float(pad.get("h") or 0.0),
                "shape": pad.get("shape", "RECT"),
                "poly": poly, "bbox": G.bbox_of(poly),
                "net": self.pad_nets.get("%s.%s" % (p.des, num), ""),
                "layers": self._pad_layers(pad, p.side),
                "hole": pad.get("hole"),
            }
            p.pads.append(rec)

        # --- holes (plated pad holes + footprint NPTH)
        p.holes = []
        for rec in p.pads:
            h = rec["hole"]
            if not h:
                continue
            hw = float(h.get("w") or 0.0)
            hh = float(h.get("h") or hw)
            if hw <= 0.0:
                # A zero-width hole record is NOT a hole.  Measured: a module's 88 SMD
                # lands each carried an empty hole dict; counting them added 88 phantom
                # drills to the census.
                continue
            p.holes.append({"des": p.des, "num": rec["num"], "kind": "pad",
                            "x": rec["x"], "y": rec["y"],
                            "d": hw, "slot_len": max(hh - hw, 0.0),
                            "plated": bool(h.get("plated", True)),
                            "net": rec["net"]})
        for h in fp.get("npth") or []:
            hx, hy = self._local_to_board(float(h["x"]), float(h["y"]),
                                          p.x, p.y, p.angle, p.side)
            p.holes.append({"des": p.des, "num": None, "kind": "npth",
                            "x": hx, "y": hy, "d": float(h["d"]), "slot_len": 0.0,
                            "plated": False, "net": ""})

        # --- body polygon: the assembly outline, else silk, else the pad bbox
        body_pts, src = None, None
        if fp.get("outline"):
            body_pts = [self._local_to_board(px, py, p.x, p.y, p.angle, p.side)
                        for px, py in fp["outline"]]
            src = "assembly"
        elif fp.get("silk"):
            body_pts = [self._local_to_board(px, py, p.x, p.y, p.angle, p.side)
                        for px, py in fp["silk"]]
            src = "silk"
        if body_pts is None:
            pts = [q for rec in p.pads for q in rec["poly"]]
            if not pts:
                raise BoardError("%s has no outline, no silk and no pads" % p.des)
            bb = G.bbox_of(pts)
            body_pts = [(bb[0], bb[1]), (bb[2], bb[1]), (bb[2], bb[3]), (bb[0], bb[3])]
            src = "pads"
        p.body = body_pts

        # --- COURTYARD: the union rule.  See the module docstring.
        union = list(body_pts)
        for rec in p.pads:
            union += rec["poly"]
        for h in p.holes:
            r = h["d"] / 2.0 + h["slot_len"] / 2.0
            union += [(h["x"] - r, h["y"] - r), (h["x"] + r, h["y"] + r)]
        p.court = G.bbox_of(union)
        p.court_source = src
        p.envelope = p.court           # kept as a separate name: callers asking for the
        # "real area the part needs" should say envelope, not court, so the intent of a
        # future edit is unambiguous.
        return p

    def _pad_layers(self, pad, side):
        lay = pad.get("layer")
        cu = tuple(self.layers["copper"])
        if pad.get("hole") and float((pad.get("hole") or {}).get("w") or 0.0) > 0.0:
            return cu
        if lay == self.layers.get("board_outline") or lay == self.layers.get("multi"):
            return cu
        if side == "bottom":
            return (self.layers["bottom"],)
        return (self.layers["top"],)

    # ------------------------------------------------------------------ accessors
    def outline_bbox(self):
        if self.outline:
            return G.bbox_of(self.outline)
        pts = [q for p in self.parts.values() for q in p.body]
        if not pts:
            raise BoardError("board has neither an outline nor any component")
        return G.bbox_of(pts)

    def all_pads(self):
        for p in self.parts.values():
            for rec in p.pads:
                yield rec

    def all_holes(self, include_vias=True):
        """Every drilled feature on the board.

        Vias are included by default because the hole-to-hole rule does not care what a
        hole is for.  Leaving them out is exactly how three stacked router vias passed a
        clearance sweep and then failed the real DRC.
        """
        for p in self.parts.values():
            for h in p.holes:
                yield h
        if include_vias:
            for v in self.vias:
                yield {"des": None, "num": None, "kind": "via",
                       "x": float(v["x"]), "y": float(v["y"]),
                       "d": float(v.get("drill") or self.rules["via_drill"]),
                       "slot_len": 0.0, "plated": True, "net": v.get("net", "")}

    def bodies(self, min_area=0.0):
        """(designator, body polygon, area mm2) for every part.

        `min_area` defaults to 0.  Do not raise it in a gate.  See body_clearance.py:
        filtering bodies by size is fault 3.
        """
        out = []
        for des, p in sorted(self.parts.items()):
            out.append((des, p.body, G.poly_area(p.body)))
        return [t for t in out if t[2] >= min_area]

    def summary(self):
        holes = list(self.all_holes())
        return {
            "source": self.source,
            "components": len(self.parts),
            "pads": sum(len(p.pads) for p in self.parts.values()),
            "netted_pads": sum(1 for r in self.all_pads() if r["net"]),
            "nets_on_pcb": len({r["net"] for r in self.all_pads() if r["net"]}),
            "tracks": len(self.tracks),
            "vias": len(self.vias),
            "holes_total": len(holes),
            "holes_plated": sum(1 for h in holes if h["plated"]),
            "outline_bbox": [round(v, 4) for v in self.outline_bbox()],
            "court_sources": _count([p.court_source for p in self.parts.values()]),
        }


def _count(seq):
    out = {}
    for v in seq:
        out[v] = out.get(v, 0) + 1
    return out


# --------------------------------------------------------------------------- synthetic

def synthetic_board():
    """A tiny board used by --selftest here and in several sibling scripts.

    It is deliberately built to contain each fault's trigger:
      * MOD1 is a module whose PADS overhang its declared outline (courtyard union),
      * C1 sits entirely UNDER MOD1's body (module-body containment),
      * R1 is a small part whose body is only 1.6 mm2 but which still has C2 under it
        (the "only large bodies were tested" fault),
      * V1/V2 are two vias 0.05 mm apart on the SAME net (net-blind hole-to-hole).
    """
    fp_mod = {
        "name": "MODULE-CASTELLATED",
        # declared body is 6 x 6, but the pads reach x = +-3.5
        "outline": [[-3.0, -3.0], [3.0, -3.0], [3.0, 3.0], [-3.0, 3.0]],
        "pads": [{"num": "1", "x": -3.2, "y": 0.0, "w": 0.6, "h": 1.0, "shape": "RECT"},
                 {"num": "2", "x": 3.2, "y": 0.0, "w": 0.6, "h": 1.0, "shape": "RECT"}],
    }
    fp_0603 = {
        "name": "R0603",
        "outline": [[-0.8, -0.4], [0.8, -0.4], [0.8, 0.4], [-0.8, 0.4]],
        "pads": [{"num": "1", "x": -0.75, "y": 0.0, "w": 0.7, "h": 0.8, "shape": "RECT"},
                 {"num": "2", "x": 0.75, "y": 0.0, "w": 0.7, "h": 0.8, "shape": "RECT"}],
    }
    fp_th = {
        "name": "HDR-1x2",
        "outline": [[-1.27, -1.27], [1.27, -1.27], [1.27, 1.27], [-1.27, 1.27]],
        "pads": [{"num": "1", "x": -1.27, "y": 0.0, "w": 1.5, "h": 1.5,
                  "shape": "OVAL", "hole": {"w": 0.9, "h": 0.9, "plated": True}},
                 {"num": "2", "x": 1.27, "y": 0.0, "w": 1.5, "h": 1.5,
                  "shape": "OVAL", "hole": {"w": 0.9, "h": 0.9, "plated": True}}],
        "npth": [{"x": 0.0, "y": 2.0, "d": 1.0}],
    }
    return {
        "units": "mm",
        "rules": dict(DEFAULT_RULES),
        "layers": dict(DEFAULT_LAYERS),
        "outline": {"polygon": [[0, 0], [30, 0], [30, 30], [0, 30]]},
        "footprints": {"MOD": fp_mod, "R0603": fp_0603, "HDR": fp_th},
        "components": [
            {"des": "MOD1", "footprint": "MOD", "x": 10.0, "y": 10.0, "angle": 0},
            {"des": "C1", "footprint": "R0603", "x": 10.0, "y": 10.0, "angle": 0},
            {"des": "R1", "footprint": "R0603", "x": 22.0, "y": 10.0, "angle": 0},
            {"des": "C2", "footprint": "R0603", "x": 22.0, "y": 10.0, "angle": 90},
            {"des": "J1", "footprint": "HDR", "x": 5.0, "y": 25.0, "angle": 0},
        ],
        "pad_nets": {"MOD1.1": "GND", "MOD1.2": "VCC", "C1.1": "GND", "C1.2": "VCC",
                     "R1.1": "VCC", "R1.2": "OUT", "C2.1": "OUT", "C2.2": "GND",
                     "J1.1": "VCC", "J1.2": "GND"},
        "nets": {"GND": [["MOD1", "1"], ["C1", "1"], ["C2", "2"], ["J1", "2"]],
                 "VCC": [["MOD1", "2"], ["C1", "2"], ["R1", "1"], ["J1", "1"]],
                 "OUT": [["R1", "2"], ["C2", "1"]]},
        "tracks": [{"net": "VCC", "layer": 1, "x1": 10.0, "y1": 14.0,
                    "x2": 22.0, "y2": 14.0, "w": 0.2}],
        "vias": [{"net": "GND", "x": 26.0, "y": 6.0, "drill": 0.3, "pad": 0.5},
                 {"net": "GND", "x": 26.05, "y": 6.0, "drill": 0.3, "pad": 0.5}],
    }


# --------------------------------------------------------------------------- selftest

def _selftest():
    ok = True
    b = Board(synthetic_board())
    s = b.summary()
    print("boardmodel selftest")
    for k in sorted(s):
        print("  %-18s %s" % (k, s[k]))

    mod = b.parts["MOD1"]
    # courtyard union: pads reach 3.2 + 0.3 = 3.5 mm from the origin, body only 3.0
    want = [10.0 - 3.5, 10.0 - 3.0, 10.0 + 3.5, 10.0 + 3.0]
    got = [round(v, 6) for v in mod.court]
    good = all(abs(a - c) < 1e-6 for a, c in zip(want, got))
    print("  %-46s %s   %s" % ("courtyard = union(outline, pads)", got,
                               "OK" if good else "FAIL want %s" % want))
    ok &= good

    body_bb = G.bbox_of(mod.body)
    good = abs(body_bb[2] - 13.0) < 1e-9
    print("  %-46s %s   %s" % ("body stays the DECLARED 6 x 6 outline",
                               [round(v, 3) for v in body_bb], "OK" if good else "FAIL"))
    ok &= good
    good = mod.court[2] > body_bb[2]
    print("  %-46s %s" % ("courtyard is WIDER than the body",
                          "OK (%.3f > %.3f)" % (mod.court[2], body_bb[2]) if good else "FAIL"))
    ok &= good

    # C1 under MOD1
    d = G.poly_distance(mod.body, b.parts["C1"].body)
    good = d == 0.0
    print("  %-46s %.4f mm  %s" % ("C1 body vs MOD1 body (must be 0)", d,
                                   "OK" if good else "FAIL"))
    ok &= good

    # rotated part: C2 is R0603 turned 90 deg, so its courtyard is taller than wide
    c2 = b.parts["C2"]
    w, h = c2.court[2] - c2.court[0], c2.court[3] - c2.court[1]
    good = h > w
    print("  %-46s %.3f x %.3f  %s" % ("90 deg rotation swaps courtyard axes", w, h,
                                       "OK" if good else "FAIL"))
    ok &= good

    # holes: 2 plated pad holes + 1 NPTH + 2 vias = 5
    holes = list(b.all_holes())
    good = len(holes) == 5 and sum(1 for x in holes if x["kind"] == "npth") == 1
    print("  %-46s %d (%s)  %s" % ("hole census incl. vias", len(holes),
                                   _count([x["kind"] for x in holes]),
                                   "OK" if good else "FAIL"))
    ok &= good

    # a zero-width hole record must not be counted
    doc = synthetic_board()
    doc["footprints"]["R0603"]["pads"][0]["hole"] = {"w": 0.0, "h": 0.0}
    n = len(list(Board(doc).all_holes()))
    good = n == 5
    print("  %-46s %d  %s" % ("zero-width hole record ignored", n,
                              "OK" if good else "FAIL (want 5)"))
    ok &= good

    print("boardmodel selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        return _selftest()
    if len(argv) < 2:
        print(__doc__)
        print("usage: python3 boardmodel.py <board.json>   |   --selftest")
        return 2
    b = load(argv[1])
    s = b.summary()
    for k in sorted(s):
        print("%-16s %s" % (k, s[k]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
