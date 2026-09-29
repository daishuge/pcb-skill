# 05 — Driving EasyEDA Pro over MCP: the trap list

Read this before the first write. Every entry was paid for with hours of a session's time, and every
one of them is a case where **the tool reported success and the design was wrong**.

Versions where these were measured: EasyEDA Pro 3.2.186, extension 1.5.13, macOS, standalone
(`HALF_OFFLINE`) deployment, driven through the `easyeda-agent` MCP bridge. Behaviour may differ on
other builds — but the *class* of failure will not, so keep the guards even if a specific symptom is
gone.

---

## Three rules that cover most of it

1. **A return value is not evidence.** Every "success" below was returned by a call that did nothing,
   did half of it, or answered about a different document.
2. **Read the document back and compare structurally.** Record counts, the full designator set, and
   the net-per-pad map — before and after.
3. **The netlist is the instrument, not the DRC.** DRC passes on boards with shorted nets.

---

## Connectivity and the schematic

### T1 — Net **ports** silently merge nets at scale. Use net **flags**.

**Symptom.** A schematic with 149 components, 109 nets and **256 net ports** passed DRC with zero
errors and looked correct to the eye. The EDA's own netlist export resolved five nets wrongly:

```
BL_SW    -> merged into TF_PWR      (backlight switch node shorted to the card rail)
BL_COMP  -> merged into GND
I2S_DOUT -> merged into GND         (I2S data shorted to ground)
U0TXD    -> merged into GND
SD_D3    -> merged into BT_CON
```

**How it was caught.** 203 must-connect + 37 must-not-connect + 18 must-be-open assertions run
against `sch_get_netlist`. Nothing else in the toolchain reported anything.

**Cause, as far as it was narrowed.** Not geometry. Ruled out by measurement, in this order:
coincident wire endpoints (0), stubs crossing foreign stubs (0), stubs passing through foreign pins
(0), coincident terminators (0), stale back-references (all empty), sheet-frame overflow (enlarging
the frame changed nothing), and layout in general — rebuilding the identical netlist at 12 columns
instead of 6, halving the page height and doubling its width, produced **exactly the same five broken
nets**. Small pages are unaffected: a single band resolved all 20 of its nets perfectly. **The
threshold sits between 180 and 263 terminators.**

**Guard.** Terminate every net with a **net flag**, never a net port. Replacing all 256 ports with
flags made all 109 nets resolve and all 258 assertions pass. And regardless: **never accept a
schematic that has only been eyeballed or only DRC'd — assert against the exported netlist.**

**Related:** `sch_create_net_flag` **negates the requested rotation** — ask for 270 to get 90. Net
ports hide this because 0 is its own negation. Verify by reading the bounding box back.

### T2 — `sch_run_drc` is asynchronous with respect to its own return value

**Symptom.** The first call after the document changes returns whatever the DRC panel still holds —
the *previous* document's result, or a partial one. The same 149-part page returned "3 warnings"
twice and "1 error + 21 warnings" twelve times in one session; an empty page returned "passed / 0",
then "20 warnings", then "4".

**Guard.** Re-run until the same `(errors, warnings)` pair repeats N times in a row before believing
it. Reading it once is how a schematic gets declared clean when it is not.

**Two more DRC facts on this build:**

- **DRC is project-wide, not per page.** The only honest claim is "zero errors project-wide". An
  empty PCB document in the same project contributes a constant couple of warnings to every
  schematic DRC run — attribute constants by ablation (build a page with one resistor and measure
  the floor) rather than explaining them away.
- **`pcb_run_drc` with a `limit` truncates the tree BEFORE the connection errors**, so a limited run
  reports only the last categories. Run it unlimited and reduce the dump yourself.

### T3 — `sch_get_netlist` mutates the schematic when unique IDs are stamped too low

