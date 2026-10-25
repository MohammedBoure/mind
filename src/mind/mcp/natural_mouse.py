"""AI-powered Natural Human Mouse Movement Controller and MCP integration wrapper.

Wraps the PyTorch-based NaturaleMouseEvent / human_mouse_engine with safe fallbacks
for headless Linux environments (absence of DISPLAY / WAYLAND_DISPLAY) and missing
GUI libraries, providing both authentic AI-generated trajectories and high-fidelity
biomechanical kinematic simulations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
import sys
import time
from typing import Any, Sequence

logger = logging.getLogger("mind.mcp.natural_mouse")

# PyAutoGUI safe import
PYAUTOGUI_AVAILABLE = False
pyautogui = None
try:
    import pyautogui as _pag
    _pag.PAUSE = 0.0
    pyautogui = _pag
    PYAUTOGUI_AVAILABLE = True
except Exception:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None


def is_headless_environment() -> bool:
    """Detect whether current execution environment is running without an active display server."""
    if sys.platform.startswith("linux"):
        display = os.environ.get("DISPLAY")
        wayland = os.environ.get("WAYLAND_DISPLAY")
        if not display and not wayland:
            return True
    return False


class NaturalMouseController:
    """High-level AI Natural Mouse Controller with dynamic neural and kinematic fallback."""

    def __init__(self, model_path: str | None = None, dry_run: bool | None = None) -> None:
        self.headless = is_headless_environment()
        self.dry_run = self.headless if dry_run is None else dry_run
        self.screen_w = 1920.0
        self.screen_h = 1080.0
        self.virtual_pos = [960.0, 540.0]
        self.engine_type = "pure_kinematics"
        self._human_mouse = None

        # Resolve screen resolution if display server is available
        if PYAUTOGUI_AVAILABLE and not self.dry_run:
            try:
                w, h = pyautogui.size()
                self.screen_w = float(w)
                self.screen_h = float(h)
                pos = pyautogui.position()
                self.virtual_pos = [float(pos[0]), float(pos[1])]
            except Exception as exc:
                logger.debug("Failed querying display size, falling back to dry-run: %s", exc)
                self.dry_run = True

        # Attempt to load PyTorch neural HumanMouse engine
        self._init_neural_engine(model_path)

    def _init_neural_engine(self, model_path: str | None) -> None:
        """Attempt to initialize the PyTorch HumanMouse engine from NaturaleMouseEvent."""
        try:
            # Add package search paths
            base_dir = os.path.dirname(os.path.abspath(__file__))
            nat_dir = os.path.join(base_dir, "NaturaleMouseEvent")
            engine_dir = os.path.join(nat_dir, "human_mouse_engine")
            for d in [nat_dir, engine_dir]:
                if d not in sys.path:
                    sys.path.insert(0, d)

            from human_mouse_engine import HumanMouse  # type: ignore

            # Discover model checkpoint
            resolved_model = model_path
            if not resolved_model:
                candidates = [
                    os.path.join(nat_dir, "models", "production_mouse_model.pth"),
                    os.path.join(nat_dir, "models", "human_mouse_model.pt"),
                    os.path.join(engine_dir, "human_mouse_model.pt"),
                ]
                for c in candidates:
                    if os.path.exists(c):
                        resolved_model = c
                        break

            self._human_mouse = HumanMouse(
                model_path=resolved_model,
                failsafe=True,
                dry_run=self.dry_run,
            )
            self.screen_w = float(self._human_mouse.screen_w)
            self.screen_h = float(self._human_mouse.screen_h)
            pos = self._human_mouse.get_current_position()
            self.virtual_pos = [float(pos[0]), float(pos[1])]
            self.engine_type = "pytorch_neural_engine"
            logger.info("NaturalMouseController initialized with PyTorch neural engine.")
        except Exception as exc:
            logger.debug("Neural engine unavailable (%s), using pure biomechanical kinematics.", exc)
            self._human_mouse = None
            self.engine_type = "biomechanical_kinematics_fallback"

    def get_position(self) -> dict[str, Any]:
        """Return current mouse position and execution state."""
        if self._human_mouse is not None and not self.dry_run and PYAUTOGUI_AVAILABLE:
            try:
                pos = self._human_mouse.get_current_position()
                self.virtual_pos = [float(pos[0]), float(pos[1])]
            except Exception:
                pass
        elif PYAUTOGUI_AVAILABLE and not self.dry_run:
            try:
                pos = pyautogui.position()
                self.virtual_pos = [float(pos[0]), float(pos[1])]
            except Exception:
                pass

        return {
            "status": "success",
            "x": round(self.virtual_pos[0], 2),
            "y": round(self.virtual_pos[1], 2),
            "dry_run": self.dry_run,
            "engine": self.engine_type,
            "mode": "headless_simulation" if self.dry_run else "live_execution",
        }

    def _generate_kinematic_trajectory(
        self,
        start_x: float,
        start_y: float,
        target_x: float,
        target_y: float,
        duration_ms: float | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a biologically authentic human trajectory using Flash & Hogan (1985) minimum-jerk kinematics."""
        dx = target_x - start_x
        dy = target_y - start_y
        dist = math.hypot(dx, dy)

        if dist < 1.0:
            return [{"x": float(target_x), "y": float(target_y), "dt_ms": 0.0, "type": "move"}]

        # Fitts's Law duration allocation if not manually requested
        if duration_ms is not None and duration_ms > 0:
            total_time_s = duration_ms / 1000.0
        else:
            w_ref = 50.0
            id_fitts = math.log2(1.0 + dist / w_ref)
            total_time_s = 0.18 + 0.14 * id_fitts
            total_time_s = max(0.20, min(1.10, total_time_s))

        step_dt_s = 0.008  # ~125 Hz standard human polling interval
        num_steps = max(18, min(120, int(round(total_time_s / step_dt_s))))
        dt_ms = (total_time_s / num_steps) * 1000.0

        # Tangential subtle curvature perpendicular to line of reach
        ux = dx / dist
        uy = dy / dist
        perp_x = -uy
        perp_y = ux
        curve_amp = (random.random() - 0.5) * 0.08 * dist

        trajectory: list[dict[str, Any]] = []
        ou_tremor_x = 0.0
        ou_tremor_y = 0.0
        theta = 15.0
        sigma = 0.35

        for i in range(num_steps + 1):
            tau = i / float(num_steps)
            # Minimum-Jerk polynomial trajectory: s(tau) = 10*tau^3 - 15*tau^4 + 6*tau^5
            s = 10.0 * (tau ** 3) - 15.0 * (tau ** 4) + 6.0 * (tau ** 5)
            # Parabolic curvature envelope: 4*tau*(1 - tau)
            arc = 4.0 * tau * (1.0 - tau) * curve_amp

            # Ornstein-Uhlenbeck micro-tremor process (dampens during landing phase)
            landing_suppression = (1.0 - tau) ** 1.5
            ou_tremor_x += -theta * ou_tremor_x * step_dt_s + sigma * random.gauss(0, 1) * math.sqrt(step_dt_s)
            ou_tremor_y += -theta * ou_tremor_y * step_dt_s + sigma * random.gauss(0, 1) * math.sqrt(step_dt_s)

            px = start_x + dx * s + perp_x * arc + ou_tremor_x * landing_suppression
            py = start_y + dy * s + perp_y * arc + ou_tremor_y * landing_suppression

            # Enforce strict boundary anchoring
            if i == 0:
                px, py = start_x, start_y
            elif i == num_steps:
                px, py = target_x, target_y

            trajectory.append({
                "x": round(px, 2),
                "y": round(py, 2),
                "dt_ms": round(dt_ms, 2) if i > 0 else 0.0,
                "type": "move",
            })

        return trajectory

    async def move(
        self,
        target_x: float,
        target_y: float,
        duration_ms: float | None = None,
    ) -> dict[str, Any]:
        """Move cursor naturally from current position to target coordinates."""
        start_x, start_y = self.virtual_pos[0], self.virtual_pos[1]
        dist = math.hypot(target_x - start_x, target_y - start_y)
        start_time = time.perf_counter()

        # Generate trajectory via PyTorch neural model or kinematic filter
        if self._human_mouse is not None:
            try:
                traj = await asyncio.to_thread(
                    self._human_mouse.generate_trajectory,
                    (start_x, start_y),
                    (target_x, target_y),
                )
                if duration_ms and duration_ms > 0 and len(traj) > 1:
                    scale = duration_ms / sum(max(1.0, s["dt_ms"]) for s in traj[1:])
                    for s in traj[1:]:
                        s["dt_ms"] *= scale

                if not self.dry_run and PYAUTOGUI_AVAILABLE:
                    await asyncio.to_thread(self._human_mouse._execute_trajectory, traj)
            except Exception as exc:
                logger.debug("Neural move execution failed (%s), fallback to kinematic.", exc)
                traj = self._generate_kinematic_trajectory(start_x, start_y, target_x, target_y, duration_ms)
        else:
            traj = self._generate_kinematic_trajectory(start_x, start_y, target_x, target_y, duration_ms)
            if not self.dry_run and PYAUTOGUI_AVAILABLE:
                def _exec():
                    for pt in traj:
                        pyautogui.moveTo(int(pt["x"]), int(pt["y"]))
                        if pt["dt_ms"] > 0:
                            time.sleep(pt["dt_ms"] / 1000.0)
                await asyncio.to_thread(_exec)

        # Update persistent virtual position
        self.virtual_pos = [float(target_x), float(target_y)]
        if self._human_mouse is not None:
            self._human_mouse._virtual_pos = (int(target_x), int(target_y))

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        theoretical_duration = sum(s["dt_ms"] for s in traj) if traj else 0.0

        return {
            "status": "success",
            "action": "natural_mouse_move",
            "from": {"x": round(start_x, 2), "y": round(start_y, 2)},
            "to": {"x": round(target_x, 2), "y": round(target_y, 2)},
            "distance_px": round(dist, 2),
            "steps": len(traj),
            "duration_ms": round(duration_ms if duration_ms else theoretical_duration, 2),
            "execution_time_ms": round(elapsed_ms, 2),
            "dry_run": self.dry_run,
            "engine": self.engine_type,
            "mode": "headless_simulation" if self.dry_run else "live_execution",
        }

    async def click(
        self,
        target_x: float,
        target_y: float,
        button: str = "left",
        clicks: int = 1,
    ) -> dict[str, Any]:
        """Move cursor naturally to target and perform human-like click(s)."""
        clean_button = button.lower() if button else "left"
        if clean_button not in ("left", "right", "middle"):
            clean_button = "left"

        click_count = max(1, int(clicks))
        move_result = await self.move(target_x, target_y)

        # Perform click action
        if not self.dry_run and PYAUTOGUI_AVAILABLE:
            def _do_click():
                for c in range(click_count):
                    pyautogui.click(button=clean_button)
                    if c < click_count - 1:
                        time.sleep(random.uniform(0.06, 0.12))  # Authentic inter-click latency
            await asyncio.to_thread(_do_click)

        return {
            "status": "success",
            "action": "natural_mouse_click",
            "clicked_at": {"x": round(target_x, 2), "y": round(target_y, 2)},
            "button": clean_button,
            "clicks": click_count,
            "move_steps": move_result.get("steps", 0),
            "move_duration_ms": move_result.get("duration_ms", 0.0),
            "dry_run": self.dry_run,
            "engine": self.engine_type,
            "mode": "headless_simulation" if self.dry_run else "live_execution",
        }

    async def sequence(
        self,
        coordinates: Sequence[Any],
        delay_between: float = 0.2,
        click_targets: bool = False,
    ) -> dict[str, Any]:
        """Execute a fluid multi-target sequence with kinematic momentum chaining."""
        parsed_targets: list[tuple[float, float]] = []

        # Parse arbitrary sequence formats (tuples, lists, dicts)
        for item in coordinates:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                parsed_targets.append((float(item[0]), float(item[1])))
            elif isinstance(item, dict) and "x" in item and "y" in item:
                parsed_targets.append((float(item["x"]), float(item["y"])))
            elif isinstance(item, str) and "," in item:
                parts = item.split(",")
                parsed_targets.append((float(parts[0].strip()), float(parts[1].strip())))

        if not parsed_targets:
            return {
                "status": "error",
                "message": "No valid coordinates provided for sequence.",
                "coordinates_received": coordinates,
            }

        total_steps = 0
        total_duration_ms = 0.0
        step_results: list[dict[str, Any]] = []

        for i, (tx, ty) in enumerate(parsed_targets):
            is_last = (i == len(parsed_targets) - 1)
            res = await self.move(tx, ty)
            total_steps += res.get("steps", 0)
            total_duration_ms += res.get("duration_ms", 0.0)

            if click_targets:
                if not self.dry_run and PYAUTOGUI_AVAILABLE:
                    await asyncio.to_thread(pyautogui.click)

            step_results.append({
                "target": {"x": round(tx, 2), "y": round(ty, 2)},
                "steps": res.get("steps", 0),
                "duration_ms": res.get("duration_ms", 0.0),
            })

            if not is_last and delay_between > 0:
                if not self.dry_run:
                    await asyncio.sleep(delay_between)
                total_duration_ms += delay_between * 1000.0

        final_pos = self.virtual_pos
        return {
            "status": "success",
            "action": "natural_mouse_sequence",
            "targets_count": len(parsed_targets),
            "waypoints": [{"x": p[0], "y": p[1]} for p in parsed_targets],
            "final_position": {"x": round(final_pos[0], 2), "y": round(final_pos[1], 2)},
            "total_steps": total_steps,
            "total_duration_ms": round(total_duration_ms, 2),
            "click_targets": click_targets,
            "dry_run": self.dry_run,
            "engine": self.engine_type,
            "mode": "headless_simulation" if self.dry_run else "live_execution",
        }


# Global singleton instance
_controller_instance: NaturalMouseController | None = None


def get_natural_mouse_controller() -> NaturalMouseController:
    """Retrieve or initialize the global NaturalMouseController singleton."""
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = NaturalMouseController()
    return _controller_instance


def reset_natural_mouse_controller() -> None:
    """Reset the global NaturalMouseController instance (for test isolation)."""
    global _controller_instance
    _controller_instance = None
