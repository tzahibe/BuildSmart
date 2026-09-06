"""Architectural planning layer: decides room-access topology (an `ArchitecturalConcept`) BEFORE
geometry, then has the existing GeometrySolver realize that decision as hard constraints.

    ArchitecturalSpec
        -> concept_generation.generate_concepts()   (bounded, deterministic, graph-only)
        -> planner.plan_with_concepts()             (realize each concept via GeometrySolver with
                                                     required_edges, refine with Spatial V2.1 inside
                                                     the concept, score with Spatial V2, select tiered)
        -> GeometricDesign                          (unchanged contract)

See ARCHITECTURAL REVIEW -> "topology before geometry": this is the first production slice of it.
"""
