# `placement/` — is this layout buildable, and can it be routed?

Placement gates that measure, then report numbers. They do not vote.
A collision-free placement is **not** the acceptance criterion: the project these came
from produced one, and it could not be routed. Read the histograms, not just the
`PASS` lines.

Everything is millimetres. Angles are degrees, counter-clockwise.

---

## The files

| file | what it measures | needs |
|---|---|---|
| `geom2d.py` | shared exact 2D geometry: polygon distance **with containment**, obrounds, capsules, round-rects | stdlib |
| `boardmodel.py` | the neutral **board JSON** every checker reads; derives placed pads, bodies and courtyards | stdlib |
| `import_easyeda.py` | adapter: an EasyEDA Pro export → board JSON (both on-disk dialects) | stdlib |
| `courtyard_check.py` | courtyard separation, pad/drill to outline, **net-blind hole-to-hole** | stdlib |
| `body_clearance.py` | every part against **every** other part's body — no size filter | stdlib |
| `channels.py` | free-span and via-lane statistics against **this board's** rules | stdlib |

`verify/` and `routing/` import `geom2d` and `boardmodel` from here by relative path, so
keep `scripts/` together.

---

## Quick start

```sh
# 1. turn an EDA export into board JSON
python3 import_easyeda.py board.json  path/to/export/PCB  path/to/export/FOOTPRINT

# 2. the three gates
python3 courtyard_check.py board.json --top 10
python3 body_clearance.py  board.json --near 3.0 --top 20
python3 channels.py        board.json --track-width 0.10

# everything self-tests on synthetic input, no board needed
for f in geom2d boardmodel import_easyeda courtyard_check body_clearance channels; do
  python3 $f.py --selftest
done
```

`import_easyeda.py` accepts files or directories and auto-detects the dialect:

* **record** — `{"type":"PAD",…}||{…}|` lines, what `document_save_to_file` writes;
* **array** — `["PAD",id,…]` NDJSON, what a project export writes inside its archive.

Mixed inputs are fine (a live PCB document plus a footprint library from elsewhere).
Components referencing a footprint that is not in the export are **warned about and
skipped**, never silently placed.

---

## The board JSON

One EDA-independent document. Porting the toolkit to another EDA means writing a
sibling of `import_easyeda.py` and nothing else.

```jsonc
{
  "units": "mm",
  "rules":  { "clearance": 0.102, "hole_to_hole": 0.2997, "edge_clearance": 0.30,
              "via_pad": 0.50, "via_drill": 0.30, "pad_to_outline": 0.30,
              "min_courtyard_gap": 0.0 },
  "layers": { "copper": [1,15,16,2], "top": 1, "bottom": 2,
              "solid_planes": [15], "assembly_outline": 48, "silkscreen": [3,4],
              "multi": 12, "board_outline": 11, "mirror_axis": "y" },
  "outline": { "polygon": [[0,0],[41.4,0],[41.4,100],[0,100]] },
  "footprints": { "<id>": { "name": "...", "outline": [[x,y],…], "silk": null,
                            "pads": [ { "num":"1", "elem":"e1", "x":0, "y":0,
                                        "w":0.7, "h":0.8, "angle":0, "shape":"RECT",
                                        "hole": {"w":0.9,"h":0.9,"plated":true} } ],
                            "npth": [ {"x":0,"y":2,"d":1.0} ] } },
  "components": [ { "des":"R1", "footprint":"<id>", "x":10, "y":10,
                    "angle":90, "side":"top" } ],
  "pad_nets": { "R1.1": "VCC", "R1#e1": "VCC" },
  "nets":     { "VCC": [["R1","1"], ["C1","2"]] },
  "tracks":   [ {"net":"VCC","layer":1,"x1":0,"y1":0,"x2":1,"y2":0,"w":0.2} ],
  "vias":     [ {"net":"GND","x":5,"y":5,"drill":0.3,"pad":0.5} ],
  "pours":    [ {"net":"GND","layer":15,"polygons":[]} ]
}
```

**Every number under `rules` and `layers` above is the example project's, shown so the
shape is clear.** They are properties of that board and that fabricator, not defaults
to inherit. `layers.copper` values are that EDA's internal layer ids
(1 = top, 15/16 = inner, 2 = bottom); yours will differ.

`pad_nets` carries two keys per pad — `DES.NUM` and `DES#ELEM` — because a pad is bound
to its net by the footprint **element** id, not the pad number. See the traps below.

---

## The courtyard rule — the one that matters

```
court = bbox( assembly-outline points  ∪  real pad boxes  ∪  hole/slot boxes )
```

Taking the nominal outline alone is **actively wrong**. Two measured cases from the
reference project:

