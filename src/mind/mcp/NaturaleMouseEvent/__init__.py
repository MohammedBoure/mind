"""NaturaleMouseEvent: AI Natural Human Mouse Trajectory Engine package.

Exposes high-level programmatic APIs, PyTorch neural trajectory generators,
and biomechanical kinematic shaping filters for authentic human-like mouse simulation.
"""

from .human_mouse_engine import (
    HumanMouse,
    HumanMouseSimulator,
    apply_biomechanical_kinematic_filter,
)

__all__ = [
    "HumanMouse",
    "HumanMouseSimulator",
    "apply_biomechanical_kinematic_filter",
]
