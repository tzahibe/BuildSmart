# POC Architectural Brain — dataset & schema (Issue #94)

Turns real ResPlan floor plans into `PlanReference` (metric geometry + graph) and
`ArchitecturalPattern` (measurable architectural semantics). Code:
`backend/spikes/architectural_brain/{plan_reference,resplan_ingest,patterns,build_corpus,
build_fixtures}.py`. Tests: `backend/tests/architectural_brain/test_plan_reference.py` (never
opens the pickle — reads only the committed fixtures).

## Source dataset

**ResPlan** (Abouagour & Garyfallidis, 2025, arXiv:2508.14006), 17,107 plans, geometry in PIXEL
coordinates per plan, South Asian residential real-estate listings. Licence: **CC BY 4.0** (data).
Local path: `RESPLAN_PKL` env var, default `/Users/mymacbook/projects/datasets/resplan/ResPlan.pkl`
— never committed, never opened by the test suite.

## `PlanReference` schema (`plan_reference.py`, `schema_version: "1.0"`)

| Field | What it is |
|---|---|
| `footprint` | Exterior ring (metres) of the largest part of ResPlan's `inner` polygon. |
| `rooms[]` | `id`, `type` (a BuildSmart `ProgramRole` value or `"CIRCULATION"` for a residual space, or `UNKNOWN`), `polygon`, `area_m2`, `width_m`/`depth_m` (axis-aligned bbox extents — ResPlan geometry is grid-aligned), `exterior_exposure` (subset of N/S/E/W), `exposure_known` (`False` = the source plan has no window geometry at all, so exposure is a genuine UNKNOWN, not "no exposure"). |
| `walls[]` | Each connected component of ResPlan's `wall` geometry, metric. |
| `doors[]` | `room_ids` (0, 1, or 2 rooms the door touches — 0 is an honestly-reported unmatched geometry, not dropped), `is_exterior`. |
| `windows[]` | `room_id` (or `None`) + `side` (footprint edge N/S/E/W, or `"UNKNOWN"` if not near one). |
| `entrance` | `room_id` + `side`, from ResPlan's `front_door`; `None`/`"UNKNOWN"` independently when undetectable. |
| `adjacency_edges[]` | Rooms whose polygons lie within ~1 wall thickness of each other (physically next to each other; door not required). |
| `access_edges[]` | Rooms connected by an actual door (`kind: "DOOR"`). |
| `derived` | `scale_m_per_px`, `wall_thickness_m`, `footprint_area_m2`, `room_type_counts` — normalisation facts, not architectural semantics. |
| `provenance` | `source_dataset`, `source_plan_id` (ResPlan's own `id`), `unit_type`, `licence`, `citation`. |

`N`/`S`/`E`/`W` are the four footprint bounding-box edges by coordinate axis — ResPlan carries no
true-north/street-facing information, so these are geometric labels, not compass-calibrated ones.

## Ingestion rules (`resplan_ingest.py`)

- **Scale**: `sqrt(area_m2 / inner.area_px)`, cross-checked against `wall_depth`: a plan whose
  implied wall thickness falls outside **8–45 cm** is rejected (`PlanRejected`) — a value outside
  that band means the scale inference is wrong, not that a real wall is unusually thin/thick.
  1/17,107 plans measured this way is rejected.
- **Rooms**: each polygon part of ResPlan's `living`/`kitchen`/`bedroom`/`bathroom`/`storage`/
  `stair` categories is one room. `living` → `LIVING`; `kitchen` → `KITCHEN`, **unless** its
  polygon is ≥90% contained inside a `living` polygon (a geometry artefact — an unlabelled living
  nook, not a second room — measured at 2/199 corpus plans), in which case it is unioned into the
  `LIVING` room instead of double-counted. Whether a genuinely separate kitchen is *open* or
  *closed* to living is not baked into the room type — it is read off `access_edges`/whether a
  standalone `KITCHEN` room exists at all (see `public_composition` below).
  `bathroom` → `TOILET` if net area < 4.0 m² else `BATHROOM` (matches the existing
  `app/vertical_slice/concept_generator.py` TOILET/BATHROOM target-area boundary). `stair` →
  `STAIRWELL`. ResPlan has no `dining` category, so `DINING` never appears from ingestion (a real
  typology gap — see below). `balcony`/`garden`/`parking`/`pool`/`veranda` have no `ProgramRole`
  equivalent and are outside `inner` on every plan checked, so they are not represented as rooms.
- **Circulation**: `inner − (walls ∪ rooms)`, connected components ≥ 2.0 m² become `CIRCULATION`
  rooms (a real minimal hallway is at least a door-width by a body-width deep; components under
  ~1 m² measured on this corpus are tiling artefacts between rooms/walls, not navigable space —
  see the `MIN_CIRCULATION_AREA_M2` comment in `resplan_ingest.py` for the measured cutoff).
- **Doors/windows/entrance**: matched to the room(s) whose polygon they touch after a
  `1.5 × wall_thickness` buffer (calibrated against real gaps between a door/front_door polygon
  and an eroded residual `CIRCULATION` polygon — see `CONNECTOR_MATCH_BUFFER_WALLS`). A connector
  touching zero rooms keeps an empty `room_ids`/`room_id: None` — never guessed.
- **Adjacency**: rooms within `1.2 × wall_thickness` of each other (a ResPlan-style
  distance-based "next to each other", independent of doors).

## Pattern rules (`patterns.py`)

- **`circulation_class`** (priority order — first rule that fires wins): `SPINE` (one residual
  component, oriented long/short > 3, ≥3 doors into it) → `HUB_LOBBY` (one residual component,
  aspect ≤1.5, ≥4 doors into it, neighbouring rooms on ≥3 of its bbox sides) → `BRANCHED` (≥2
  residual components directly joined to each other) → `TWO_WING` (footprint fills ≤65% of its own
  minimum rotated rectangle — this corpus's own ~10th percentile of fill-ratio, isolating the most
  L-like tenth rather than claiming a universal geometric constant; median fill-ratio on this
  corpus is ~0.82, so most ResPlan footprints have a notch, not a second wing) → `FRONT_BAND`
  (public rooms on the entrance side cover ≥60% of the footprint's extent along that side) →
  `OTHER`. `UNKNOWN` only if a plan has no rooms at all (never observed post-normalisation).
- **`zoning`**: `CENTRAL_PUBLIC` (area-weighted public-room centroid within 15% of the footprint
  diagonal from the footprint centre, closer to it than the private centroid) →
  `PUBLIC_FRONT_PRIVATE_REAR` (public/private separation axis aligned with the entrance side, public
  nearer to it) → `PUBLIC_PRIVATE_WINGS` (a separation axis exists but isn't entrance-aligned) →
  `OTHER`/`UNKNOWN` (no public or no private rooms at all).
- **`public_composition`**: `OPEN` (no standalone `KITCHEN` room — merged into `LIVING` at
  ingest, or none present) / `CLOSED_ADJACENT` (a `KITCHEN` room exists with a door directly to
  `LIVING`) / `CLOSED_SEPARATE` (a `KITCHEN` room exists but is not door-connected to `LIVING`) /
  `UNKNOWN` (no `LIVING` room). `DINING` never participates — ResPlan has no dining category, so
  the living↔dining and dining↔kitchen relationships are always reported `"NOT_PRESENT"`.
- **`bedroom_grouping`**: for each bedroom, its "gateway" is the lexicographically-first
  non-bedroom room it has a door to; the share of bedrooms whose gateway is the single largest
  shared gateway. `None` (UNKNOWN) if the plan has no bedrooms (never true post-corpus-filter).
- **`wet_core_strategy`**: `SINGLE` (1 wet room) / `CLUSTERED` (≥2 wet rooms, all one connected
  component via `adjacency_edges`) / `DISPERSED` (≥2 wet rooms in ≥2 components) / `UNKNOWN` (0
  wet rooms detected — see the corpus counts below, a real data gap, not a bug).
- **`entrance_relationship`**: `TO_LIVING`/`TO_HALL`(→`CIRCULATION`)/`TO_KITCHEN`/`TO_OTHER`, or
  `UNKNOWN` if the entrance room itself is UNKNOWN.
- **`exposure_pattern`**: share of habitable rooms (LIVING/DINING/KITCHEN/FAMILY_ROOM/BEDROOM/
  MASTER_BEDROOM/STUDY/SAFE_ROOM) with a measured exterior exposure; `None` (UNKNOWN) if the plan
  has no window geometry at all.
- **`circulation_ratio`**, **`corridor_length_m`** (longest residual component's oriented long
  side), **`circulation_nodes`** (residual component count) are always measurable (0 is a real
  answer, not UNKNOWN).
- **`topology_depth`**: max door-hops from the entrance room over `access_edges`; `None` if the
  entrance room is UNKNOWN.
- **`relationships`**: `entrance_public` (`DIRECT`/`VIA_ONE_ROOM`/`FAR`/`NOT_CONNECTED`/`UNKNOWN`),
  `bedrooms_private_circulation` / `wet_bedrooms_public` (share of bedrooms/wet-rooms whose access
  neighbour is a circulation/bedroom room respectively — `None` if none exist), plus the always-
  `"NOT_PRESENT"` `living_dining`/`dining_kitchen` pair noted above.

## The corpus (`build_corpus.py` → `backend/spikes/architectural_brain/corpus/`)

**Selection**: all Villa/IndependentHouse/BuilderFloor with ≥3 bedrooms, plus Apartment with 3–5
bedrooms (out of 6,919/17,107 plans matching this filter before dedup) — this is what biases the
corpus toward 3–5 bedrooms against a dataset that is 93% Apartment and mostly 1–2 bedrooms.
**Deduplication**: a documented proxy fingerprint (unit type, net/gross area, per-category polygon
area, bedroom/bathroom/door counts) — not ResPlan's own geometry-based near-duplicate scan (not
reproducible without the paper's tooling), so treat this as an approximation, not an exact match to
the paper's "1,170 redundant plans" figure. **Sampling**: a fixed stride across the deduplicated
candidate list (`len(candidates) // 200`), not the first N — the dataset is not shuffled, and a
stride avoids biasing toward whatever was scraped/ordered first.

**Result: 199 plans**, 1 rejected for out-of-range implied wall thickness (of the plans the stride
touched). Footprint area 58.5–359.1 m² (median 141.7 m²); bedrooms: 3 in 162 plans, 4 in 27, 5 in
10. Unit types: Apartment 185, BuilderFloor 13, Villa 1 (Villa/IndependentHouse are a small
minority of ResPlan overall, and the stride sample reflects that).

Measured distributions (n=199):

| `circulation_class` | count | | `zoning` | count |
|---|---|---|---|---|
| OTHER | 91 | | PUBLIC_PRIVATE_WINGS | 81 |
| FRONT_BAND | 71 | | CENTRAL_PUBLIC | 68 |
| TWO_WING | 28 | | PUBLIC_FRONT_PRIVATE_REAR | 50 |
| BRANCHED | 9 | | | |

| `wet_core_strategy` | count | | `public_composition` | count |
|---|---|---|---|---|
| DISPERSED | 173 | | CLOSED_SEPARATE | 189 |
| CLUSTERED | 13 | | CLOSED_ADJACENT | 8 |
| UNKNOWN | 13 | | OPEN | 2 |

`entrance_relationship` is `TO_LIVING` for all 199 corpus plans — a real, measured property of this
typology (compact plans, no separate foyer/hall in front of the door), not a classifier bug: only
54/1,840 rooms across the whole corpus are `CIRCULATION` at all, so an entrance landing in a hall is
architecturally rare here to begin with.

**UNKNOWN counts (n=199)**: `exposure_pattern` UNKNOWN (no window geometry at all) in 6/199 plans;
`wet_core_strategy` UNKNOWN (zero bathroom/toilet rooms detected — a source-data gap, some listings
were digitised without bathroom polygons) in 13/199; `entrance`/`bedroom_grouping` UNKNOWN in 0/199
(every corpus plan has a detectable `front_door` and ≥3 bedrooms by construction of the filter).

Room-type counts across the corpus: LIVING 371, BEDROOM 644, BATHROOM 449, KITCHEN 197, TOILET 90,
CIRCULATION 54, STORAGE 27, STAIRWELL 8 (1,840 rooms total).

**SPINE does not occur anywhere in the 17,107-plan dataset** under the measurable rule above — every
plan was checked (a single residual component with oriented aspect > 2.5 *and* ≥2 doors into it
already returns zero matches across all 17,107 plans; the stated rule, aspect > 3 and ≥3 doors, is
strictly narrower). This is architecturally plausible for the dataset's regional scope (compact
South Asian apartments/houses without a dedicated long spine hallway) rather than a derivation bug —
confirmed by cross-checking real `BRANCHED` examples, where a genuine multi-door hallway system
exists but is split into ≥2 residual pieces by a bend, not one long straight run. Because AC-2
requires a `SPINE` example in the 20-plan test fixture, that one fixture plan
(`synthetic-spine-01`) is a hand-built synthetic `PlanReference` — clearly marked
`provenance.source_dataset: "SYNTHETIC"` — used only to prove the `SPINE` rule itself is
implemented correctly and deterministically; it is not, and does not claim to be, a real ResPlan
plan. The other 19 fixture plans are real ResPlan plans (see `build_fixtures.py`).

## Typology gap

ResPlan is exclusively South Asian residential real-estate listings — apartment-dominated (93%),
median 110 m², no plot/street/site context, no `SAFE_ROOM` category (a mandatory feature of
Israeli residential construction that BuildSmart's `ProgramRole` vocabulary carries), and no
`DINING` category (a distinct room in many Israeli plans, folded into `living` here or absent).
`GARAGE`/`PARKING` polygons exist in the raw data but sit outside every `inner` footprint checked,
and have no `ProgramRole` equivalent regardless. Anything trained or benchmarked against this
corpus should treat it as evidence about *floor-plan organisation patterns* (circulation topology,
zoning, wet-core clustering) that transfer across markets, not as a source of Israeli-market
specifics (setback rules, safe-room placement, plot/street relationships) — those remain out of
scope for this POC per Issue #94.

## Licence & attribution

ResPlan is released under **CC BY 4.0**. Citation: Abouagour & Garyfallidis, 2025, "ResPlan: A
Large-Scale Vector-Graph Dataset of 17,000 Residential Floor Plans", arXiv:2508.14006. Every
corpus file's `plan_reference.provenance` block carries this citation and licence, and
`backend/spikes/architectural_brain/corpus/ATTRIBUTION.md` restates it at the directory level.
