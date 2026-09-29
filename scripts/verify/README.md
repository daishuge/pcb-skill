# `verify/` — measure the artefact that gets built

The fabrication package is what the factory makes. Verifying it by asking the EDA that
produced it proves nothing: the same code path made the file and the answer. Everything
here reads the shipped files — Gerber, Excellon, the 3D export — with a parser written
from the spec, so that a disagreement between this and the EDA is *information*.

---

## The files

| file | what it measures | needs |
|---|---|---|
| `gerber.py` | RS-274X and Excellon reader; raises on anything it has not met | stdlib |
| `raster.py` | exact-crossing fill, connected-component labelling, PNG out | **numpy** |
| `clearance.py` | different-copper clearance, pours included, raster-bracket then exact | numpy (via `raster`) |
| `drill_census.py` | per-file census, subset proof, distinct union | stdlib |
| `mask_check.py` | solder-mask opening per pad, expansion histogram, tented vias | stdlib |
| `outline_check.py` | outline size/closure/pen, copper and drills outside the board | stdlib |
| `netlist_assert.py` | must-connect / must-not-connect / must-be-open, from geometry | stdlib |
| `pad_reconcile.py` | pad-by-pad, PCB net map vs. schematic netlist | stdlib |
| `mesh3d.py` | 3D interference from a fresh, explicitly named export — **no cache** | stdlib |

Only `raster.py` and `clearance.py` need numpy; they say so and exit cleanly without it,
and their `--selftest` reports `SKIPPED` rather than failing. Everything else is
standard library. `geom2d` and `boardmodel` come from `../placement`, so keep `scripts/`
together.

---

## Quick start

```sh
GB=path/to/gerber

python3 gerber.py $GB/*.G* $GB/*.DRL                       # census of every file
python3 outline_check.py $GB/*.GKO --size 41.4,100.0 --edge 0.30 \
        --drills $GB/Drill_PTH_Through.DRL $GB/Drill_NPTH_Through.DRL
python3 drill_census.py $GB/*.DRL --budget 621
python3 mask_check.py $GB/Gerber_TopLayer.GTL $GB/Gerber_TopSolderMaskLayer.GTS
python3 clearance.py $GB/Gerber_TopLayer.GTL --rule 0.102 --res 0.01 \
        --board board.json --layer 1
python3 raster.py $GB/Gerber_InnerLayer1.G1 --compare-fills     # the fault-4 detector

python3 pad_reconcile.py board.json --netlist netlist.json
python3 netlist_assert.py board.json assertions.json --plane-nets "GND"
python3 mesh3d.py export/3D_File.obj board.json --expect-vertices 107775

for f in gerber raster clearance drill_census mask_check outline_check \
         netlist_assert pad_reconcile mesh3d; do python3 $f.py --selftest; done
```

The `--size 41.4,100.0`, `--rule 0.102`, `--budget 621` and `--expect-vertices 107775`
values above are **the example project's** — a 41.4 × 100 mm 4-layer board at a
fabricator whose free-drill allowance worked out to 621 holes for that area. Substitute
your own; none of them is a default.

---

## The four tool faults

All four were found in these scripts, on a released board. Each **passed a check that
was not actually checking**. Two are fixed here; the other two are in `../placement/`.

### 1. A pickle-cached 3D model measuring the previous release → `mesh3d.py`

The original hard-coded the previous release's OBJ path **and** cached the parsed mesh
in a pickle beside it. The 3D interference gate silently measured **the wrong board for
an entire release**: 95 430 vertices instead of that board's 107 775, and it reported
**0 interferences on a board that had three**. Re-pointed at a fresh export it
immediately found three passives inside a connector's moulded body.

Three rules follow, and `mesh3d.py` enforces all of them:

1. **the OBJ path is a required argument** — no default, no discovery;
2. **nothing is cached** — not a pickle, not a temp file, not between runs;
3. **the vertex and triangle counts are printed first, every run**, because a stale
   export is invisible unless you can see its size. `--expect-vertices N` makes it
   mechanical: the run fails if the mesh is not the size you expected.

It also sniffs the file: a `.obj` that is really a ZIP (common — some EDAs export mesh +
`.mtl` + textures as one archive) is rejected by name instead of failing deep inside a
float parse. Being handed the wrong file is the exact failure this script exists to
prevent.

The geometric fact that makes the gate necessary at all: **a footprint's courtyard is not
the part.** A barrel jack's layer-48 courtyard stopped at x 38.350 while its solid reached
x 41.400 — a **3.05 mm** overhang, and everything placed in that strip is unbuildable. A
courtyard check will never say so. Clusters overlapping *no* courtyard are therefore
reported, never dropped silently, and parts whose solid overhangs their courtyard by more
than `--overhang` are listed every run.

### 4. A raster fill leaking through a plane's keyhole cut-ins → `raster.py`

An EDA writes a copper plane as **one** G36 contour whose interior holes are reached by
**zero-width keyhole channels**: the same segment appears twice, traversed in opposite
directions. The original fill rounded each edge crossing to a column with
`ceil((x − X0)/RES − 0.5)` and took the parity of a cumulative sum. Mathematically the two
crossings cancel; after independent float evaluation and the `ceil` they can land in
**adjacent columns**, the parity flips, and the plane bleeds through its own moat — so two
physically separate copper regions receive **one label**.

What that cost:

* an isolated analogue-ground via read as **connected to the main ground plane** — a
  short that does not exist;
* every Gerber-side clearance number on the project had been computed on labels that
  merged regions the rule is supposed to separate, so the gap between them **was never
  measured**;
* a via-redundancy analysis called 127 vias redundant when the true number was 122, and
  one of the five was load-bearing and was in the removal set.