**Symptom.** With generated unique IDs starting at `gge1001…`, fetching the netlist **renamed one
resistor to `R1` and handed a transistor's uniqueId another part's identity**, so that transistor
vanished from the netlist entirely.

**How it was caught.** Push a verified document → fetch the netlist → re-read the document and diff:
`changed: ['R1', 'R504']`.

**Cause.** ID collision with the project's own allocator, which is **page-local** and will happily
issue an ID below the project maximum. A previous iteration saw a create return `gge8117` against a
project maximum of `gge8500`.

**Guard.** Measure the project's maximum unique ID and stamp well above it (the reference project
used `gge90001…`). Then re-read the document after any query that could allocate.

### T4 — geometry read from a *library* document silently mirrors the part

**Symptom.** A symbol document's pin `y` is in the runtime axis (y **down**); the schematic API is
y **up**. Deriving pin offsets from the library document mirrors the part, and the push still reports
success. It cost a whole page — a module wired end-for-end and two MOSFETs with source and drain
swapped.

**Guard.** **Read pin coordinates back from a placed instance, never from a library document.**

**Related:** pin *span* is per-part, not per-package. A 1 µF 0603 had ±15 while another 0603 had ±20,
and one diode was −40 left / +30 right. Getting the direction wrong breaks connections silently, and
DRC returns an unchanged count because orphan stubs still land on many-pin nets. Only a connectivity
query catches it.

---

## Layers, rules and the PCB

### T5 — a "4-layer" board whose inner layers do not exist

**Symptom.** The design rules said four layers. The physical stack-up record said four layers. The
stack-up manager showed four layers. **The inner layers' `layerStatus` was `0` — they were disabled
and copper could not be placed on them.** The routing preference still listed only the outer layers.

**Consequence if missed:** hours of autorouting on a board that is electrically two layers.

**Guard.** **Before routing, read `layerStatus` directly.** The rule set and the physical stack-up
record can each contradict it, and when they conflict, `layerStatus` decides. Set the copper count
explicitly, then verify by readback — and again after an application restart.

### T6 — the physical stack-up API is a stub

**Symptom.** A review found the document's physical stack described a **two-layer** board (one
59.449 mil dielectric; inner layers at `0, 0, 0, 0`) while the copper was four-layer. The obvious fix
— set it through the API — does not exist:

> Every physical-stacking method in the shipped SDK is a stub, and a direct write to the
> layer-physics record **reverts on cold restart** (it is GUI-only state).

**Guard, in two parts.** First, **verify the consequence rather than the symptom**: the Gerber export
contained exactly 4 copper files, so nothing wrong reached the fab. Second, **anything the file
cannot carry becomes a named human checklist item at the order step** — here, selecting the correct
stack-up on the order form (see `03-jlc-manufacturing.md` §10).

### T7 — `PAD_NET` is keyed by element id, and one pad number can be many lands

**Symptom.** A record reads `["PAD_NET", componentElementId, padNumber, netName, padElementId, flag]`
— the net is the *fourth* field and the pad is identified by the *fifth*, the element id.

Building a dictionary keyed by **pad number** silently collapses multi-element pads. A USB-C shell's
four anchor lands all share pad number 1; another connector had **nine sub-pads under one number**.
One tool that did this counted 402 pads where the board has 935, and a hole-clearance check that used
a union bounding box for "pad 1" claimed every hole between the four shell lands as ground — and hid
the one real violation.

**Guard.** Key by element id. Treat each land as its own object for every geometric check.

### T8 — a pad is not its bounding rectangle

**Symptom.** The tool emits `RECT` (optionally corner-rounded), `OVAL` (a stadium), `ELLIPSE` and
`POLYGON`, and the autorouter honours the real outline. A 45° track cleared a SOIC land by exactly
0.102 mm against the true rounded end and appeared to *overlap* it by 0.043 mm against a plain
rectangle — **16 false violations from that one shortcut.** On the Gerber side the same error class
produced 11 phantom violations including a 0.0004 mm "short".

