"""#142L steps 2/3/4 — the offline ARCHITECTURAL QUALITY evaluator (experiment only, never wired into
production selection).

It reads ONE validator-PASS plan record from `quality_142l.baseline` and returns a vector of RAW
metrics. It deliberately does NOT collapse them into one score: #142L's question is which dimensions
carry signal, and an up-front weighted sum would only encode our guesses (task §5).

AUDIT FIRST (task §3). The repository already measures a great deal of this on realized geometry, and
where it does, THIS EVALUATOR READS PRODUCTION'S OWN NUMBER rather than inventing a second definition:

  `circulation_metrics.measure`   area/ratio/longest segment/narrowest width/dead ends/turns/duplication
  `entrance_sequence.measure`     arrival zone and class, pocket length, distance to public, private
                                  doors passed, foyer, stray pockets
  `dead_space.measure`            STUB / SLIVER / CORNER / OVERSIZED_HALL regions, m2 and share
  `public_composition.measure`    kitchen-dining and dining-living relation, public-zone coherence,
                                  living exposure, composition score
  `wet_privacy.compute_wet_privacy`  per wet room: entered-from class, sight line, exposure score
  `wet_core.compute_wet_core`     shared wet wall, clusters, plumbing complexity index
  `master_suite.compute_master_suites`  master sight lines to bed and ensuite door, routes crossing the
                                  bed, suite score  (computed in production code but wired to NOTHING)
  `hub_guard.proportions_of`, `l_massing_guard.exposure_of`  bedroom/master/safe-room aspects,
                                  worst wet aspect, two-sided exposure share, wet adjacency share

Those are marked `PRODUCTION` below. `DERIVED` marks what #142L adds because nothing measures it yet
(public/private wall sharing, routes through the public zone, facade allocation, bedroom consistency,
the measured adjacency prior over realized contacts). `MISSING_INFORMATION` lists the qualities §2 asks
about that NO available data supports; those are never faked.

Conventions of the realized geometry
  * `rect_m = [x, y, w, h]` in metres; the STREET is the footprint's y = minimum edge, so "front" =
    small y (`resolve_entrance` reads that edge; the band pipeline puts row 0 there).
  * `doors` lists the doors the realizer actually built; an OPEN wall group is also a connection.
  * Role sets come from the production policy modules (`access_rules`, `exposure_policy`), never
    re-listed here, so a policy change cannot silently diverge from this evaluator.
"""
from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass

from app.vertical_slice.access_rules import CIRCULATION_ROLES, SERVICE_ROLES, WET_ROLES
from app.vertical_slice.exposure_policy import EXPOSURE_POLICY, ExposureRequirement
from app.vertical_slice.geometry_core.model import ProgramRole

EPS = 1e-6
#: The public living core of a house (ENTRANCE/FLEX are in production's PUBLIC_ROLES but are not
#: living space, so they are excluded from the "public zone" reading).
PUBLIC_CORE = (ProgramRole.LIVING, ProgramRole.DINING, ProgramRole.KITCHEN, ProgramRole.FAMILY_ROOM)
BEDROOMS = (ProgramRole.BEDROOM, ProgramRole.MASTER_BEDROOM)
#: Net short side below which an inhabited room reads as a sliver. ROOM_TEMPLATES' smallest habitable
#: `min_short_side_m` is 2.1 m (STUDY); production's own `dead_space.SLIVER_MIN_USABLE_WIDTH_M` is
#: 0.9 m, which only catches leftovers. 2.0 m is this experiment's documented judgement, not a rule.
SLIVER_SHORT_SIDE_M = 2.0


@dataclass(frozen=True)
class MetricDef:
    name: str
    dimension: str
    direction: str          # up | down | info
    unit: str
    definition: str
    inputs: str
    rationale: str
    limitations: str
    availability: str       # PRODUCTION | DERIVED


def _d(*a) -> MetricDef:
    return MetricDef(*a)


DIMENSIONS = ("circulation_efficiency", "public_private_separation", "privacy", "entrance_quality",
              "public_zone_quality", "bedroom_quality", "wet_core_quality", "exposure_quality",
              "proportion_quality", "soft_adjacency_quality")

_PROD = "production realized-geometry module (see module docstring)"

