# Examples & Testing Suite

This directory contains executable demonstrations, statistical benchmarks, simulation scripts, and visual verification tools for NaturaleMouseEvent.

## Files

- **`demo_test.py`**: Full interactive demonstration and testing suite. Provides CLI menus and direct execution flags:
  - `--mode dry-run`: Non-movement statistical benchmark evaluating reach accuracy and duration distributions.
  - `--mode live`: Live physical cursor navigation across multi-point screen waypoints with dynamic curvature.
  - `--mode click`: Precision targeting and authentic mouse click testing.
  - `--mode wander`: Micro-tremor and biological idle wandering demonstration.
  - `--mode plot`: Exports multi-panel kinematic analysis chart to `docs/trajectory_demo.png`.
- **`compare_human_vs_bot.py`**: Side-by-side trajectory and velocity profile comparison generator between AI human trajectories and conventional linear bots. Outputs to `docs/human_vs_bot_comparison.png`.
- **`simulate_mouse.py`**: Lightweight standalone dry-run simulation script generating step-by-step coordinates without physical mouse control.

## Running Examples

Execute any example script directly from the repository root:

```bash
# Run dry-run benchmark with production model
python examples/demo_test.py --mode dry-run --model models/production_mouse_model.pth

# Export kinematic trajectory visualization
python examples/demo_test.py --mode plot --model models/production_mouse_model.pth

# Run human vs bot comparison plot generator
python examples/compare_human_vs_bot.py

# Run offline simulation
python examples/simulate_mouse.py
```
