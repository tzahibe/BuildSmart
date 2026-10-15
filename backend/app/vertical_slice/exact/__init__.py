"""The exact sizer and the cross-band families of the shape-agnostic realizer (#197/#200), moved
out of the research harness so the brain can use them. `scipy` (HiGHS) is a declared dependency;
the oracles import it lazily and every caller falls back, typed, to production's band sizer when
it is missing or a solve returns UNKNOWN. Nothing here names a shape."""