METRICS: dict[str, MetricDef] = {m.name: m for m in (
    # ------------------------------------------------------------------ A. circulation
    _d("circulation_ratio", "circulation_efficiency", "info", "ratio 0-1",
       "`circulation_metrics.ratio` — dedicated circulation area over plan area", _PROD,
       "Circulation is overhead, but a house with none has no separation between public and private "
       "life; C26 already refuses the extreme (>0.24). Direction is deliberately `info`: lower is not "
       "simply better, which is precisely the trap §2A warns about.",
       "Says nothing about the shape or usefulness of that circulation.", "PRODUCTION"),
    _d("circulation_longest_segment_m", "circulation_efficiency", "down", "m",
       "`circulation_metrics.longest_segment_m` — longest single corridor run", _PROD,
       "A long corridor is the clearest form of wasted movement; C26 refuses beyond 20 m.",
       "A long corridor that serves many rooms is less wasteful than a short one that serves two.",
       "PRODUCTION"),
    _d("circulation_dead_ends", "circulation_efficiency", "down", "count",
       "`circulation_metrics.dead_end_count` — corridor ends with neither a door nor an open join",
       _PROD, "A corridor end that serves nothing is pure waste and reads as a mistake.",
       "Production's own threshold refuses only at 2+; one dead end is common.", "PRODUCTION"),
    _d("circulation_turns", "circulation_efficiency", "down", "count",
       "`circulation_metrics.turn_count` — axis changes on the entrance-to-farthest-room path", _PROD,
       "Turns make a route feel long and hard to read; production measures but never gates them.",
       "Counted on one representative path, not all routes.", "PRODUCTION"),
    _d("circulation_duplicated_area_m2", "circulation_efficiency", "down", "m2",
       "`circulation_metrics.duplicated_area_m2` — area of circulation rooms that redundantly serve "
       "an overlapping set of rooms", _PROD,
       "Two corridors doing one corridor's job.", "Measured, never gated, by production.", "PRODUCTION"),
    _d("circulation_rooms_served", "circulation_efficiency", "up", "count",
       "rooms reachable through one door directly off a HALL/CIRCULATION room",
       "realized door graph + roles",
       "A corridor earns its area by distributing; the more rooms one circulation space serves "
       "directly, the less of the plan is spent on passage.",
       "Counts doors, not walking comfort.", "DERIVED"),
    _d("mean_steps_from_entrance", "circulation_efficiency", "down", "doors",
       "mean doors crossed on the shortest realized-door path from the arrival room to every other room",
       "realized door graph",
       "How deep the plan is as actually walked.",
       "Topological: one long corridor counts as one step.", "DERIVED"),
    _d("max_steps_from_entrance", "circulation_efficiency", "down", "doors",
       "worst-case door count from the arrival room to any room", "realized door graph",
       "The room nobody wants to reach; catches a tacked-on wing.",
       "Same topological limitation.", "DERIVED"),
    _d("mean_walk_from_entrance_m", "circulation_efficiency", "down", "m",
       "mean Manhattan distance from the entrance door centre to each room centroid",
       "entrance door + room rects",
       "A metric rather than topological proxy for daily walking distance.",
       "Manhattan through walls, not along the real route (see MISSING_INFORMATION).", "DERIVED"),
    _d("dead_space_share", "circulation_efficiency", "down", "ratio 0-1",
       "`dead_space.dead_space_share` — STUB + SLIVER + CORNER + OVERSIZED_HALL area over plan area",
       _PROD, "Production's own residual-pocket measure: area that is neither room nor useful passage.",
       "Its STUB limit is documented as stale and it gates nothing today.", "PRODUCTION"),

    # ------------------------------------------------------------------ B. public/private zoning
    _d("public_private_wall_m", "public_private_separation", "down", "m",
       "total shared interior wall length between a PUBLIC_CORE room and a bedroom-class room",
       "room rects + roles",
       "Every metre of wall between the living core and a bedroom is noise and privacy transfer that "
       "circulation would otherwise absorb. Rubric section J records that NO production check measures "
       "whether delivered zoning stayed coherent — this is that gap.",
       "Wall length is not acoustics; a shared wall without a door is far milder than a door.", "DERIVED"),
    _d("public_private_wall_share", "public_private_separation", "down", "ratio 0-1",
       "public_private_wall_m over the plan's total interior shared-wall length", "room rects + roles",
       "Normalises the raw length against plan size.", "Same acoustic caveat.", "DERIVED"),
    _d("bedrooms_reached_through_public", "public_private_separation", "down", "count",
       "bedrooms with NO realized-door route from the arrival room that avoids every PUBLIC_CORE room "
       "other than the arrival room itself",
       "realized door graph + roles",
       "Reaching a bedroom across the living room is the classic zoning failure: residents cross the "
       "family's activity to go to bed and guests see the sleeping wing.",
       "Arriving INTO the living room is not counted here — that is entrance quality, measured by "
       "`arrival_is_circulation`, and would otherwise be charged twice.", "DERIVED"),
    _d("public_components", "public_private_separation", "down", "count",
       "connected components of the PUBLIC_CORE rooms under shared-wall adjacency", "room rects + roles",
       "A coherent public zone is one piece; two fragments means the living functions were scattered.",
       "Rooms joined only through a hall count as separate here by design.", "DERIVED"),
    _d("private_components", "public_private_separation", "down", "count",
       "connected components of the bedroom-class rooms plus their ensuites under shared-wall adjacency",
       "room rects + roles + resolved wet rooms",
       "A sleeping wing in one piece can be shut off from the rest of the house.",
       "A two-wing house may legitimately split bedrooms.", "DERIVED"),
    _d("zone_band_overlap", "public_private_separation", "down", "ratio 0-1",
       "overlap of the front-to-back (y) extents of the public cluster and the bedroom cluster, over "
       "the smaller extent", "room rects + roles",
       "Front-to-back stratification (public at the street, private at the back) is the band family's "
       "natural zoning move; heavy overlap means the zones are interleaved.",
       "Assumes a front/back reading; a left/right zoning scores badly without being wrong.", "DERIVED"),

    # ------------------------------------------------------------------ C. privacy
    _d("bedroom_doors_off_public", "privacy", "down", "count",
       "bedroom-class rooms with a realized door into a PUBLIC_CORE room", "realized door graph + roles",
       "A bedroom door onto the living room exposes the room every time it is used.",
       "Door existence, not its position on the wall or any screening.", "DERIVED"),
    _d("bedroom_doors_off_arrival", "privacy", "down", "count",
       "bedroom-class rooms with a realized door into the room the front door arrives in",
       "realized door graph + entrance", "The most exposed case: the bedroom is on show at the front door.",
       "Treats the arrival room as one undivided space.", "DERIVED"),
    _d("master_hall_sight_line_to_bed", "privacy", "down", "0/1",
       "`master_suite.hall_sight_line_to_bed` — a straight ray from the master's entry door reaches the "
       "conservative bed envelope", _PROD,
       "The only room-level sight-line computation in the repository besides the wet rooms'. Being "
       "visible in bed from the corridor is a real privacy defect.",
       "Master bedroom only; the bed envelope is a conservative placeholder, not a furniture layout. "
       "No equivalent exists for secondary bedrooms (see MISSING_INFORMATION).", "PRODUCTION"),
    _d("master_suite_score", "privacy", "down", "score",
       "`master_suite.suite_score` — weighted sum of: ensuite route crosses the bed (1.0), wardrobe "
       "route crosses the bed (0.5), hall sight line to bed (0.3), hall sight line to ensuite door (0.2)",
       _PROD, "Production's own master-suite privacy measure, computed today and wired to nothing.",
       "Its weights are production's, not derived here; master only.", "PRODUCTION"),
    _d("wet_doors_to_public", "privacy", "down", "count",
       "wet rooms whose `WetPrivacy.entered_from_class` is PUBLIC", _PROD,
       "A bathroom opening off a public room is the complaint specs/009 and C29 were written about.",
       "Uses production's classification, including its decision that LIVING access is legal.", "PRODUCTION"),
    _d("wet_direct_sight_lines", "privacy", "down", "count",
       "wet rooms whose `WetPrivacy.direct_sight_line` is true", _PROD,
       "A bathroom door facing straight into a public room.", "Wet rooms only.", "PRODUCTION"),
    _d("wet_privacy_worst", "privacy", "down", "score",
       "worst `WetPrivacy.privacy_score` in the plan (production's own exposure + obstruction - "
       "adjacency combination, already used as a ranking key in `_break_l_tie`)", _PROD,
       "Production's existing privacy ranking key, applied to every plan rather than only L peers.",
       "Wet rooms only; production's own scale.", "PRODUCTION"),
    _d("entrance_to_bedroom_steps", "privacy", "info", "doors",
       "fewest doors from the arrival room to any bedroom-class room", "realized door graph",
       "Separation of the sleeping zone from the front door. Reported, never ranked: more separation is "
       "more private but less convenient, and that trade-off is a taste the brief does not state.",
       "Topological.", "DERIVED"),

    # ------------------------------------------------------------------ D. entrance
    _d("arrival_is_circulation", "entrance_quality", "up", "0/1",
       "`entrance_sequence.is_circulation_arrival` — the front door arrives into HALL/CIRCULATION",
       _PROD,
       "A transition space lets a visitor be received without entering the family's living space; "
       "`ENTRANCE_ZONE_PRIORITY` ranks hall, then circulation, then living, and `general_pipeline`'s "
       "own `_entrance_rank` already prefers it.",
       "Arriving into a generous living room is a legitimate open-plan choice — specs/009 decision C "
       "ranks it third, not forbidden.", "PRODUCTION"),
    _d("entrance_pocket_m", "entrance_quality", "down", "m",
       "`entrance_sequence.pocket_length_m` — dead length of the arrival space beyond the first opening "
       "(C25 refuses beyond 4.0 m)", _PROD,
       "An arrival that runs into a blank pocket is the anti-pattern 'entrance dead-end'.",
       "Production's thresholds are documented PARAMETER·UNVERIFIED.", "PRODUCTION"),
    _d("entrance_distance_to_public_m", "entrance_quality", "down", "m",
       "`entrance_sequence.distance_to_public_m` — distance from the front door to the first public room",
       _PROD, "Excessive travel immediately after entry (§2D); production's own `entrance_sequence_prefers` "
       "ranks on exactly this and IS wired into `general_pipeline`.",
       "Distance only; says nothing about what is passed on the way.", "PRODUCTION"),
    _d("entrance_private_doors_passed", "entrance_quality", "down", "count",
       "`entrance_sequence.private_doors_passed` — private-room doors passed on the way to the public zone",
       _PROD, "Walking past bedroom doors to reach the living room is both a privacy and an arrival defect.",
       "Counted on the measured route only.", "PRODUCTION"),
    _d("arrival_fanout", "entrance_quality", "up", "count",
       "realized doors in the arrival room, excluding the front door", "realized door graph",
       "An entrance should distribute; a fanout of 1 makes the arrival a corridor stub.",
       "High fanout can also mean every door is visible from the front door — read with "
       "`bedroom_doors_off_arrival`.", "DERIVED"),
    _d("steps_entrance_to_living", "entrance_quality", "down", "doors",
       "doors crossed from the arrival room to LIVING (0 when arrival IS the living room)",
       "realized door graph", "The main public destination should be immediately available.",
       "Topological.", "DERIVED"),

    # ------------------------------------------------------------------ E. public-space quality
    _d("public_zone_coherent", "public_zone_quality", "up", "0/1",
       "`public_composition.public_zone_coherent` — the public rooms form one coherent related group",
       _PROD, "Production's own public-composition measure (Issue #41), already ranked on by "
       "`composition_prefers` in `general_pipeline`.",
       "Production's own definition of 'related', which includes open joins and doors.", "PRODUCTION"),
    _d("kitchen_dining_related", "public_zone_quality", "up", "0/1",
       "`public_composition.kitchen_dining_related` (1/0; absent pair reported as 1 — not a defect)",
       _PROD, "Serving between kitchen and dining is daily use; KITCHEN-LIVING is also the highest-lift "
       "measured adjacency in the ResPlan corpus.",
       "`None` when the brief has no separate dining room, which is not a defect.", "PRODUCTION"),
    _d("living_exterior_exposed", "public_zone_quality", "up", "0/1",
       "`public_composition.living_exterior_exposed`", _PROD,
       "The main living space should reach the facade.",
       "Binary: says nothing about how much frontage the living room gets, and it is constant (1) across "
       "every plan in this pool because C19 already requires it.", "PRODUCTION"),
    _d("public_largest_cluster_share", "public_zone_quality", "up", "ratio 0-1",
       "net area of the largest shared-wall-connected public cluster over the total public net area",
       "room rects + roles + net areas",
       "How much of the public programme actually hangs together as one space.",
       "A deliberately separated formal dining room reads as fragmentation.", "DERIVED"),
    _d("public_narrowest_neck_m", "public_zone_quality", "up", "m",
       "smallest shared wall between two adjacent rooms inside the largest public cluster",
       "room rects + roles",
       "A public zone joined by a 0.9 m neck is two rooms, not one space (§2E 'narrow necks').",
       "Falls back to the cluster's own width for a single-room cluster.", "DERIVED"),
    _d("public_compactness", "public_zone_quality", "up", "ratio 0-1",
       "net area of the largest public cluster over its bounding-box area", "room rects + net areas",
       "A compact public zone is a usable space; an L of leftovers is not.",
       "Punishes a deliberately articulated plan.", "DERIVED"),
    _d("public_worst_aspect", "public_zone_quality", "down", "ratio",
       "largest net long/short ratio among the PUBLIC_CORE rooms", "production net dims",
       "A 4:1 living room cannot be furnished as one space; the rubric records KITCHEN median aspect "
       "2.75 and DINING 2.35 against real plans as a known strip-room gap.",
       "Per room; says nothing about the combined shape.", "PRODUCTION"),

    # ------------------------------------------------------------------ F. bedrooms
    _d("bedroom_worst_aspect", "bedroom_quality", "down", "ratio",
       "`hub_guard.PlanProportions.bedroom_max` — worst secondary-bedroom aspect (production's own "
       "gate value, HUB_GATES.bedroom_aspect = 1.35)", _PROD,
       "A narrow bedroom cannot take a bed with circulation on both sides; the quality tier's "
       "`preferred_aspect_ratio` for a bedroom is 1.5 against a legal max of 2.5.",
       "Gross rect, as production computes it.", "PRODUCTION"),
    _d("master_aspect", "bedroom_quality", "down", "ratio",
       "`hub_guard.PlanProportions.master` — master-bedroom aspect (gate 1.40)", _PROD,
       "Same, for the one bedroom the programme singles out.", "Gross rect.", "PRODUCTION"),
    _d("bedroom_min_net_area_m2", "bedroom_quality", "up", "m2",
       "smallest net area among bedroom-class rooms", "production net areas",
       "The worst bedroom is what a family argues about.",
       "Area alone; a large awkward room still scores well here.", "PRODUCTION"),
    _d("bedroom_min_short_side_m", "bedroom_quality", "up", "m",
       "smallest net short side among bedroom-class rooms", "production net dims",
       "Usable width governs whether furniture fits at all.",
       "The furniture feasibility flag is reported separately.", "PRODUCTION"),
    _d("bedroom_area_cv", "bedroom_quality", "down", "ratio",
       "coefficient of variation of net area across the SECONDARY bedrooms (BEDROOM role only)",
       "production net areas + roles",
       "Secondary bedrooms are normally meant to be comparable; one child getting half the room of "
       "another is a complaint, not a design.",
       "Assumes secondary bedrooms SHOULD be comparable — a documented assumption, false if a brief "
       "distinguishes them, which these briefs do not.", "DERIVED"),
    _d("master_is_largest_bedroom", "bedroom_quality", "up", "0/1",
       "1 when MASTER_BEDROOM has the largest net area among bedroom-class rooms",
       "production net areas + roles",
       "The one bedroom hierarchy the programme states by naming the role.",
       "Binary; ignores the margin.", "DERIVED"),
    _d("bedrooms_with_window", "bedroom_quality", "up", "ratio 0-1",
       "fraction of bedroom-class rooms with at least one placeable window", "production windows",
       "Daylight is REQUIRED for bedrooms and gated by C19/C8; the fraction exposes plans that satisfy "
       "it minimally.", "Window count, not area or orientation.", "PRODUCTION"),
    _d("bedroom_public_wall_m", "bedroom_quality", "down", "m",
       "total shared wall between bedroom-class and PUBLIC_CORE rooms", "room rects + roles",
       "Noise at the pillow; the per-bedroom view of the zoning metric.", "Not acoustics.", "DERIVED"),
    _d("bedrooms_entered_from_circulation", "bedroom_quality", "up", "ratio 0-1",
       "fraction of bedroom-class rooms whose realized door comes from HALL/CIRCULATION",
       "realized door graph + roles",
       "The access policy's own preference for private rooms, measured on the built result.",
       "Legality is already hard-gated; this measures how uniformly it was achieved.", "DERIVED"),

    # ------------------------------------------------------------------ G. wet core
    _d("plumbing_complexity_index", "wet_core_quality", "down", "count",
       "`wet_core.plumbing_complexity_index` — estimated independent plumbing stacks (components over "
       "wet rooms plus the kitchen)", _PROD,
       "Fewer stacks is real build cost; production's own estimate, with a ranking key "
       "(`candidate_wet_core_key`) that has no caller.",
       "An ESTIMATE by its own docstring; no riser or slab routing.", "PRODUCTION"),
    _d("wet_shared_wall_m", "wet_core_quality", "up", "m",
       "`wet_core.shared_wall_length_m` — interior wall shared between two wet rooms", _PROD,
       "Back-to-back wet rooms share one wet wall.",
       "Clustering can also bury a bathroom; balanced by `wet_rooms_with_window`.", "PRODUCTION"),
    _d("wet_cluster_count", "wet_core_quality", "down", "count",
       "`wet_core.cluster_count` — wall-connected groups of wet rooms", _PROD,
       "Scattering wet rooms multiplies runs.",
       "An ensuite legitimately sits away from a guest WC; a preference, not a rule.", "PRODUCTION"),
    _d("wet_adjacency_share", "wet_core_quality", "up", "ratio 0-1",
       "`hub_guard.PlanProportions.wet_share` — wet rooms adjacent to their served room over all wet "
       "rooms (production's own gate value, HUB_GATES.wet_adjacency = 0.80)", _PROD,
       "The rubric records this as the single largest measured quality gap after circulation topology: "
       "40% against a ~85-90% reference.",
       "Production's own adjacency definition.", "PRODUCTION"),
    _d("wet_rooms_with_window", "wet_core_quality", "up", "ratio 0-1",
       "fraction of wet rooms with at least one placeable window", "production windows + roles",
       "Guards the clustering metrics: a tight wet core that lands every bathroom in the dark is not "
       "better. Bathrooms are PREFERRED (not REQUIRED) exposure, so this never gates.",
       "Window presence, not ventilation adequacy.", "PRODUCTION"),
    _d("ensuite_adjacent_to_host", "wet_core_quality", "up", "ratio 0-1",
       "fraction of resolved ENSUITE wet rooms sharing a wall with their declared host bedroom",
       "resolved wet rooms + room rects",
       "An ensuite must belong to its bedroom; the door proves access, the wall proves it is part of "
       "the suite rather than reached around a corner.",
       "1.0 when the brief has no ensuite.", "DERIVED"),

    # ------------------------------------------------------------------ H. exposure / daylight
    _d("preferred_exposure_satisfied", "exposure_quality", "up", "ratio 0-1",
       "fraction of rooms whose exposure policy is PREFERRED that have an exterior wall",
       "roles + realized geometry + EXPOSURE_POLICY",
       "The exposure the policy wants but never enforces — the honest place to reward daylight beyond "
       "the validators.", "Exterior wall, not window area or orientation.", "DERIVED"),
    _d("two_sided_exposure_share", "exposure_quality", "up", "ratio 0-1",
       "`l_massing_guard.ExposureProportions.two_sided_share` — habitable rooms with two or more "
       "exterior sides", _PROD,
       "Dual-aspect rooms get cross light and ventilation; production already ranks L-massing on it.",
       "Counts sides, not their orientation or view.", "PRODUCTION"),
    _d("windowless_rooms", "exposure_quality", "down", "count",
       "rooms with no placeable window whose exposure policy is REQUIRED or PREFERRED",
       "production windows + EXPOSURE_POLICY",
       "A room the policy wants daylit and did not get.",
       "REQUIRED misses are already impossible in a PASS plan, so this counts PREFERRED misses.",
       "PRODUCTION"),
    _d("max_single_room_facade_share", "exposure_quality", "down", "ratio 0-1",
       "longest exterior wall run belonging to one room over the footprint perimeter",
       "room rects + footprint",
       "One room monopolising the facade starves the rest (§2H).",
       "Perimeter share, not the solar value of each side.", "DERIVED"),
    _d("public_facade_share", "exposure_quality", "up", "ratio 0-1",
       "exterior wall length of PUBLIC_CORE rooms over the footprint perimeter", "room rects + footprint",
       "The rooms people spend the day in should get the frontage.",
       "Treats every side as equal (see MISSING_INFORMATION on orientation).", "DERIVED"),
    _d("bedroom_facade_share", "exposure_quality", "up", "ratio 0-1",
       "exterior wall length of bedroom-class rooms over the footprint perimeter", "room rects + footprint",
       "Bedrooms need their own frontage for light and air.", "Same orientation caveat.", "DERIVED"),
    _d("street_facade_public_share", "exposure_quality", "info", "ratio 0-1",
       "fraction of the street-edge facade held by PUBLIC_CORE rooms", "room rects + footprint",
       "Who faces the street is an architectural stance (public front versus private front), not a "
       "quality: reported, never ranked.",
       "Street side taken from the footprint only.", "DERIVED"),

    # ------------------------------------------------------------------ I. proportion
    _d("mean_net_aspect", "proportion_quality", "down", "ratio",
       "mean net long/short ratio over all rooms", "production net dims",
       "The plan's overall tendency to squeeze rooms.", "A mean hides one terrible room.", "PRODUCTION"),
    _d("max_net_aspect", "proportion_quality", "down", "ratio",
       "largest net long/short ratio over all rooms", "production net dims",
       "The worst-shaped room, which is what a reader notices first.",
       "Every room is already inside its own template bound, so differences here are quality, not legality.",
       "PRODUCTION"),
    _d("worst_wet_aspect", "proportion_quality", "down", "ratio",
       "`l_massing_guard.ExposureProportions.worst_wet_aspect`", _PROD,
       "Wet rooms are where strip shapes concentrate; production already ranks L-massing on it.",
       "Wet rooms only.", "PRODUCTION"),
    _d("sliver_rooms", "proportion_quality", "down", "count",
       f"inhabited rooms (not wet, service or circulation) with a net short side below "
       f"{SLIVER_SHORT_SIDE_M} m", "production net dims + roles",
       "Below roughly two metres a habitable room stops being usable whatever its area.",
       f"The {SLIVER_SHORT_SIDE_M} m line is a documented judgement; production's own sliver floor "
       f"(0.9 m) only catches leftovers.", "DERIVED"),
    _d("min_net_short_side_m", "proportion_quality", "up", "m",
       "smallest net short side over all rooms", "production net dims",
       "The tightest dimension anywhere in the plan.",
       "Wet and service rooms legitimately set this.", "PRODUCTION"),
    _d("furniture_fit_share", "proportion_quality", "up", "ratio 0-1",
       "fraction of rooms whose furniture envelope fits (production's C9 feasibility record)", _PROD,
       "The only furniture signal the pipeline produces today.",
       "A boolean per room: fits or not. Real layout quality (usable wall lengths, clearances) is "
       "measured by `furnishability.py`, whose C30 is defined but NOT called by `validate` — see "
       "MISSING_INFORMATION.", "PRODUCTION"),

    # ------------------------------------------------------------------ J. soft adjacency
    _d("soft_adjacency_lift", "soft_adjacency_quality", "up", "mean lift",
       "mean ResPlan corpus adjacency LIFT over realized touching pairs whose BOTH roles the corpus "
       "can measure (LIVING, KITCHEN, BEDROOM, BATHROOM, BALCONY only)",
       "realized adjacency + `topology_poc.priors.adjacency_table` (17,107 real plans)",
       "The only non-invented source of soft adjacency preference in the repository: how often real "
       "architects put these two roles together relative to chance.",
       "Covers 5 roles; HALL, DINING, MASTER_BEDROOM, SAFE_ROOM, TOILET and the rest are explicitly "
       "UNMEASURABLE by that corpus. Frequency in real plans is also not desirability — and the corpus "
       "is apartments, where for example BEDROOM-LIVING touching is near-universal (lift 1.89) in a way "
       "a detached house need not copy.", "PRODUCTION"),
    _d("measurable_adjacency_coverage", "soft_adjacency_quality", "info", "ratio 0-1",
       "fraction of realized touching pairs for which the prior had data", "as above",
       "States how much of the plan the adjacency prior could see at all — the honesty term for the "
       "metric above.",
       "Low coverage means the lift is weak evidence, not that the plan is bad.", "PRODUCTION"),
)}

