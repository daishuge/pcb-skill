# 03 — Ordering from JLC (嘉立创 / JLCPCB)

Read this **before** you fix the board outline, the stack-up or the design rules. Every constraint
here is geometric or procedural, and every one of them is free to satisfy at the sketch stage and
expensive to satisfy at the Gerber stage.

---

## How to read this file

Every figure carries how it was established:

- **VERIFIED** — read from a JLC-owned page (URL + the page's own update date) or from a live order
  form / account page, on 2026-09-06 or 2026-09-07.
- **COMPUTED** — arithmetic on verified numbers. The arithmetic is shown so you can redo it.
- **NOT ESTABLISHED** — genuinely unsettled. Do not turn these into facts.

> **Fees, coupon families and process limits change.** The reference project found the coupon
> taxonomy had been reorganised by surface finish since the rules a previous iteration had read, and
> found one commonly-quoted engineering fee traceable to a page timestamped **2011**. Re-verify every
> number below against the live pages before you commit a design to it, and prefer JLC's own pages
> over any third-party write-up.
>
> The international site (`jlcpcb.com`) and the Chinese site (`jlc.com`) **do not share a fee
> schedule**. One carries a small-hole surcharge the other does not. Use the site you will actually
> order from.

---

## 1. The free-prototype coupon — the rules, verbatim

> `1-4层(包括铝基板)的PCB免费打样通用券： 需满足订单工艺要求，不限制设计软件`
>
> `基本工艺要求说明： 10*10cm以内 5片 （长宽小于1CM的板不在免费范围），单片出货， 常规工艺，双面板支持杂油， 单，四，六 层板仅支持绿油。，（嘉立创小助手、移动端下单）`
>
> *("Free-prototype universal coupon for 1–4 layers (aluminium substrate included): the order must
> meet the process requirements; no restriction on design software. Basic process requirements:
> within 10×10 cm, 5 pieces (boards smaller than 1 cm on a side are not covered), shipped as
> individual boards, **regular process**, 2-layer boards may use assorted mask colours, 1/4/6-layer
> boards support green only. (Order via the JLC ordering assistant or the mobile site.)")*
>
> — VERIFIED, `www.jlc.com/portal/server_guide_37595.html`, page's own update date 2025-07-10

And:

> `券的使用期限为一个月，从领券之日开始算起。`
> `注意：各种券不能通用。 1-4层免费券，不能用作6层PCB打样`
>
> *("The coupon is valid for one month from the day it is claimed. Note: coupons are not
> interchangeable — a 1–4 layer free coupon cannot be used for a 6-layer prototype.")*
>
> — VERIFIED, `www.jlc.com/portal/t7i37578.html`

**What that means for the design, before you draw anything:**

| rule | design consequence |
|---|---|
| 10 × 10 cm | **both edges ≤ 100.00 mm.** The reference board is 41.40 × 100.00 — 100.00 exactly, and that constrained every later floorplan decision |
| 5 pieces | you get spares, not a production run |
| 单片出货 | **no panelising.** Do not design a panel or a V-cut array |
| 常规工艺 | the envelope in §4. Anything outside it is a surcharge and may void the coupon |
| 4/6 layers → 绿油 only | **green solder mask.** Colour is not a design choice on a free 4-layer board |
| 1.6 mm | thickness is fixed |
| 不需要阻抗 | **no impedance control.** Design differential pairs to a computed impedance and accept the tolerance; you cannot order controlled impedance on this coupon |
| 嘉立创小助手 / 移动端下单 | **the ordering route is part of the coupon.** See §7 |

Further exclusions, all VERIFIED from the live coupon page:

> `开源文件、返单或者存在拆单行为均不支持免费打样`
>
> *("Open-source files, repeat orders, and order-splitting behaviour are not eligible for free
> prototyping.")*

**Do not publish the design to an open-hardware platform before ordering.** This is a real trap: an
agent that helpfully pushes the project to a public gallery as a deliverable can disqualify the
coupon it spent the whole project designing for.

> `同一手机号，同一终端设备，多次相同地址等均视为同一用户…免费打样劵需微信扫码领取`
>
> *("The same phone number, the same device, or repeated use of the same address are all treated as
> one user … free-prototype coupons must be claimed by scanning a WeChat QR code.")*

---

## 2. Two coupon families, and how one is earned

This is the part most write-ups get wrong, and it decides whether your board is free at all.

| family | covers | how you get it |
|---|---|---|
| **通用券** (universal) | any design software | requires **≥ ¥20 of *actually paid* PCB spend in the previous calendar month, shipped** |
| **EDA专用券** (EDA-exclusive) | **only boards designed 100 % in JLC's own EDA** | available with no spend requirement |

Verbatim from the live claim page:

> `上个月PCB实付订单金额达到20元及以上，且订单已发货，则本月能领取PCB OSP免费打样通用券或EDA专用券`
> `优惠券详情（仅限小助手）2-6层OSP EDA专用券，2-6层OSP通用券`
> `上个月PCB实付订单金额没有达到20元及以上，则只能领取EDA专用券`
> `优惠券详情（仅限小助手）2-6层OSP EDA专用券`
>
> *("If last month's actually-paid PCB order total reached ¥20 or more and the order has shipped,
> you may claim either the OSP free-prototype universal coupon or the EDA-exclusive coupon this
> month — coupon details (assistant only): 2–6 layer OSP EDA-exclusive, 2–6 layer OSP universal.
> If last month's actually-paid PCB total did not reach ¥20, you may claim only the EDA-exclusive
> coupon.")*
>
> — VERIFIED live, 2026-09-06

**The trap that bit the reference project:** the previous month's only PCB order had itself been
free, so 实付 (actually paid) was ¥0, which is below the ¥20 gate. Every 通用券 tile on the page was
locked. **A free board this month does not earn you a universal coupon next month.** If a project
wants to escape the EDA-native rule later, one paid PCB order of ≥ ¥20 must land first.

### What "EDA-exclusive" costs the design

> `必须是嘉立创EDA的原生设计，不能导入！`
>
> *("It must be a native JLC EDA design — it cannot be imported!")*
>
> — VERIFIED, repeated three times on `www.jlc.com/portal/t7i37578.html`; the refusal message is
> `系统判断该文件不是 100% 使用嘉立创EDA设计` (`server_guide_37593.html`, updated 2026-01-08)

Consequence: **no importing geometry or a board from another EDA tool.** Footprints and symbols
brought in through the EDA's own library or extension API are fine; a board imported wholesale is
not. Plan the fallback before you need it — the reference project's was *"create a fresh native PCB
document in the GUI and copy-paste the content into it, one minute of human work, decided at order
time."*

Whether handing a *Gerber* to the ordering client counts as "importing" is **NOT ESTABLISHED**. The
reference project's reading was that the clause bars a design imported from another EDA, not a
Gerber handed to the ordering app — but that is a reading, it decides whether the coupon holds, and
it was left as the user's call.

---

## 3. Surface finish: OSP vs ENIG

**Free prototypes default to OSP.** VERIFIED:

> `免费打样已全部切换为OSP工艺` and `OSP无任何表面处理费用`
> — `www.jlc.com/portal/t7i37578.html`, article dated 2026-08-24

**6-layer boards: the free channel is OSP only since 2026-05-29.** VERIFIED 2026-09-29, verbatim from
`www.jlc.com/portal/q7i61353.html` (dated 2026-05-29):

> `后续6层板免费打样通道，仅支持OSP表面处理，不再受理沉金工艺订单`

The coupon-use page `server_guide_37576.html` (updated 2026-09-15) still lists 沉金 among the 6-layer
coupon conditions, and `q33i62511.html` (2026-08-07) says `沉金打样券：继续保留` without saying it covers
6 layers. Rule for an order: pick the finish the coupon's own title names, and pay only if the total
reads ¥0.00. (ARK CARD round-2 audit, 2026-09-29: its package had specified 沉金 on the 6-layer coupon.)

**Free ENIG (沉金) also exists for 2–4 layers** (the 2024 notice below also said 6), and this is the lever most people miss. VERIFIED, verbatim, from
`www.jlc.com/portal/q7i42818.html` (dated 2024-03-05) and confirmed still live on the claim page in
2026:

> `原2、4层免费打样不支持免费沉金，现升级为 2-6层全面支持免费沉金打样`
> `3、2-6层 沉金板限每月免费打样一次 。即当月打了一次免费沉金板，第二次则为喷锡板；`
> `4、对于免费沉金板， 沉金面积不得超出整板面积的20% ，超出则不支持沉金免费打样；`
> `5、领取沉金板的客户，要进行"嘉立创题库"考核`
> `8、与喷锡工序相比，沉金板生产时间长，沉金板交期比喷锡板多1天左右`
>
> *("Free prototyping for 2- and 4-layer boards previously did not support free ENIG; it is now
> upgraded so that 2–6 layers fully support free ENIG prototyping. (3) Free ENIG is limited to once
> per month for 2–6 layers — after one free ENIG board that month, the next is HASL. (4) For a free
> ENIG board the gold area must not exceed 20 % of the whole board area; above that, free ENIG
> prototyping is not supported. (5) Customers claiming ENIG must pass the JLC process quiz.
> (8) Compared with HASL, ENIG takes longer to produce — about one extra day of lead time.")*

So free ENIG is: **2–6 layers, once per calendar month, gold area ≤ 20 % of the board, one extra
day of lead time, and gated behind a process quiz.**

**Which one to design for:**

- **ENIG is materially better for hand soldering** — flat, wettable, no oxide layer to fight on a
  fine-pitch connector. Take it if the account can claim it and the design has < 20 % gold area.
- **OSP is what the free coupon usually gives you.** Then two design rules follow:
  1. no pad that requires a flat gold finish;
  2. **no BGA pad ≤ 0.25 mm** — `BGA焊点≦0.25mm，仅限沉金工艺` (VERIFIED), i.e. a tiny BGA pad forces
     ENIG and therefore breaks an OSP-only coupon.
- **Decide before layout, not at the order form.** The coupon families are split by finish, and the
  one you can claim may not be the one you designed for.

---

## 4. The 常规工艺 envelope — 4-layer, what stays free

Sources: `www.jlc.com/portal/vtechnology.html` and `www.jlc.com/portal/q7i38752.html`. All VERIFIED.

| parameter | JLC's own words (4-layer / 多层板) | use this |
|---|---|---|
| min track / space, 1 oz | `多层板：0.09/0.09mm(3.5mil/3.5mil)` | **≥ 0.10 mm** (3.94 mil) for margin. Below 3.5 mil is **+20 % of 货款** *and* very likely not 常规工艺 |
| min drill | `最小钻孔：0.15mm（常规0.3mm）` | **0.30 mm** — this is the value JLC itself calls 常规 |
| 0.15 mm drill | `双面板、多层板最小钻孔0.15mm（非常规！费用高请慎用）` | **do not use** |
| via pad vs hole | `① 外径必须比内径大0.1mm,推荐大0.15mm以上` `② 最小孔推荐0.2mm以上` | 0.30 drill / 0.50 pad satisfies both comfortably |
| via annular ring | `过孔单边焊环：0.05mm，常规设计：0.1mm` | **0.10 mm per side is "regular"** — legal, and zero margin. Use 0.30/0.55 on a re-spin |
| via-to-via | `④ 过孔孔边到孔边最小间隙0.2mm` | |
| hole-to-hole, plated | `有铜孔边缘跟有铜孔边缘：建议0.3mm` | |
| track to via, outer | `底层及顶层线离过孔外径最边缘最小距离：多层≧3.5mil` | |
| **track to via, inner layers** | `多层板内层线离过孔内径边缘最小距离：≧6.7mil` | **0.17 mm from the DRILL edge — the tightest inner-layer rule, and easy to miss** |
| plated-hole annular ring (TH parts) | `多层板：≧0.20mm(建议值)，极限值为0.15mm` | 0.20 recommended; 0.15 is the limit, not a target |
| pad edge to track, 1 oz | `≧0.1mm(尽量大于此参数)` | |
| solder-mask opening | `开窗比焊盘单边≧0 (焊盘与开窗1：1，全部采用阻焊LDI制作)` | **1:1 openings are allowed** — useful on fine-pitch connectors |
| track width tolerance | `±20%` | |

### Is 0.20 mm drill / 0.40 mm pad free?

**NOT ESTABLISHED, and the reference project refused to guess.** The Chinese fee schedule lists no
diameter-based hole surcharge at all; the international page charges exactly that combination
(*"0.2mm or 0.25mm hole size with via diameter less than 0.45mm will cost more"*). The two do not
agree. Position taken:

- **0.30 / 0.50 — SAFE.** JLC calls it 常规.
- **0.20 / 0.40 — probably free on the CN site, NOT ESTABLISHED.** Settle it by comparing two live
  quotes with different drill files, not by reasoning.
- **0.15 / 0.25 — do not use.** JLC's own words: `非常规！费用高请慎用`.

---

## 5. The drill-count surcharge — compute it for *your* board

> `大量钻孔会增加钻机的工作时长及钻咀的损耗，从而增加钻孔成本。因此，对于1平米超15万孔的订单需收钻孔费（即超量钻孔费），不设封顶。`
>
> *("Heavy drilling increases machine time and drill-bit wear, and therefore drilling cost. So an
> order exceeding 150 000 holes per square metre incurs a drilling fee (an excess-drilling fee),
> **with no cap**.")*
>
> — VERIFIED, `www.jlc.com/portal/server_guide_53841.html`

**The arithmetic (COMPUTED — do this for your own outline):**

```
threshold_holes_per_board = 150000 holes/m² × board_area_m²

reference board: 41.4 mm × 100 mm = 4140 mm² = 0.004140 m²
                 150000 × 0.004140 = 621 holes per board
```

A dense 4-layer board reaches this easily. The reference project's routed board landed at **616 of
621 — 0.81 % margin** — and that was rejected as unacceptable margin on a hard constraint, because:

- the fee is explicitly **uncapped** (`不设封顶`);
- its *rate* is published only as an image, so it cannot be priced in advance;
- the acceptance test for a free order is a **¥0.00 quote**, and an unknown charge on the order that
  is supposed to be free is exactly what stops it;
- 5 holes is inside the noise of how a CAM tool counts slots and stacked holes.

Target ≤ 95 % of the threshold. The reference project got to **584 (5.96 % margin)** by deleting 32
redundant stitching vias under explicit keep rules — see `02-review.md` §meta-lesson 4 for how to
choose which vias are actually redundant.

**Does exceeding it void the coupon?** Read carefully and record the answer honestly. The reference
project's finding: *"exceeding it adds a fee; no published JLC text says it disqualifies the free
coupon. 钻孔费 sits on the surcharge schedule beside 微割费 / 铣边费 / 小板费 / 大面积沉金费 /
测试超点费 — a volume charge, not a process class."* It stayed under the threshold anyway.

### Counting the holes correctly

The export may contain **two plated drill files**, and one is a *subset view* of the other, not an
addition. In the reference package `Drill_PTH_Through.DRL` (526 hits) already **contains** every one
of the 517 vias that `Drill_PTH_Through_Via.DRL` lists on its own — verified coordinate by
coordinate as a strict subset. Summing them gives 1057 and a false conclusion that the board blows
the budget; the real count was 540.

Also: plated component holes are often **slots** (`G85` records in Excellon), a shape a naive parser
silently drops. Count unique drilled *features*, cross-check against the drill drawing's symbol
count, and attribute every non-via hole to a part.

---

## 6. The rest of the surcharge schedule

From `www.jlc.com/portal/server_guide_53841.html`, read in full. Trigger conditions VERIFIED; the
**rates are published only as images and are NOT ESTABLISHED**.

| surcharge | trigger, verbatim | applies to a ~41 × 100 mm 4-layer board? |
|---|---|---|
| 钻孔费 | `对于1平米超15万孔的订单需收钻孔费…不设封顶` | **yes, if dense — see §5** |
| 多层线宽/线距 | `多层板线宽/线距小于3.5mil：4-8层加收货款的20%` | no, if you stay ≥ 3.5 mil |
| 微割费 | `对于单板尺寸单边小于1.5cm的订单` | no |
| 铣边费 | `0.8～1.0mm的锣槽宽度，每平米达到80m锣程` | only if the outline/slots are milling-heavy |
| 小板费 | `对于单片尺寸≤3cm的电路板` | no |
| 大面积沉金费 | `PCB顶底层两面沉金面积合计占比超 30%` | no on OSP; relevant if you take ENIG |
| 测试超点费 | `每PCS或SET的测试点达到或者超过8000点` | check the netlist pin count |
| 板长 ≥ 60 cm | `板子长度达到或超过60cm：样板每款加收200元` | no |

---

## 7. Ordering routes — and which one honours a coupon

There are three, and they are not equivalent. **This is the single most consequential procedural
fact in this file.**

| route | coupon? | measured evidence |
|---|---|---|
| **网页版下单** (the web order form) | **NO** | The coupon appeared in the selector's **不可用** tab, greyed out, valid and unexpired. Quote: **¥162**, not ¥0 |
| **下单助手** (the desktop ordering assistant) | **yes** | The same order page quotes **¥54** through the assistant against ¥162 through the web form, before any coupon. The coupon rules name this route |
| **微信扫码下单** (WeChat scan / mobile) | **yes** | Named in the coupon rules alongside the assistant; needs no install |

The coupon page says `（仅限小助手）` — *"assistant only"* — **four separate times**. Both the
rules pages and the live account page agree.

**The EDA's own "one-click order" is not a fourth route.** Its documentation says, verbatim:

> 嘉立创EDA会根据当前打开的PCB生成Gerber文件上传服务器。上传成功后点击弹窗的确定按钮打开嘉立创的下单页面进行下单。
>
> *("JLC EDA generates a Gerber from the currently open PCB and uploads it to the server. On success,
> clicking OK in the dialog opens JLC's ordering page to place the order.")*

It generates a Gerber, uploads it, and **opens the ordinary web order form** — the one that refuses
the coupon.

**Two corrections the reference project had to make to its own earlier research, both worth knowing:**

1. **The web order form is layer-count dependent.** An earlier pass concluded "the web form does not
   offer OSP at all" — read on the form's **2-layer default**. Switch 板子层数 to 4 and the finish
   list becomes `有铅喷锡（免费）/ OSP（无铅/免费）/ 无铅喷锡（收费+30元/平方米）/ 沉金（收费）`.
   **Always set the layer count before reading any option list on that form.** The coupon fails
   because of `仅限小助手`, not because of OSP.
2. **The desktop assistant does ship a macOS build** (arm and x64), alongside Windows and Linux —
   an earlier pass had seen only a Windows download and treated the whole route as blocked.

**A practical warning about driving the assistant with an agent:** the reference project measured
that its window **renders a stale image to screen capture** — the accessibility tree updates but the
pixels do not — so its GUI cannot be driven safely by sight. Its PCB-order page offers only "pick an
already-uploaded file" plus a native file dialog; there is no watch folder. And the web order page
has **no Gerber upload control at all** (measured: zero `input[type=file]`), because the upload
happens after 提交订单 — which an agent must not press. Plan for the final ordering clicks to be the
user's.

**The coupon is often not load-bearing for the budget.** In the reference project the assistant
quoted the board at ¥54 without any coupon, which still cleared the project's ¥350 ceiling; only the
web form's ¥162 broke it. So the operative rule reduced to something simpler than "get the coupon":
**never order this board through the web form.**

---

## 8. Economic SMT (经济型贴片) — if you use machine assembly at all

Skip this section if the user hand-solders everything. Read it before you decide.

### Fees

| item | figure | status | source |
|---|---|---|---|
| 工程费 (setup) | **¥50 per order** | VERIFIED | `m.jlc.com/portal/newV2/smt.jsp`; `server_guide_30669.html` (updated 2026-08-31) |
| 钢网费 (stencil) | **¥0** | VERIFIED | same (`不用钢网费`) |
| 焊点费 (per joint) | **¥0.01 per joint** | VERIFIED | `server_guide_42886.html` (`目前贴片焊点收费标准为0.01元每个贴片焊点`) |
| 焊点费 discount to ¥0.005 | only if designed in JLC EDA **and** the order area > 1 m² | VERIFIED | same |
| 换料费, 基础库 (basic library) | **¥0** (`基础库不用加收`) | VERIFIED | `m.jlc.com/portal/q3i18121.html` |
| 换料费, 扩展库 (extended library) | **¥20 per part type** (an FAQ says `20-30元`) | VERIFIED, two figures | `m.jlc.com/portal/newV2/smt.jsp` |
| 换料费 if pre-stocked at JLC | **¥5 per type** | VERIFIED | `m.jlc.com/portal/q3i18121.html` |
| cap on extended types per order | **none** — `取消所有扩展库型号的使用限制` | VERIFIED | `server_guide_24593.html` |

JLC's own worked example, which pins the joint rate arithmetically:

> `有5片板需要SMT，每片有200个焊点，总计：1000焊点+50.0工程费+0钢网=¥60元`
>
> *("5 boards need SMT, 200 joints each: 1000 joints + ¥50 setup + ¥0 stencil = ¥60.")*

**No coupon waives the ¥50 setup fee.** The reference project looked for one and found none: the
"blind box" free-SMT coupon is randomly granted to some new customers (`嘉立创会视产能情况…随机免费给部分新客户贴片`,
`数量少，碰到的概率不大`), and the PCB free-prototype coupon's rules say nothing about SMT fees.
**Budget ¥50 as payable.**

### Minimum quantity, and the quantity that actually matters

**Minimum SMT quantity is 2 pieces**, and it can differ from the PCB quantity:

> `现在最少贴2片…其中下单PCB的5片或者10片 SMT可以选贴2片`

VERIFIED, but the Chinese source page is dated 2020-06-24 — the international capability page
independently states Economic `Order Volume: 2 - 50 pcs`, which agrees. **1 piece is not available.**

Cost lever: dropping the SMT quantity from 5 to 2 saves roughly ¥12 of joint fee on a 400-joint board
*plus* 60 % of the per-position parts cost. If the user needs one finished unit, order 2.

### What economic SMT will not do

> `局限:不支持潮敏、中低温、沉板与夹板式结构，0201及以下片式元件、引脚中心距≤0.35mm的芯片和球间距≤0.4mm的BGA等精密器件。`
> — `server_guide_30669.html` (updated 2026-08-31)

> `局限:不支持潮敏、中低温、沉板与夹板式结构，片式元件＜0402、IC pin间距＜0.4mm、BGA球径间距＜0.5mm等精密器件。`
> — `server_guide_26.html` (updated 2026-09-05)

*("Limitations: moisture-sensitive parts, low/medium-temperature parts, recessed-board and
sandwich-board structures are not supported, nor precision devices such as chip components smaller
than 0402, ICs with pin pitch below 0.4 mm, or BGAs with ball pitch below 0.5 mm.")*

The international page agrees: Economic `Minimum Component Package: 0402`, `Minimum IC Pin Spacing:
0.4mm`, `Minimum BGA Spacing: 0.5mm`, `Assembly type: Single sided placement`, `PCB Layers: 2,4,6`.

**So: 0402 is the smallest chip; 0201 is refused; a 0.4 mm-pitch IC is fine and a 0.35 mm one is not.
This is a DFM gate, not a fee.**

**One side only** — `【经济型】产线说明：（只焊接一面）` (VERIFIED). Which of the two faces is
**NOT ESTABLISHED**: JLC never names it, though the order form exposes a 焊接层 selector. Design
top-side placement.

Board thickness accepted: `经济型可接板厚为0.8mm、1,0mm、1.2mm、1.6mm` — the coupon's 1.6 mm is fine.
Reflow: `回流焊温度：255+/-5度` for economic vs 240 ± 5 for standard; paste
`305无铅锡膏(Sn96.5Ag3.0Cu0.5)`, `无铅 免清洗工艺`.

### The loss allowance that inflates the parts bill silently

> `使用(使用数量)=订单所需数量+损耗数量。`
> `基础库： 嘉立创把器件整盘装在贴片机上。 损耗完全由嘉立创承担`
> `扩展库： 贴片机上位置有限…如有贴装，需要更换机上物料。`
>
> *("Usage (quantity used) = quantity the order requires + loss quantity. Basic library: JLC keeps
> the full reel loaded on the machine, and bears the loss entirely. Extended library: machine slots
> are limited, so many parts cannot stay loaded — placing one requires changing the material on the
> machine.")*
>
> — VERIFIED, `www.jlc.com/portal/server_guide_42767.html` (updated 2025-04-23)

Extended-library loss, verbatim:

| pins | unit price | loss added |
|---|---|---|
| 1–2 | `0.0-0.1（不含0.1）元` | **10 pcs** |
| 1–2 | `0.1-0.2（不含0.2）元` | 8 pcs |
| 1–2 | `0.2-0.5（不含0.5）元` | 4 pcs |
| 1–2 | `0.5-1.0（不含1.0）元` | 2 pcs |
| 1–2 | `≥1.0（含1.0）元` | 0 |
| 3–8 | `0.0-0.2（不含0.2）元` | 5 pcs |
| 3–8 | `0.2-0.5（不含0.5）元` | 4 pcs |
| 3–8 | `0.5-1.0（不含1.0）元` | 2 pcs |
| 3–8 | `≥1.0（含1.0）元` | 0 |
| > 8 | any | `按0损耗处理` |
| 批量订单 | — | `再加上千分之二的损耗` |

And a second, easily-missed floor on the same page:

> `使用数量需要≥最小上机数量`
> `规则：编带器件的长度需要在8CM，才可以装飞达。`
>
> *("The quantity used must be ≥ the minimum machine-loading quantity. Rule: taped components need
> 8 cm of tape length before they can be loaded into a feeder.")*

**8 cm of tape minimum per taped extended part.** At 0402's 2 mm tape pitch that is ≈ 40 pieces; at a
4 mm-pitch SOT-23 it is ≈ 20 (the pitch→count arithmetic is COMPUTED; the 8 cm rule is VERIFIED). On
a 2-board run this dominates the required quantity for every extended part.

### The economics, stated plainly

At **quantity one**, a ¥20 per-type loading fee dwarfs every part price on a small board. That
inverts the usual rule:

> basic, machine-placed (fee ¥0) **>** *leaded extended, hand-soldered (fee ¥0)* **>** extended,
> machine-placed (fee ¥20/type)

The middle option wins far more often at qty 1 than it would at volume. A worked case from the
reference project: an ¥3.37 QFN codec plus a ¥20 fee loses to an ¥8.56 leaded TSSOP DAC plus ¥0 —
and the leaded part also satisfies a no-QFN hand-assembly rule for free. The break-even fee was
¥5–8; the measured fee was ¥20; the leaded chain won and the codec was dropped.

### What JLC changes without telling you

> `因SMT生产工艺需要，我们会帮您添加或修改工艺边或MARK点，且不另行通知，外形四角圆角半径在0.3-2MM范围`
>
> *("For SMT production we will add or modify process rails or fiducials without separate
> notification, and the four corners of the outline will be rounded to R0.3–2 mm.")*
>
> — VERIFIED, on the live order form

**If you select SMT, your outline is not sacred.** Any enclosure must tolerate added rails and
rounded corners. This does not apply to a bare-PCB order.

### One more SMT-side fact for the BOM

> `嘉立创将完全弃用立创商城的价格体系，采用自用的价格体系`
>
> *("JLC will abandon the LCSC price system entirely and use its own.")*

**JLC SMT part prices are not LCSC prices.** Price a machine-assembly BOM from the SMT match screen,
never from LCSC listings. (They are also different *stock* pools — see `04-sourcing.md`.)

---

## 9. Order-form checklist

Set the layer count **first**, then read every other option list. The reference project's parameter
set, for a free 4-layer 41.4 × 100 mm board:

```
板材类别      FR-4
板子层数      4                       ← set this before reading any other list
层压结构      JLC04161H-7628（免费）   ← see §10: the design file cannot carry this
板子尺寸      4.14 × 10 CM            ← the field's unit is CM, not mm
板子数量      5
成品板厚      1.6
阻焊颜色      绿色      字符颜色  白色
焊盘喷镀      OSP（无铅/免费）
外层铜厚      1 oz     内层铜厚  0.5 oz
阻焊覆盖      过孔塞油
出货方式      单片（不拼板）
阻抗          无要求
最小孔径      0.3mm（免费）
线路测试      选免费项（AOI / 飞针）
确认生产稿    不需要                  ← 需要 costs ¥3–10
SMT / 钢网    不需要 / 不需要
交期          免费加急项，不勾任何加价项
```

Two things the form says that are worth keeping:

- Selecting 过孔盖油 pops `过孔盖油已经免费升级为过孔塞油` — the upgrade is free and the option
  cannot be set back.
- The same row warns `如果是gerber文件，此选项中选项无效，一律按文件过孔属性生产` — **if you upload
  a Gerber, the file governs via tenting, not the form.** Make sure the design tents what you want
  tented.

**Confirm the total reads ¥0.00 with the coupon applied before going any further.** If it does not,
stop: something about the coupon's conditions is not what you think.

---

## 10. What the design file cannot carry

Some order parameters live only on the order form, and no amount of care in the EDA puts them into
the fabrication package.

The reference project raised a SERIOUS finding that the document's physical stack-up described a
**two-layer** board (one 59.449 mil dielectric; the inner layers at zero thickness) while the copper
was four-layer. The fix looked easy — set the physical stack through the API — and then:

> The physical stack-up **cannot be set through the API** — every physical-stacking method in the
> shipped SDK is a stub, and a direct write to the layer-physics record reverts on cold restart (it
> is GUI-only state). **The risk it was raised for does not occur**: the Gerber export contains
> exactly 4 copper files. **Therefore the 4-layer stack must be selected on the order form**, and
> that is now a named checklist item for the order step — it is not carried by the document.

Two lessons:

1. **Verify the consequence, not the symptom.** "The stack-up record is wrong" mattered only if it
   changed the output. Counting copper files in the export answered that in a minute.
2. **Anything the file cannot carry becomes a human checklist item, written down, at the order
   step.** Put it in the build/order instructions, not in a comment.

---

## 11. Source list

Every URL below was fetched 2026-09-06/07. **Re-verify before relying on any figure.**

**JLC's own pages (Chinese):**
`server_guide_37595.html` (free-coupon core rules) ·
`t7i37578.html` (coupon scheme, expiry, blind box, OSP article) ·
`server_guide_30669.html` (经济型/标准型 product types) ·
`server_guide_26.html` (SMT sizes / thickness / limits) ·
`server_guide_4026.html` (SMT process, single-side) ·
`server_guide_19858.html` (SMT ordering flow, form fields) ·
`server_guide_42767.html` (物料损耗 policy) ·
`server_guide_42886.html` (焊点费 ¥0.01) ·
`server_guide_51484.html` (panelising, economic-vs-standard fees) ·
`server_guide_53841.html` (附加收费一览表 — the surcharge schedule) ·
`server_guide_24593.html` (no cap on extended types) ·
`vtechnology.html` + `q7i38752.html` (capability tables) ·
`q7i42818.html` (free ENIG for 2–6 layers) ·
`q7i54031.html` ("免费打样规则暂无任何变更") ·
`t7i1392.html` (JLC SMT prices ≠ LCSC prices) ·
`m.jlc.com/portal/newV2/smt.jsp` (economic SMT fee card) ·
`m.jlc.com/portal/q3i18121.html` (换料费) ·
`m.jlc.com/portal/q2i15713.html` (min SMT qty 2) ·
`www.jlc.com/portal/appDownloadsWithConfig.html` (ordering-assistant downloads)

**International (corroboration only, different fee basis):**
`jlcpcb.com/capabilities/pcb-assembly-capabilities` ·
`jlcpcb.com/help/article/pcb-assembly-price` ·
`jlcpcb.com/help/article/in-what-cases-will-there-be-charged-extra` ·
`jlcpcb.com/impedance` (stack-up dielectric constants and thicknesses, needed for any impedance
calculation)
