# NaturaleMouseEvent: AI Natural Human Mouse Trajectory Engine

An AI-powered system designed to generate biologically authentic, human-like mouse cursor trajectories and interactions using behavioral biometrics, kinematics modeling, and PyTorch.

## Repository Architecture & Modular Layout

```
NaturaleMouseEvent/
├── human_mouse_engine/        # Standalone packaged AI engine & execution layer
│   ├── __init__.py            # Package exports (HumanMouse, Simulator, Kinematics)
│   ├── human_mouse.py         # Core API, GRU neural models & neuromuscular filtering
│   ├── execute_mouse_action.py# Standalone CLI cursor controller
│   ├── human_mouse_model.pt   # Embedded standalone model weights
│   ├── requirements.txt       # Engine minimal dependencies
│   └── README.md              # Engine documentation
├── pipeline/                  # Data engineering & deep learning pipelines
│   ├── data_prep/             # SQLite parsing, trajectory filtering & .npz export
│   │   ├── preprocess_all_sqlite.py
│   │   ├── prepare_dataset.py
│   │   ├── scan_dbs.py
│   │   ├── analyze_dur.py
│   │   └── README.md
│   ├── training/              # PyTorch model training pipelines
│   │   ├── train_pilot.py     # Kinematic Memory & Production training (AMP FP16)
│   │   ├── train_model.py     # Scheduled Sampling baseline training
│   │   └── README.md
│   └── README.md              # Pipeline architecture documentation
├── examples/                  # Demonstration, benchmarking & visual test scripts
│   ├── demo_test.py           # Full interactive CLI demo & benchmark suite
│   ├── compare_human_vs_bot.py# Side-by-side human vs. bot trajectory comparison
│   ├── simulate_mouse.py      # Standalone headless trajectory simulation
│   └── README.md              # Examples documentation & usage guide
├── models/                    # Trained PyTorch neural network checkpoints
│   ├── production_mouse_model.pth # 100% full dataset trained checkpoint
│   ├── human_mouse_model.pt       # Compact deployment weights
│   └── README.md                  # Model architecture specifications & benchmarks
├── docs/                      # Visual artifacts & documentation assets
│   ├── trajectory_demo.png        # Kinematic momentum chaining & acceleration plot
│   ├── human_vs_bot_comparison.png# Spatial path & velocity profile comparison
│   └── README.md                  # Documentation assets index
├── data/                      # Telemetry databases & preprocessed tensors
│   ├── mouse_dataset_fixed_N256_full.npz
│   └── README.md                  # Dataset specifications & tensor schema
└── requirements.txt           # Complete repository dependencies
```

---

## Key Features & Kinematics Modeling

