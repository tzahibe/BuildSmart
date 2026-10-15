"""Moved to `app.vertical_slice.exact.milp_oracle` (the brain uses it); this name stays for the harness and its tests."""
from app.vertical_slice.exact.milp_oracle import *
from app.vertical_slice.exact.milp_oracle import (  # noqa: F401
    BIG,
    _height_grid,
    _spine_once,
    _target_objective,
)