**Guard.** Carry every land as a core box plus a corner radius (its true outline is the core swept by
a disc), and give the obround aperture its own branch in any Gerber reader.

### T9 — rotation sign differs between the schematic and the PCB domains

**Symptom.** Schematic exports store **clockwise**. On the PCB, bottom-side parts are **mirrored in Y
and rotated counter-clockwise**. Mirror-Y-then-CCW is algebraically identical to CW-then-mirror-Y, so
**every bottom-side check passes under either rule** — only a rotated *top*-side part separates them.

**Guard.** Calibrate any transform against a rotated top-side part *and* an asymmetric bottom-side
part. See `02-review.md` §2d for the sibling failure: a mirror implemented on the wrong axis, which
survived review because 148 of 152 pads were symmetric two-terminal chips. The toolkit's own
`boardmodel` defaulted to the X mirror until 2026-09-28; on a 6-layer board with 64 bottom-side parts
that default made `route_accept` report 223 false overlaps and 48 false split nets. The default is now
`"y"`.

### T10 — `pcb_modify_primitive` on a via rewrites dimensions you did not ask about

**Symptom.** Asking only to change `x`/`y` rewrote `diameter` and `holeDiameter` to one decimal
place: 19.685 came back as 19.6, tripping the board's own minimum-via rule.

**Guard.** Pass the dimensions explicitly, or do not use it on vias.

### T11 — the drilled-hole rules are not the copper rules

**Symptom.** EasyEDA applies the **board-outline** clearance rule (0.29972 mm on the reference board)
to drilled holes and slots, not the 0.102 mm copper rule, and reports it as `Slot Region to Track` /
`Hole to Hole`.

Hole-to-**track** is exempt when the track is on the net of the pad that owns the plated hole.
Hole-to-**hole** is **not** exempt by net at all — a ground stitching via 0.3 mm from a connector's
own ground shell slot is an error.

**Guard.** Model drilled features separately from copper, inflate them by the outline rule, and
attribute violations by individual land (see T7).

### T12 — `connectMode: 0` is DIRECT

Whatever the serialised text says (`connType: "DIVERGENCE"`), `connectMode: 0` in the plane/copper
zone rules means direct connection. Established twice, across two project iterations. No rule change
is needed to get pads to bond to pours.

---

## Document I/O — the most dangerous section

### T13 — `pcb_import_changes` returns `true` and places nothing

**Symptom.** Every variant returns `true`; the PCB stays empty.