#: Qualities §2 asks about that NO available data supports. Reported as a finding (§13 question 2),
#: never faked, never approximated into a ranked metric.
MISSING_INFORMATION: dict[str, str] = {
    "sight_lines_for_secondary_bedrooms_and_public_rooms":
        "Sight lines are computed ONLY for wet rooms (`wet_privacy.direct_sight_line`) and for the MASTER "
        "bedroom (`master_suite.hall_sight_line_to_bed`, which is production code with no production "
        "caller). There is no general room-to-room or door-to-door visibility computation, so '§2C "
        "bedroom doors directly visible from the entrance' is approximated by the door's host room "
        "(`bedroom_doors_off_arrival`), not by actual line of sight, for every bedroom but the master.",
    "client_priorities":
        "No brief field states whether THIS client values privacy over open public space, or bedroom area "
        "over circulation. Without it, any weighting ACROSS dimensions is our taste, not the client's — "
        "which is why #142L ranks by dominance and reports weighting scenarios instead of choosing one.",
    "preferred_adjacency_channel":
        "`TopologyProposal.spatial_adjacency` is a single HARD list: a proposer that wants 'kitchen NEAR "
        "dining, but not necessarily sharing a wall' has no field to say it in, and the critic has no "
        "PREFERRED tier to score. The measured ResPlan priors cover only 5 roles, and they describe "
        "apartments. Everything else in §2J is unsupported by data we hold.",
    "orientation_noise_and_views":
        "The brief carries `street_facing_side` (e.g. NORTH) so facade orientation is KNOWN, but no room "
        "carries a solar, view or noise requirement and `app/geometry_domain` has no solar check (rubric "
        "section O is `not_measured`). Facade metrics therefore treat every side as equal.",
    "furniture_layout_quality":
        "`furnishability.py` computes a real `Usability` tier per room (required objects placed, clearance "
        "satisfied, access path clear, usable wall length, window blocked) and C30 is fully defined and "
        "tested — but C30 is NOT called from `validate()` because it was measured to fail on real valid "
        "plans, and `usability_key` has no caller. So '§2E usable wall lengths' and real furnishability "
        "are COMPUTABLE but not currently trustworthy as a ranking signal without first re-calibrating C30.",
    "circulation_route_geometry":
        "Walking distance is approximated by Manhattan centroid distance. `circulation_metrics` measures "
        "corridor length, turns and dead ends but produces no route polyline through door openings, so "
        "true path length and pinch points along the real route are unavailable.",
    "acoustic_and_thermal_performance":
        "Wall types are structural/semantic (PARTITION, RC_SAFE_ROOM, EXTERIOR, OPEN) with no acoustic or "
        "thermal property, so 'noise transfer' is proxied by shared wall length only.",
    "area_fidelity_target":
        "Rubric section B (Area Fidelity) has NO deterministic signal merged: there is no measure of how "
        "close delivered room areas are to what the person asked for, only that they sit inside the "
        "template band. A plan that systematically under-delivers area cannot be distinguished here.",
}


