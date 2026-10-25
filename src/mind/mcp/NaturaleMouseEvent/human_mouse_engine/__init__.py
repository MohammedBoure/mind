"""
AI Natural Human Mouse Engine Package.

Provides high-level programmatic APIs, PyTorch neural trajectory generators,
and biomechanical kinematic shaping filters for authentic human-like mouse simulation.
"""

from .human_mouse import (
    HumanMouse,
    HumanMouseSimulator,
    apply_biomechanical_kinematic_filter,
    MemoryConditionedMouseGenerator,
    ExtendedConditioningEncoder,
    KinematicDecoder,
    ActionHead,
    ContinuousTremorGenerator,
    sample_target_within_box,
    compute_terminal_momentum,
    PYAUTOGUI_AVAILABLE,
)

__all__ = [
    "HumanMouse",
    "HumanMouseSimulator",
    "apply_biomechanical_kinematic_filter",
    "MemoryConditionedMouseGenerator",
    "ExtendedConditioningEncoder",
    "KinematicDecoder",
    "ActionHead",
    "ContinuousTremorGenerator",
    "sample_target_within_box",
    "compute_terminal_momentum",
    "PYAUTOGUI_AVAILABLE",
]