`raster.Grid.fill_polys` now collects the **exact float crossings** per scanline, sorts
them, and fills the spans between consecutive pairs. Coincident edges then open and
immediately close a zero-width span, which is what the Gerber means.

**The leak is alignment-dependent and does not reproduce from clean synthetic geometry —
which is exactly why it survived several releases.** So the old fill is kept, clearly
marked and never called by a check, and there is an operational detector:

```sh
python3 raster.py LAYER.G1 --compare-fills
```

It rasterises the same layer both ways and reports any component the two disagree about.
**Any disagreement at all is the bug.** Run it per export; a layer that agreed last time
proves nothing about this one. (On the example project's mid-project package all four
copper layers agree; the leak was found on a later export of the same board.)

### 2 and 3 — containment blindness, and size-filtered body checks

Both live in `../placement/`; see that README. `clearance.py` depends on fix 2:
`geom2d.poly_distance` tests containment before it measures any edge.

---

## Two more faults these scripts encode

**An obround is not a rectangle.** Modelling a stadium-shaped pad by its bounding
rectangle grows four corners it does not have. That single mistake produced **eleven
phantom clearance violations** on a released board, every one of them around SOIC/TSSOP
lands and every one of them nonsense. `clearance._flash_poly` has a real obround branch.

**Pour copper cannot be attributed by pour-boundary containment.** Asking "which pour
outline contains this point" is ambiguous wherever a lower-priority pour legitimately
fills the gaps a higher-priority one leaves: ground fill inside an analogue-ground zone's
rectangle got labelled analogue, and same-net copper abutting itself then looked like a
violation. `clearance.py` never asks that question — it attributes copper by **connected
component**, which is a physical fact, and finds an interior point by scanline rather than
by centroid (a concave pour's centroid is frequently outside it, and a vertex sits on the
boundary where the label is ambiguous).

**One drill file can be a strict subset of another.** On the reference board the via file
(517 hits) is entirely contained in the PTH file (526 hits) — summing them gave 1057 where
the truth was 540, the difference between comfortably inside a fabricator's free-drill
allowance and over it. `drill_census.py` reports each file separately, **proves** the
subset relation for every ordered pair, and reports the union as *the* number. A G85 line
is one drilled feature, not two holes.

---

## Blind spots, per script

* **`gerber.py`** — raises on an unhandled parameter rather than skipping it, on purpose:
  a reader that silently ignores what it does not understand will happily report a clean
  board it never read. It does **not** model polarity (`%LPC` is accepted and ignored, so
  a clear-polarity cut-out would read as solid), step-and-repeat, or aperture-macro
  primitives other than the outline (code 4). Non-metric files are refused, not scaled.
  `RoundRect` follows the macro EasyEDA writes into the file: a circle of diameter `r`
  centred on each of the four points, width-`r` lines between them and the outline through
  them, so the pad is the point rectangle grown by `r/2` (outer size `2*max|x| + r`). An
  earlier note read the points as outer corners and matched that to the EDA's DRC value;
  the DRC describes the design pads, not what the fab renders, so it proved nothing. The
  outer size is exact only for axis-aligned instances; a rotated RoundRect gets a bounding
  box.
* **`raster.py`** — **resolution is a ceiling on truth.** At 10 µm a 5 µm sliver is
  invisible and two regions 5 µm apart may merge. Any conclusion tighter than one pixel
  must be re-measured exactly. A label is copper, not a net.
* **`clearance.py`** — one layer at a time; no inter-layer anything. Sites are *found* by
  raster, so a pair under one pixel apart may be labelled as touching and never measured.
  Without `--board` it reports gaps between copper **islands** (the manufacturing
  question); with it, same-net pour pinches are separated out and listed rather than
  counted as violations, and copper claimed by two nets is reported first.
* **`drill_census.py`** — plating comes only from a `TYPE=PLATED` header comment; if your
  exporter omits it this reports `False` and you decide, because a file name is not a
  measurement. No aspect-ratio or minimum-drill rules.
* **`mask_check.py`** — matches a mask flash to a pad by centre within `--tol` (0.02 mm).
  A deliberately offset opening is reported as "no opening", which is the safe direction.
  It does **not** check mask slivers between openings, or that an opening is big enough
  for assembly. Pads drawn as regions rather than flashes are invisible; compare the flash
  count against the board model's pad count.
* **`outline_check.py`** — uses the outline **polygon** when the path is a single closed
  stroke, otherwise its bounding box, and says which. Cutouts, milled slots, V-scoring and
  panel rails are not modelled. The cut follows the stroke **centre**, so the finished
  board is the reported extent minus one pen width; both numbers are printed.
* **`netlist_assert.py`** — physical connectivity only. No resistance, no components: a
  must-connect *through* a series part correctly fails, so assert the two halves
  separately. **An empty assertion file passes vacuously and proves nothing** — write the
  negative assertions too. A board that has never been asked a must-not-connect question
  has not been checked for shorts.
* **`pad_reconcile.py`** — refuses to run with only one source, by design. Both sides can
  agree and both be wrong. A footprint whose pad numbering does not match its symbol's pin
  numbering is invisible here, because both sides use the same names; what catches that is
  a geometric pad-by-pad check against the EDA's own reported pad coordinates.
* **`mesh3d.py`** — parts are compared as axis-aligned **boxes**, so two interleaving
  L-shaped bodies read as interfering when they do not; every finding needs an eye on the
  render. A part with no 3D model contributes no cluster and is **not checked** — the
  count of parts carrying a solid is printed against the board's part count, and the
  difference is yours to explain. Nominal and rigid: no flex, tilt or tolerance.