* a castellated module whose layer-48 outline says 25.0 mm while its pads span
  **26.114 mm**;
* a USB-C receptacle whose drilled slots are **1.7 mm** inside **1.0 mm** pads, so the
  hole outline has to be in the union too.

The same error seen from the other side: a tantalum's **land** is 9.23 mm while its
**body** is 7.30 mm, which put a candidate pad 0.21 mm off the board edge. That is why
the model keeps `body` (what physically sits there) and `court` (the union) as separate
things, and why the placement gates use the one that fits the question.

---

## The four tool faults, and where each is fixed

These were all found in the original scripts, on a released board. Each one **passed a
check that was not actually checking**.

### 1. A pickle-cached 3D model measuring the previous release
Fixed in `../verify/mesh3d.py` (see that README). Listed here because the fix that goes
with it is geometric: **a footprint's courtyard is not the part.** A barrel jack's
layer-48 courtyard stopped at x 38.350 while its moulded body reached x 41.400 — a
3.05 mm overhang in which three passives had been legally placed. `body_clearance.py`
and `mesh3d.py` are not substitutes for each other; run both.

### 2. A polygon-distance function blind to full containment
`geom2d.poly_distance`. Distance was computed edge-to-edge only, so a polygon lying
**wholly inside** another read as positively clear: a large tantalum land that had
entirely swallowed an 0805 pad still reported **0.22 mm** of clearance, and the gate
consuming that number passed the board. Containment is now tested first, in both
directions, and returns `0.0`. `geom2d.py --selftest` prints the wrong answer the old
code gave (4.000 mm) next to the right one, so the failure is visible rather than
described.

### 3. A placement gate that only tested large module bodies
`body_clearance.py`. The original collected "module bodies" as those with area ≥ 20 mm²
and tested other parts only against those. An 0603 was therefore legally placed
**underneath a 3.5 × 2.8 mm tantalum**, whose body is 9.8 mm²: the tantalum is not a
module, so nothing was looking. There is **no size filter** now — every part against
every part, 16 110 pairs on a 180-part board, seconds. `--min-area` exists only to
reproduce the broken behaviour for comparison and says so loudly when used.

### 4. A raster fill leaking through a plane's keyhole cut-ins
Fixed in `../verify/raster.py`; see that README.

### And the family member that lives here
**The clearance sweep skips same-net pairs — correct for copper, wrong for holes.**
A fabricator's hole-to-hole rule applies to *any* two holes. Three vias a router stacked
on one node (two 0.02 mm apart, two coincident) passed the same-net-skipping sweep and
failed the real DRC. `courtyard_check.py`'s `hole_to_hole` **never looks at a net**, and
includes vias, pad holes and NPTH alike.

---

## Other traps encoded in these scripts

* **`padAngle` is the pad's render rotation; a "relative" angle is not.** Reading the
  wrong one made half a module's pads overlap.
* **A zero-width `hole` record is not a hole.** A module's 88 SMD lands each carried an
  empty hole dict; counting them added 88 phantom drills to the census.
* **Stored units are mil**, in both export dialects, *including inside footprint
  documents whose canvas record claims mm*. Converted once, in the adapter.
* **Bottom-side mirroring is Y for EasyEDA Pro** (`layers.mirror_axis = "y"`, the
  default since 2026-09-28). Measured on a 6-layer board with 64 bottom-side parts:
  "x" gave 223 false overlaps and 48 false split nets, "y" matched EasyEDA's DRC; the
  same answer as `references/02-review.md` §2d. Older reference board models negated X,
  so it stays a config key — re-measure on an asymmetric bottom part if an export
  disagrees. Get it wrong and every bottom part is 180° out, which looks plausible on a
  symmetric footprint.
* **A multi-primitive assembly outline is reduced to its bounding box** by the adapter.
  Conservative for containment (a false overlap, never a false clearance) and wrong if
  you need the real notch — for that, use the 3D solid.
* **The outline test uses the outline's bounding box.** On a board with a cutout or a
  rounded corner that is *optimistic*, the only place in this toolkit where a limitation
  errs that way. Treat a marginal edge result as unproven.

---

## Reading `channels.py`

The via-lane width is computed, never assumed:

```
via needs  = via_pad + 2 × clearance
lanes(span) = floor( (span − clearance) / (track_width + clearance) )
```

The measured case from the reference project, reproduced by `--selftest`: a **0.55 mm**
channel holds exactly **one** 0.254 mm track and **two** 0.10 mm tracks. Dropping the
signal width was the change that let the board route — and nothing in a
collision-checking placement gate would ever have said so.

`ESCAPE` lists parts with no side offering a via-capable corridor. A part with no escape
side cannot get its pads to another layer, however clean its clearances look.