Measured, four ways, each verified against the **raw PCB source** rather than the primitives API
(the empty document's source contains only layer-display records):

| attempt | result |
|---|---|
| target PCB with the schematic's uuid, schematic active | `true`; 0 components |
| target PCB with no uuid, PCB active | `true`; 0 components |
| after `pcb_save` + reload | `true`; 0 components |
| a detached staging PCB created for the test | the call ran > 45 s and timed out; the staging PCB was still empty |

A previous iteration recorded the same behaviour across seven variants.

**Guard.** Do not fight it. **Build the PCB by writing source directly.** And prove what the gate
existed to prove by another route: the reference project verified that **all 29 distinct footprints
used by the schematic resolve in the library, 0 missing**, by uuid, which is the actual risk that
gate was covering.

**Side effect to know about:** this same comparator drives a persistent `Netlist Error 1` in DRC
("PCB and schematic netlist does not match") that is *not* a defect. Counter-measure it directly —
read every pad primitive from the live PCB with the net the EDA holds for it, read every pin→net pair
from the live schematic, and match designator by designator. The reference project's result: **0
differences over 477 pairs, 149 components on both sides, 109 nets on both sides, symmetric
difference empty.**

### T14 — `document_load_from_file` silently half-writes onto a non-empty page

**Symptom.** Reported `success: true` while landing **25 of 477 wires and 142 of 149 designators**.
Every downstream instrument then reported confident nonsense about that half-written document, and
the corruption got worse with each successive push in the same editor session.

**Guard.** **Blank the page first** — push a minimal empty document — then push the real one. Then
read the document back and compare record counts *and* the full designator set. Wrap this into one
"push and verify" helper and make it the only sanctioned way to push a page.

### T15 — `document_load_from_file` de-duplicates by record id, silently

**Symptom.** Two append passes seeded with the same starting number produced the same id sequence.
EasyEDA kept one of each, and **704 mm of copper across 22 nets — every hand-routed net among them —
vanished on load**, with `success: true` and no warning.

**Guard.** Check generated record ids against the ids already in the document before appending.

**Same call, two more behaviours:**

- It **drops zero-length segments** — which a grid router can emit. (The reference board carried six
  sub-10 µm segments, harmless in the fab, but they change the record set on any future round-trip
  and invalidate a cold-reopen fingerprint.)
- It **re-segments top-layer copper on the way in**: per-net line counts move in both directions with
  no copper lost. **Verify a PCB push by connectivity, never by byte-diff.**

### T16 — `document_load_from_file` re-annotates components whose attributes you rewrite

Nine parts came back as `C1`…`R1` with fresh unique ids, **irreversibly**. Use source replacement for
**additive** work only.

### T17 — the canvas does not repaint after a load

A screenshot shows the *pre-push* page. For a rendered image of what was actually saved, use the page
thumbnail inside a fresh project export.

---

## Pours

### T18 — `pcb_rebuild_pours` reports success on pours it did not fill

**Symptom.** `rebuiltCount: 5, emptyCount: 0` — and 24 ground connection errors on the first pass. A
previous iteration recorded the same lie with **120 of 143 ground pads unconnected**.

**Symptom, worse form.** A declared pour with **no filled record at all** — 0 polygons, 0 mm² — in two
exports taken minutes apart, while the other four pours were filled. The shipped Gerber would have
contained no copper for that island, so the fabricated board would not be the board that was
reviewed.

**Guard.** **Judge a pour by its `POURED` record, not by the rebuild call's return value.** If the
tool still will not fill it, wire the net instead (widen it to ≥ 0.5 mm and shorten the tie path) and
say so in the report.

**Related discipline:** a higher-priority island suppresses a lower-priority pour inside its whole
boundary, so ground pads inside that boundary can end up with a via 1–2 mm away and nothing joining
them to it. Wire such islands **as well as** pouring them, and draw an explicit stub from each pad to
its stitching via.

---

## Libraries and projects

### T19 — library writes land only in the project that is currently open

**Symptom.** The project library is addressed by the literal string `"project"`, which resolves
against **whatever project is open at the time**. On this standalone deployment the personal library
is `null` — it does not exist — so there is often **no writable library at all**.

**Guard.** Open the target project *before* any library write, and verify with
`project_get_structure` before and after. Stage library content on disk as a project archive and
import it into the existing project rather than writing part by part.

### T20 — `project_create` and new-project `project_import_file` fail on a standalone install

**Symptom.** `project_create` logs, server-side:

```
[ERROR] [SERVER] json api /api/client/createProject"
{"map":{},"code":1111116,"msg":"请求参数path错误","detail":"path","httpCode":500}
```

The local endpoint needs a filesystem `path`; the extension API models the destination as
team/folder and has no way to pass one. The mismatch is structural.

`project_import_file` **without** an existing project uuid fails the same way — and the decisive test
is that **the runtime cannot re-import its own unmodified export as a new project.** So the failure
is the mode, not the archive.

**Guard.** Ask the user to create the project in the GUI (about 20 seconds), then import into it with
`existingProjectUuid` set. That path works.

### T21 — `project_import_file` **adds** to a project, it does not replace it

With an existing project uuid, an import lands the archive's content **alongside** what is already
there. Importing a board twice gives you two boards, not an updated one.

**Guard.** Know which documents already exist before importing; delete what you mean to replace; and
verify with `project_get_structure` afterwards. Take a backup of the project store first — the
reference project took a live SQLite backup plus a full project export before the first write
attempt.

### T22 — system-library documents cannot be opened as documents

`lib_footprint_open_in_editor` returns `false` for the system library on this build, so system
footprints cannot be read that way. Two working routes:

1. an existing project's own export, which carries local copies of everything it uses;
2. the vendor's public product API, whose footprint payload is the full footprint source.

The reference project used both and **cross-validated: the two sources agreed on 47 of 49 parts.**
That agreement is what makes a 45-row parts manifest trustworthy.

The same limitation bites during fixes: a review finding about silkscreen crossing mask openings was
recorded as **not done** because `lib_footprint_open_in_editor` errored on the project's own
footprints. Accepting a cosmetic finding with the reason stated is the right outcome there.

### T23 — an exported project carries a stale rule table

`project_export_file` serialises rules from the *named*-config store, while a PCB's active config may
be unnamed. It cannot be fixed from the API or from the source; it must be set in the Design Rules
dialog by hand. Cosmetic for manufacturing — but do not read the export's rules and believe them.

---

## Export and fabrication data

### T24 — the Gerber export needs an explicit `layers` list

**Symptom.** `pcb_export_to_file` with `format: "gerber"` and no `layers` **silently ships copper and
drills only** — no silkscreen, no solder mask, no paste, no board outline. **9 files instead of 17,
and no warning.**

**Guard.** Read the layer ids out of the document's own `LAYER` records — do not guess them — and
pass an explicit list. The reference project's 12-entry list: four copper layers, two silkscreen, two
solder mask, two paste, board outline, drill drawing. Also set the extras explicitly:
metallic and non-metallic drilling information, the **drill table**, and the flying-probe test file.

`other.drillTable: true` is what puts the hole table into the drill drawing; without it that file
ships at 17 kB instead of 194 kB.

### T25 — two exports of an unchanged board never diff clean

**Symptom.** Every Gerber layer carries **exactly one aperture that is defined and never used**, and
its D-code moves between exports, which renumbers every subsequent aperture and shifts every aperture
selection by one.

Verified by parsing: the number of unused apertures is exactly 1 in every layer of both exports, and
no draw or flash ever selects one. Consequence: nil. But **compare two exports by parsing, never by
`diff`.**

### T26 — the two plated drill files overlap

`Drill_PTH_Through.DRL` already **contains** every via that `Drill_PTH_Through_Via.DRL` lists. The via
file is a supplementary view, not an addition. Summing them double-counts every via — on the
reference board, 1057 instead of 540, which would falsely blow the free-tier drill budget.

### T27 — Gerber shapes that a naive reader gets wrong

| shape | trap |
|---|---|
| plated **slots** | emitted as Excellon `G85` records; a naive parser drops them silently. All nine plated component holes on the reference board were slots |
| **polygon** pads | their solder-mask opening is a `G36`/`G37` **region**, not an aperture flash. A pad-to-mask check that only matches flashes reports those pads as unmasked |
| **`RoundRect`** aperture | its parameters are the **outer** corners plus a rounding diameter, not a rectangle to be grown. Settle it against a known 0.5 mm-pitch connector: aperture `±0.15 X ±0.570001` → a 0.300 mm pad with a 0.200 mm web |
| **obround** (`%ADDnnO,wXh*%`) | needs its own branch — see T8 |
| pour strokes and fills | **cannot be attributed to a net by pour-boundary containment.** Match them to the document's poured polygons by vertex; poured path coordinates are in units of 0.254 mm (10 mil), not mils |

### T28 — `pick_and_place` and `bom` ignore the CSV file type

They emit UTF-16 LE, tab separated. Also: **the PCB-side BOM reads supplier metadata from the library
device, not from the schematic instance**, so it is stale wherever the two disagree. **The schematic
is the source of truth.**

---

## Runtime and process

### T29 — a 45 s MCP timeout usually means the extension dropped

Check `server_info` for `extensionConnected: false`; it reconnects on its own in a few seconds.
**Do not restart the bridge.**

### T30 — the application ignores a graceful quit on macOS

`kill <pid>` is clean and the bridge reconnects in about four seconds. **After a restart the PCB tab
must be reopened explicitly** with `editor_open_document` before anything else works.

### T31 — same-process results are not evidence about the saved document

**Always: save → quit the application completely → relaunch → reopen → re-measure.** The reference
project's schematic verification compared generator source against post-restart readback:

```
generator source : COMPONENT 627  WIRE 477  LINE 477  ATTR 7599   149 designators
after cold reopen: COMPONENT 627  WIRE 477  LINE 477  ATTR 9920   149 designators
missing: []   extra: []
```

Note that the attribute count **grew** by 2321 — the tool backfills each instance from its library
device on load (3D model, transform, description). So the verifier must allow attributes to grow but
never to shrink. Design the comparison around what the tool legitimately does.

### T32 — pull large results straight to disk

Netlists, BOMs and DRC dumps are large. The reference project wrote a direct client for the bridge
daemon's socket so those results went to a file instead of through an agent's context window. Do the
same; it is the difference between a verification pass that fits in a session and one that does not.

### T33 — long-running verification must run in the foreground

A Gerber clearance sweep (~2 minutes per layer, ~225 MB peak) died silently and repeatedly when
launched as a background shell job — no traceback, output truncated at the last flush, which looks
exactly like an out-of-memory kill and is not one.

---

## The autorouter, if you use one

The reference project used FreeRouting through a DSN/SES round trip. Four failures worth knowing:

1. **It hangs on load when a protected net arrives in disjoint pieces.** Infinite recursion in the
   polyline-combining routine. Bisecting the protected copper one net at a time isolated it to a
   single net whose two pieces both *ended inside* a pad. **Emit every hand-routed net as one
   continuous chain that runs *through* its own pads instead of stopping in them**; the DSN then
   loads in seconds. (See also `02-review.md` §meta-lesson 3: feeding it 3 326 protected traces
   instead of 51 is what caused a 10 h 53 m stall.)
2. **It quotes a net name in the SES only when it has to.** `(net "BT_PWR"` and `(net VSYS` occur in
   the same file. A converter matching only the quoted form silently dropped **15 nets including the
   3.3 V rail (34 pads), the analogue ground (31 pads) and every power rail** — and it looked exactly
   like an autorouter failure. One regex.
3. **It keeps only the class clearance from the DSN boundary.** At 0.115 mm it left a via 0.204 mm
   and four track ends 0.185 mm from the outline, inside the board's own 0.300 mm rule. Insetting the
   boundary polygon makes it fail on load; a **keepout ring** on all copper layers works, at a cost
   of about one net of routing quality.
4. **The DSN export does not describe non-plated holes.** The router laid copper straight through
   the microSD's, the jack's, the switch's and the four side keys' mounting holes — 15 slot-rule
   errors on the first poured DRC. Cut and re-route those against a model that inflates every drill
   by the outline rule.

**Also:** EasyEDA single-quotes the net name in class definitions (`(class X 'X' …)`) and FreeRouting
then binds nothing — emit **bare** class members.

---

## A minimal push-and-verify recipe

```
1. blank the target page (push a minimal empty document)
2. push the generated document
3. save
4. read the document back
5. compare: record counts per type, the complete designator set, and the per-pad net map
6. quit the application, relaunch, reopen, repeat steps 4–5
7. only now run DRC (settled, N identical runs) and export the netlist
8. assert the netlist against must-connect / must-not-connect / must-be-open
```

Anything that skips step 5 is not verification.
