# 🤖 AI Natural Human Mouse Engine

An AI-powered natural human mouse trajectory generation and execution engine built with **PyTorch** and **PyAutoGUI**. 

This package generates realistic, human-like mouse movements using trained neural networks and advanced biomechanical kinematic shaping. It eliminates robotic straight-line cursor movements by introducing natural micro-variations, global proportional bell rescaling ($V_{\text{target\_max}}(D) = \operatorname{clip}(V_{\text{base}} + \alpha \sqrt{D}, 1600.0, 2300.0)$), neuromuscular onset inertia with quintic smoothstep ramp ($w(t) = 6\tau^5 - 15\tau^4 + 10\tau^3$), jerk-free cosine waypoint momentum blending, continuous Savitzky-Golay coordinate smoothing, Hann acceleration relaxation ramp across drive-to-deceleration inflection, 8-12 Hz neuromuscular physiological tremor, and a Windows 1ms multimedia timer loop with sub-millisecond execution precision.

---

## 📁 Package Structure

```
human_mouse_engine/
├── __init__.py             # Package Exports (HumanMouse, Simulator, Kinematic Filters)
├── human_mouse.py          # Core AI Engine Module (HumanMouse & Biomechanical Shaping)
├── execute_mouse_action.py # Standalone Command-Line (CLI) Executable Tool
├── human_mouse_model.pt    # Embedded PyTorch Neural Network Weights
├── requirements.txt        # Engine Python Dependencies List
└── README.md               # Engine Documentation & Usage Guide
```

---

## ⚙️ Installation & Requirements

### 1. Prerequisites
- Python **3.10+** (Python 3.12 / 3.14 supported)

### 2. Install Dependencies
Run the following command to install required Python libraries:

```bash
pip install -r requirements.txt
```

*Required Dependencies:*
- `torch` (PyTorch for running model inference)
- `numpy` (Numerical matrix calculations)
- `pyautogui` (Physical mouse control)

---

## 🚀 1. Command-Line Interface (CLI Usage)

You can execute natural mouse actions directly from your terminal using `execute_mouse_action.py`.

### Examples

#### Move to a target coordinate and click:
```bash
python execute_mouse_action.py --x 800 --y 500 --click
```

#### Execute a continuous multi-target sequence:
```bash
python execute_mouse_action.py --sequence "400,300;1200,200;900,600"
```

#### Run the built-in 10-target AI demo:
```bash
python execute_mouse_action.py --demo
```

#### Run in dry-run simulation mode (does not move physical cursor):
```bash
python execute_mouse_action.py --dry-run --x 500 --y 300
```

### CLI Arguments Reference

| Option | Type | Description |
| :--- | :--- | :--- |
| `--model` | String | Path to custom PyTorch checkpoint (default: auto-discovers `models/production_mouse_model.pth`, `human_mouse_model.pt`, etc.) |
| `--x` | Integer | Target X coordinate on screen |
| `--y` | Integer | Target Y coordinate on screen |
| `--click` | Flag | Performs a left mouse click after reaching target |
| `--sequence` | String | Semicolon-separated coordinates e.g. `"400,300;1200,200"` |
| `--demo` | Flag | Executes a 10-target natural trajectory demo |
| `--delay` | Float | Pause duration (seconds) between targets (Default: `0.4`) |
| `--dry-run` | Flag | Simulates trajectory generation without physical mouse movement |
| `--no-failsafe` | Flag | Disables PyAutoGUI corner escape safety check |

---

## 🐍 2. Python Programmatic API Usage

You can import `HumanMouse` into your own Python automation scripts (Selenium, Playwright, PyAutoGUI, custom bots).

```python
from human_mouse import HumanMouse

# 1. Initialize Human Mouse AI Engine
mouse = HumanMouse()

# 2. Smoothly move mouse to (800, 400)
mouse.move_to(target_x=800, target_y=400)

# 3. Move mouse to (1200, 600) and click
mouse.click_at(target_x=1200, target_y=600, button='left')

# 4. Move across a continuous sequence of targets
targets = [(400, 300), (900, 500), (600, 800)]
mouse.move_sequence(targets, click_targets=False, delay_between=0.3)

# 5. Pass custom prior movement context (momentum/velocity)
custom_context = (0.05, -0.02, 0.0, 0.1) # (vx, vy, click_density, avg_dt)
mouse.move_to(800, 400, prev_context=custom_context)

# 6. Manually set or get persistent context
mouse.set_context(vx=0.08, vy=-0.03, clicks=0.0, avg_dt=0.1)
current_ctx = mouse.get_context()
```

---

## 🛠️ API Reference (`HumanMouse` Class)

### `HumanMouse(model_path=None, failsafe=True, dry_run=False)`
- **`model_path`**: Custom path to `.pt` weights file. Defaults to `human_mouse_model.pt`.
- **`failsafe`**: Enables PyAutoGUI fail-safe protection.
- **`dry_run`**: If `True`, simulates trajectories without moving the physical mouse.

### Main Methods

- **`move_to(target_x, target_y, click=False, button='left', delay_after=0.1, prev_context=None, target_radius=5.0)`**
  Moves cursor naturally from current position to `(target_x, target_y)` with biological easing convergence.
  Accepts optional `prev_context` tuple `(vx, vy, click_density, avg_dt)` to condition momentum, and `target_radius` tolerance.
  
- **`click_at(target_x, target_y, button='left', delay_after=0.1, prev_context=None, target_radius=5.0)`**
  Moves cursor naturally and performs click at destination. Accepts optional `prev_context` and `target_radius`.

- **`move_sequence(target_list, click_targets=False, delay_between=0.4, target_radius=5.0)`**
  Moves smoothly across a list of `(x, y)` targets maintaining velocity momentum context automatically across targets.

- **`set_context(vx=0.0, vy=0.0, clicks=0.0, avg_dt=0.1)`**
  Manually overrides the internal 4D momentum context vector.

- **`get_context()`**
  Returns the active 4D momentum context tuple `(vx, vy, clicks, avg_dt)`.

- **`generate_trajectory(start_pos, target_pos, prev_context=None, intent=1.0, target_radius=5.0)`**
  Returns a list of dict steps `[{'x': int, 'y': int, 'dt_ms': float, 'type': str}]` with smooth biological easing and zero teleportation.

---

## 🧪 Verification

To test that everything works in your environment:

```bash
python execute_mouse_action.py --dry-run --x 500 --y 300
```
