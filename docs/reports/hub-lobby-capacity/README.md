# Generalizing HUB_LOBBY — the experiment, and why it stopped

**Hypothesis tested (#182).** Production lacks concept diversity because HUB_LOBBY knowledge exists
but its compiler supports only a narrow two-bedroom programme, so it never contributes a second
circulation topology.

**Result: the hypothesis is half right, and the half that is wrong matters more.** The compiler's
"exactly 2 bedrooms" is **not** an arbitrary coding shortcut. It is the exact capacity of a compact
lobby under this engine's own dimensions. Generalizing it is therefore not a matter of removing a
literal, and a single hub cannot serve the audited programmes at all.

**No production code was changed.** The generalized compiler written to test this was reverted once
it answered the question; what remains is the measurement that explains it.

---

## 1. The three answers

**1. Can HUB_LOBBY be generalized across realistic residential programmes?**
**No — not as a single compact lobby.** It tops out at two bedrooms, by geometry.

**2. Does it survive realization and validation?**
Beyond two bedrooms it never reaches validation. Every generalized tree was rejected by Geometry
Core itself, and the refusals name the cause exactly:

```
B06   leaf 'HALL' cannot be 3.75 x 5.60 m, the rectangle its forced cuts fix
B09   leaf 'BATH_1' cannot be 3.75 x 5.30 m, the rectangle its forced cuts fix
```

3.75 × 5.60 m is a 21 m² lobby — past the 16 m² a compact lobby is allowed. The solver refused to
build the only hall big enough to serve three bedrooms.

**3. Does it produce a visibly different, architecturally credible concept?**
Not demonstrated, because nothing beyond two bedrooms realizes. The stop rule applies as written:
*"if larger programmes make HUB_LOBBY architecturally nonsensical, do not force them to fit simply
to improve coverage."* Forcing them would mean elongating the lobby into a corridor, which is the
spine concept this candidate exists to differ from.

## 2. Why two bedrooms is the capacity, in production's own numbers

`compile_hub_lobby`'s HALL `ZoneSpec` bounds the lobby at **16 m² and aspect 1.5**. A rectangle
under those bounds has a longest possible face of **4.90 m**, with the other face 3.27 m.

Every room reached from the lobby consumes a share of that perimeter at least its own minimum short
side plus the engine's edge inset:

| role | lobby edge it consumes | fits on the 4.90 m face |
|---|---:|---:|
| BEDROOM | 2.80 m | **1** |
| MASTER_BEDROOM | 3.20 m | 1 |
| SAFE_ROOM | 2.60 m | 1 |
| BATHROOM | 1.80 m | 2 |
| TOILET | 1.30 m | 3 |

The parti spends its faces as: north = the public opening, west = the master, east = the bedroom
ring, south = the shared wet rooms. So the fan-out is

> **1 public opening + 1 master + 1 bedroom + 1–2 wet rooms = 2 bedrooms total.**

Which is exactly what the hand-authored compiler supports. Reproduce with
`python -m app.ai_harness.hub_capacity.capacity`.

## 3. What the generalized compiler did establish

It was programme-driven rather than count-driven: it read `build_room_program(spec)`, placed the
public chain north, the master and its ensuite west, the remaining bedroom-class rooms on the east
face and the shared wet rooms south, and searched the master column's width and the lobby's depth
for a sizing. On the eight audited briefs it compiled for **B06 and B09** (both 3-bedroom, on the
two largest footprints) and declined the rest with architectural reasons rather than a bedroom
count. Both compiled trees were then **rejected by Geometry Core** for the reason above.

It also surfaced two real defects in the existing parti that are independent of capacity:

- **The hand-authored hub drops DINING.** The brief's programme is LIVING, DINING, KITCHEN, but the
  tree carries only LIVING and KITCHEN, so a hub plan would be missing a room the brief asked for.
- **A plan's width must satisfy both sides.** With a small programme the private row is narrower
  than the public band needs, and sizing the band into the private row's width empties the band.

## 4. The one brief within capacity, and the bounded gap

Of the eight audited briefs exactly one — **B20, two bedrooms** — is inside a compact lobby's
capacity. The existing compiler still declines it, for a different and much smaller reason:

```
B20   compile_hub_lobby's 3-wet-room GUEST_WC row is not yet combined with a safe room
```

That is a three-way south-row split (shared bath | safe room | guest WC) that was named as a
follow-up and never built. It is the only audited brief where a hub is both architecturally sound
and currently blocked by an implementation gap rather than by geometry.

## 5. The next missing structural concept

> **BRANCHED** — a hub plus a secondary distribution.

This is how real architecture serves three or more bedrooms from a hub: the lobby distributes to
the public zone, the master and a short bedroom corridor, and that corridor serves the rest. It is
the only way past the perimeter limit that does not turn the lobby into a spine. The repo already
has `compile_branched`, documented as supporting a four-bedroom programme, and #182 measured it
returning zero candidates on all eight briefs — so it needs the same forensic treatment before
anything is built.

**Not recommended:** relaxing the HALL area or aspect bound to admit more rooms. That buys coverage
by destroying the thing that makes HUB_LOBBY a distinct concept, and the result would be a spine
under another name — explicitly against this experiment's architectural invariant.

## 6. Scope

No production code changed; the generalized compiler was reverted after it answered the question.
No L-shaped massing, no outline-seam change, no BRANCHED implementation, no courtyard/ring/two-wing,
no selection or ranking change, no #142, no validator change, no production default change, no
randomization. What ships here is a report and one harness probe.