# ----------------------------------------------------------------------------- helpers

def _role(plan, z):
    r = plan["rooms"].get(z, {}).get("role")
    return ProgramRole(r) if r else None


def _rect(plan, z):
    return plan["rooms"][z]["rect_m"]


def shared_wall_m(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if abs(ax + aw - bx) < EPS or abs(bx + bw - ax) < EPS:
        return max(0.0, min(ay + ah, by + bh) - max(ay, by))
    if abs(ay + ah - by) < EPS or abs(by + bh - ay) < EPS:
        return max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    return 0.0


def contacts(plan) -> dict:
    ids = sorted(plan["rooms"])
    out = {}
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            L = shared_wall_m(_rect(plan, a), _rect(plan, b))
            if L > EPS:
                out[frozenset((a, b))] = round(L, 3)
    return out


def door_graph(plan) -> dict:
    g = {z: set() for z in plan["rooms"]}
    for d in plan["doors"]:
        if d.get("placeable") and d["a"] in g and d["b"] in g:
            g[d["a"]].add(d["b"]); g[d["b"]].add(d["a"])
    for group in plan.get("open_groups") or ():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a in g and b in g:
                    g[a].add(b); g[b].add(a)
    return g


def _bfs(g, start, blocked=frozenset()):
    dist, q = {start: 0}, deque([start])
    while q:
        x = q.popleft()
        for y in sorted(g.get(x, ())):
            if y not in dist and y not in blocked:
                dist[y] = dist[x] + 1
                q.append(y)
    return dist


def _components(zones, pairs):
    adj = {z: set() for z in zones}
    for pr in pairs:
        a, b = tuple(pr)
        if a in adj and b in adj:
            adj[a].add(b); adj[b].add(a)
    seen, comps = set(), []
    for z in sorted(adj):
        if z in seen:
            continue
        comp, stack = {z}, [z]
        seen.add(z)
        while stack:
            for y in adj[stack.pop()]:
                if y not in seen:
                    seen.add(y); comp.add(y); stack.append(y)
        comps.append(sorted(comp))
    return comps


def _aspect(w, h):
    return max(w, h) / max(min(w, h), EPS)


def exterior_run_m(plan, z) -> float:
    x, y, w, h = _rect(plan, z)
    fx, fy, fw, fh = plan["footprint_m"]
    return round((w if abs(y - fy) < EPS else 0) + (w if abs(y + h - (fy + fh)) < EPS else 0)
                 + (h if abs(x - fx) < EPS else 0) + (h if abs(x + w - (fx + fw)) < EPS else 0), 3)


def _b(v, default=0):
    return default if v is None else (1 if v else 0)


# ----------------------------------------------------------------------------- the evaluator

def evaluate(plan: dict, priors=None) -> dict:
    """Raw metric vector for one validator-PASS plan. Deterministic, unweighted, unnormalised."""
    rooms, pq = plan["rooms"], plan["production_quality"]
    roles = {z: _role(plan, z) for z in rooms}
    net = {z: rooms[z]["net_area_m2"] for z in rooms}
    dims = {z: (rooms[z]["net_w_m"], rooms[z]["net_h_m"]) for z in rooms}
    fx, fy, fw, fh = plan["footprint_m"]
    perimeter = 2 * (fw + fh) or EPS
    circ = [z for z in rooms if roles[z] in CIRCULATION_ROLES]
    public = [z for z in rooms if roles[z] in PUBLIC_CORE]
    beds = [z for z in rooms if roles[z] in BEDROOMS]
    secondary = [z for z in rooms if roles[z] is ProgramRole.BEDROOM]
    wet = [z for z in rooms if roles[z] in WET_ROLES]
    inhabited = [z for z in rooms if roles[z] not in set(WET_ROLES) | set(SERVICE_ROLES) | set(CIRCULATION_ROLES)]
    C, g = contacts(plan), door_graph(plan)
    arrival = plan["entrance_door"]["b"]
    dist = _bfs(g, arrival) if arrival in g else {}
    ent_c = plan["entrance_door"]["center_m"]
    resolved_wet = {w[0]: (w[1], w[2]) for w in (plan.get("proposal", {}) or {}).get("wet_rooms") or []}
    m: dict = {}

    cm, es, dsp, pc, pp = pq["circulation"], pq["entrance"], pq["dead_space"], pq["public_composition"], pq["proportions"]

    # A circulation ---------------------------------------------------------
    m["circulation_ratio"] = cm["ratio"]
    m["circulation_longest_segment_m"] = cm["longest_segment_m"] or 0.0
    m["circulation_dead_ends"] = cm["dead_end_count"]
    m["circulation_turns"] = cm["turn_count"]
    m["circulation_duplicated_area_m2"] = cm["duplicated_area_m2"]
    m["circulation_rooms_served"] = len({n for z in circ for n in g.get(z, ()) if n not in circ})
    others = [z for z in rooms if z != arrival]
    reach = [dist[z] for z in others if z in dist]
    m["mean_steps_from_entrance"] = round(statistics.mean(reach), 3) if reach else 0.0
    m["max_steps_from_entrance"] = max(reach) if reach else 0
    walks = [abs(ent_c[0] - (rooms[z]["rect_m"][0] + rooms[z]["rect_m"][2] / 2))
             + abs(ent_c[1] - (rooms[z]["rect_m"][1] + rooms[z]["rect_m"][3] / 2)) for z in others]
    m["mean_walk_from_entrance_m"] = round(statistics.mean(walks), 3) if walks else 0.0
    m["dead_space_share"] = dsp["dead_space_share"]

    # B zoning --------------------------------------------------------------
    pp_wall = sum(L for pr, L in C.items()
                  if any(roles[a] in PUBLIC_CORE for a in pr) and any(roles[a] in BEDROOMS for a in pr))
    m["public_private_wall_m"] = round(pp_wall, 3)
    m["public_private_wall_share"] = round(pp_wall / (sum(C.values()) or EPS), 4)
    blocked = (set(public) - {arrival}) if public else set()
    priv_dist = _bfs(g, arrival, blocked=blocked) if arrival in g else {}
    m["bedrooms_reached_through_public"] = sum(1 for b in beds if b in dist and b not in priv_dist)
    m["public_components"] = len(_components(public, [pr for pr in C if all(roles[a] in PUBLIC_CORE for a in pr)])) if public else 0
    priv_set = set(beds) | {z for z, (k, _h) in resolved_wet.items() if k == "ensuite" and z in rooms}
    m["private_components"] = len(_components(priv_set, [pr for pr in C if all(a in priv_set for a in pr)])) if priv_set else 0
    if public and beds:
        py0 = min(rooms[z]["rect_m"][1] for z in public); py1 = max(rooms[z]["rect_m"][1] + rooms[z]["rect_m"][3] for z in public)
        by0 = min(rooms[z]["rect_m"][1] for z in beds); by1 = max(rooms[z]["rect_m"][1] + rooms[z]["rect_m"][3] for z in beds)
        m["zone_band_overlap"] = round(max(0.0, min(py1, by1) - max(py0, by0)) / max(min(py1 - py0, by1 - by0), EPS), 4)
    else:
        m["zone_band_overlap"] = 0.0

    # C privacy -------------------------------------------------------------
    m["bedroom_doors_off_public"] = sum(1 for b in beds if any(roles[n] in PUBLIC_CORE for n in g.get(b, ())))
    m["bedroom_doors_off_arrival"] = sum(1 for b in beds if arrival in g.get(b, ()))
    suites = pq["master_suite"]["records"]
    m["master_hall_sight_line_to_bed"] = max((_b(s["hall_sight_line_to_bed"]) for s in suites), default=0)
    m["master_suite_score"] = round(max((s["suite_score"] for s in suites), default=0.0), 4)
    wp = plan.get("wet_privacy") or []
    m["wet_doors_to_public"] = sum(1 for w in wp if (w.get("entered_from_class") or "").upper() == "PUBLIC")
    m["wet_direct_sight_lines"] = sum(1 for w in wp if w.get("direct_sight_line"))
    m["wet_privacy_worst"] = round(max((w.get("privacy_score") or 0.0 for w in wp), default=0.0), 4)
    bsteps = [dist[b] for b in beds if b in dist]
    m["entrance_to_bedroom_steps"] = min(bsteps) if bsteps else 0

    # D entrance ------------------------------------------------------------
    m["arrival_is_circulation"] = _b(es["is_circulation_arrival"])
    m["entrance_pocket_m"] = es["pocket_length_m"] if es["pocket_length_m"] is not None else 0.0
    m["entrance_distance_to_public_m"] = es["distance_to_public_m"] if es["distance_to_public_m"] is not None else 0.0
    m["entrance_private_doors_passed"] = es["private_doors_passed"]
    m["arrival_fanout"] = len(g.get(arrival, ()))
    living = next((z for z in rooms if roles[z] is ProgramRole.LIVING), None)
    m["steps_entrance_to_living"] = dist.get(living, 0) if living else 0

    # E public zone ---------------------------------------------------------
    m["public_zone_coherent"] = _b(pc["public_zone_coherent"])
    m["kitchen_dining_related"] = _b(pc["kitchen_dining_related"], default=1)
    m["living_exterior_exposed"] = _b(pc["living_exterior_exposed"])
    pub_pairs = [pr for pr in C if all(roles[a] in PUBLIC_CORE for a in pr)]
    comps = _components(public, pub_pairs) if public else []
    best = max(comps, key=lambda c: sum(net[z] for z in c)) if comps else []
    m["public_largest_cluster_share"] = round(sum(net[z] for z in best) / (sum(net[z] for z in public) or EPS), 4) if public else 0.0
    inner = [C[pr] for pr in pub_pairs if all(a in best for a in pr)]
    m["public_narrowest_neck_m"] = round(min(inner), 3) if inner else round(min(dims[best[0]]) if best else 0.0, 3)
    if best:
        bx0 = min(rooms[z]["rect_m"][0] for z in best); bx1 = max(rooms[z]["rect_m"][0] + rooms[z]["rect_m"][2] for z in best)
        by0 = min(rooms[z]["rect_m"][1] for z in best); by1 = max(rooms[z]["rect_m"][1] + rooms[z]["rect_m"][3] for z in best)
        m["public_compactness"] = round(sum(net[z] for z in best) / max((bx1 - bx0) * (by1 - by0), EPS), 4)
    else:
        m["public_compactness"] = 0.0
    m["public_worst_aspect"] = round(max((_aspect(*dims[z]) for z in public), default=0.0), 3)

    # F bedrooms ------------------------------------------------------------
    m["bedroom_worst_aspect"] = round(pp["bedroom_max"] if pp["bedroom_max"] is not None
                                      else max((_aspect(*dims[z]) for z in secondary), default=0.0), 3)
    m["master_aspect"] = round(pp["master"] if pp["master"] is not None else 0.0, 3)
    m["bedroom_min_net_area_m2"] = round(min((net[z] for z in beds), default=0.0), 3)
    m["bedroom_min_short_side_m"] = round(min((min(dims[z]) for z in beds), default=0.0), 3)
    m["bedroom_area_cv"] = round(statistics.pstdev([net[z] for z in secondary]) /
                                 (statistics.mean([net[z] for z in secondary]) or EPS), 4) if len(secondary) > 1 else 0.0
    master = next((z for z in rooms if roles[z] is ProgramRole.MASTER_BEDROOM), None)
    m["master_is_largest_bedroom"] = 1 if (master and beds and net[master] >= max(net[z] for z in beds) - EPS) else (0 if master else 1)
    m["bedrooms_with_window"] = round(sum(1 for z in beds if any(w.get("placeable") for w in rooms[z].get("windows", []))) / (len(beds) or EPS), 4) if beds else 1.0
    m["bedroom_public_wall_m"] = round(sum(L for pr, L in C.items()
                                           if any(a in beds for a in pr) and any(roles[a] in PUBLIC_CORE for a in pr)), 3)
    m["bedrooms_entered_from_circulation"] = round(
        sum(1 for b in beds if any(roles[n] in CIRCULATION_ROLES for n in g.get(b, ()))) / (len(beds) or EPS), 4) if beds else 1.0

    # G wet core ------------------------------------------------------------
    wc = plan.get("wet_core") or {}
    m["plumbing_complexity_index"] = wc.get("plumbing_complexity_index", 0)
    m["wet_shared_wall_m"] = round(wc.get("shared_wall_length_m", 0.0), 3)
    m["wet_cluster_count"] = wc.get("cluster_count", 0)
    m["wet_adjacency_share"] = round(pp["wet_share"] if pp["wet_share"] is not None else 1.0, 4)
    m["wet_rooms_with_window"] = round(sum(1 for z in wet if any(w.get("placeable") for w in rooms[z].get("windows", []))) / (len(wet) or EPS), 4) if wet else 1.0
    ens = [(z, h) for z, (k, h) in resolved_wet.items() if k == "ensuite" and z in rooms and h in rooms]
    m["ensuite_adjacent_to_host"] = round(sum(1 for z, h in ens if C.get(frozenset((z, h)), 0.0) > EPS) / len(ens), 4) if ens else 1.0

    # H exposure ------------------------------------------------------------
    pref = [z for z in rooms if roles[z] and EXPOSURE_POLICY[roles[z]].exterior_wall is ExposureRequirement.PREFERRED]
    m["preferred_exposure_satisfied"] = round(sum(1 for z in pref if exterior_run_m(plan, z) > EPS) / len(pref), 4) if pref else 1.0
    m["two_sided_exposure_share"] = round(pp["two_sided_share"] if pp["two_sided_share"] is not None else 0.0, 4)
    want = [z for z in rooms if roles[z] and EXPOSURE_POLICY[roles[z]].exterior_wall in
            (ExposureRequirement.REQUIRED, ExposureRequirement.PREFERRED)]
    m["windowless_rooms"] = sum(1 for z in want if not any(w.get("placeable") for w in rooms[z].get("windows", [])))
    runs = {z: exterior_run_m(plan, z) for z in rooms}
    m["max_single_room_facade_share"] = round(max(runs.values(), default=0.0) / perimeter, 4)
    m["public_facade_share"] = round(sum(runs[z] for z in public) / perimeter, 4)
    m["bedroom_facade_share"] = round(sum(runs[z] for z in beds) / perimeter, 4)
    street = sum(rooms[z]["rect_m"][2] for z in rooms if abs(rooms[z]["rect_m"][1] - fy) < EPS)
    m["street_facade_public_share"] = round(sum(rooms[z]["rect_m"][2] for z in public
                                                if abs(rooms[z]["rect_m"][1] - fy) < EPS) / (street or EPS), 4)

    # I proportion ----------------------------------------------------------
    asp = [_aspect(*dims[z]) for z in rooms]
    m["mean_net_aspect"] = round(statistics.mean(asp), 3)
    m["max_net_aspect"] = round(max(asp), 3)
    m["worst_wet_aspect"] = round(pp["worst_wet_aspect"] if pp["worst_wet_aspect"] is not None else 0.0, 3)
    m["sliver_rooms"] = sum(1 for z in inhabited if min(dims[z]) < SLIVER_SHORT_SIDE_M)
    m["min_net_short_side_m"] = round(min(min(dims[z]) for z in rooms), 3)
    ff = plan.get("furniture_fits") or {}
    m["furniture_fit_share"] = round(sum(1 for v in ff.values() if v) / len(ff), 4) if ff else 1.0

    # J soft adjacency ------------------------------------------------------
    lift_sum = lift_n = cov_n = 0
    lift_sum = 0.0
    for pr in C:
        a, b = tuple(pr)
        cov_n += 1
        v = _prior_lift(priors, roles[a], roles[b])
        if v is not None:
            lift_sum += v; lift_n += 1
    m["soft_adjacency_lift"] = round(lift_sum / lift_n, 4) if lift_n else 0.0
    m["measurable_adjacency_coverage"] = round(lift_n / (cov_n or EPS), 4) if cov_n else 0.0
    return m


def _prior_lift(priors, ra, rb):
    """Measured ResPlan adjacency lift for a realized role pair, or None when that corpus cannot
    measure one of the two roles."""
    if priors is None or ra is None or rb is None:
        return None
    rows = getattr(getattr(priors, "adjacency_table", None), "rows", None)
    if not rows:
        return None
    key = {ra.value, rb.value}
    for row in rows:
        if {row.role_a, row.role_b} == key and getattr(row, "meets_min_support", True):
            return row.lift
    return None


__all__ = ["METRICS", "DIMENSIONS", "MISSING_INFORMATION", "MetricDef", "evaluate", "contacts",
           "door_graph", "shared_wall_m", "exterior_run_m"]