- **Biomechanical Kinematic Shaping (`apply_biomechanical_kinematic_filter`)**:
  - *Savitzky-Golay Smoothing*: Continuous 2nd-order polynomial coordinate filtering ($w=9, p=2$) with strict endpoint anchoring.
  - *Neuromuscular Onset Inertia*: Quintic smoothstep ramp ($w(\tau) = 6\tau^5 - 15\tau^4 + 10\tau^3$ where $w'(0)=0, w''(0)=0$) modeling arm muscle recruitment latency (~30–40 ms) from zero initial acceleration.
  - *Global Proportional Bell Rescaling*: Distance-adaptive peak velocity ceiling ($V_{\text{target\_max}}(D) = \operatorname{clip}(V_{\text{base}} + \alpha \sqrt{D}, 1600.0, 2300.0)$) with uniform scalar scaling ($s = V_{\text{target\_max}} / v_{\text{peak}}$), preserving 100% of the neural model's continuous bell-curve convexity without artificial flatline velocity plateaus or zero-acceleration deadzones.
  - *Waypoint Relaunch Acceleration Symmetry*: Smoothstep transition envelope across $K_{\text{trans}} = 10\text{--}14$ steps (~40–60 ms) matching the physiological rise base of initial onset and bounding transition peaks $\le 14,000\text{ px/s}^2$.
  - *Acceleration Decay Relaxation*: Hann cosine decay window ($K_{\text{relax}} = 7$ steps) across drive-to-deceleration inflection ensuring unbroken $C^1$ continuity and finite jerk ($\frac{da}{dt}$).
- **Fitts's Law Dynamic Step Allocation**: Distance-adaptive budgeting ($N_{\text{steps}} = \text{int}(N_{\text{base}} + k \cdot \log_2(1 + \text{dist} / W_{\text{ref}}))$) allowing short reaches (200–300 px) to complete naturally in ~250–350 ms and long reaches (800–1200 px) in ~550–750 ms.
- **Natural Landing Phase & Box Dispersion**: Decouples artificial 0.00 px robotic snapping, allowing authentic human terminal dispersion ($\sigma \approx 0.8\text{–}1.6\text{ px}$, average error ~1.5–2.5 px). Includes `sample_target_within_box(box_bounds)` for UI target selection via truncated 2D Gaussian ($\sigma = w/6, \sigma = h/6$).
- **Continuous 8–12 Hz Neuromuscular Tremor**: Ornstein-Uhlenbeck (OU) physiological micro-tremor process with ballistic speed suppression.
- **Sub-Millisecond Execution Precision**: Windows 1ms multimedia timer (`timeBeginPeriod`) with hybrid sleep-spinwait pacing.

---

## Quick Start & Testing

### 1. Interactive Demo & Statistical Benchmark

Run the demo suite directly from the repository root:

```bash
# Dry-run benchmark across varied screen distances (Momentum Chaining)
python examples/demo_test.py --mode dry-run --model models/production_mouse_model.pth

# Generate & export multi-segment kinematic chained analysis (docs/trajectory_demo.png)
python examples/demo_test.py --mode plot --model models/production_mouse_model.pth

# Live cursor test across 4 screen waypoints with dynamic curvature
python examples/demo_test.py --mode live

# Side-by-side comparative visualization (docs/human_vs_bot_comparison.png)
python examples/compare_human_vs_bot.py

# Offline lightweight simulation
python examples/simulate_mouse.py
```

### 2. Standalone CLI Controller

Execute natural cursor movements directly via `human_mouse_engine`:

```bash
# Move to screen coordinate (800, 500) and click
python human_mouse_engine/execute_mouse_action.py --x 800 --y 500 --click

# Dry-run simulation mode (does not move physical mouse)
python human_mouse_engine/execute_mouse_action.py --dry-run --x 500 --y 300

# Continuous multi-target sequence
python human_mouse_engine/execute_mouse_action.py --sequence "400,300;1200,200;900,600"
```

---

## Python Programmatic API Usage

Import `HumanMouse` from the `human_mouse_engine` package into any automation script:

```python
from human_mouse_engine import HumanMouse

# Initialize engine (automatically discovers models/production_mouse_model.pth)
mouse = HumanMouse()

# Move cursor naturally to (800, 400)
mouse.move_to(target_x=800, target_y=400)

# Move and click
mouse.click_at(target_x=1200, target_y=600, button='left')

# Continuous sequence with automatic momentum chaining
targets = [(400, 300), (900, 500), (600, 800)]
mouse.move_sequence(targets, click_targets=False, delay_between=0.3)
```

---

## Model Training & Data Engineering

### 1. Preprocessing Raw Telemetry Databases
Convert raw SQLite telemetry into unified PyTorch tensors:
```bash
python pipeline/data_prep/preprocess_all_sqlite.py --data_dir data --output data/mouse_dataset_fixed_N256_full.npz
```

### 2. Production Training with Kinematic Memory (Full Dataset)
Train across all 53,028 human episodes with Automatic Mixed Precision (`torch.amp` FP16) and direct in-memory indexing:
```bash
python pipeline/training/train_pilot.py --full --epochs 10 --batch_size 128 --num_workers 0 --save_path models/production_mouse_model.pth
```

### 3. Pilot Training (Local Subset)
```bash
python pipeline/training/train_pilot.py --data data/mouse_dataset_fixed_N256_full.npz --subset 6000 --epochs 6 --batch_size 64 --save_path models/pilot_mouse_model.pth
```
