"""
Interactive Demonstration and Testing Suite for NaturaleMouseEvent.
Author: Senior AI Kinematics & Robotics Engineer
Project: NaturaleMouseEvent
"""

import os
import sys
import time
import math
import argparse
from typing import List, Tuple, Dict, Any, Optional

import numpy as np

# Enable UTF-8 encoding on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
ENGINE_DIR = os.path.join(REPO_ROOT, "human_mouse_engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

try:
    from human_mouse_engine import HumanMouse, PYAUTOGUI_AVAILABLE
except ImportError:
    from human_mouse import HumanMouse, PYAUTOGUI_AVAILABLE

try:
    import matplotlib
    matplotlib.use('Agg')  # Headless rendering compatible with all environments
    import matplotlib.pyplot as plt
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


def print_banner():
    print("""
========================================================================
   🖱️  NATURALE MOUSE EVENT: AI INTERACTIVE DEMO & TESTING SUITE
   Biologically Authentic Human Cursor Kinematics & Neural Simulation
========================================================================
""")


def resolve_model_path(cli_model: Optional[str] = None) -> Optional[str]:
    """Resolves model checkpoint path with priority for production_mouse_model.pth or pilot_mouse_model.pth."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))

    if cli_model:
        candidates = [
            cli_model,
            os.path.join(repo_root, cli_model),
            os.path.join(script_dir, cli_model)
        ]
        for c in candidates:
            if os.path.exists(c):
                return os.path.abspath(c)
        print(f"[Model Config] Warning: Specified checkpoint '{cli_model}' not found.")

    # Check for models in priority order
    candidates = [
        os.path.join(repo_root, "models", "production_mouse_model.pth"),
        "models/production_mouse_model.pth",
        os.path.join(repo_root, "models", "pilot_mouse_model.pth"),
        "models/pilot_mouse_model.pth",
        os.path.join(repo_root, "models", "best_model.pth"),
        "models/best_model.pth",
        os.path.join(repo_root, "models", "human_mouse_model.pt"),
        os.path.join(repo_root, "human_mouse_engine", "human_mouse_model.pt"),
        "models/human_mouse_model.pt",
        "human_mouse_model.pt"
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)

    return None


def run_countdown(seconds: int = 3, message: str = "Starting in"):
    """Displays a non-intrusive countdown to allow the user to release their mouse."""
    print(f"\n[Notice] {message}:", end=" ", flush=True)
    for i in range(seconds, 0, -1):
        print(f"{i}...", end=" ", flush=True)
        time.sleep(1.0)
    print("GO!\n")


def run_dry_run_benchmark(mouse: HumanMouse, num_trials: int = 5):
    """
    Executes simulated trajectories with Kinematic Momentum Chaining
    without physical cursor movement, computing statistical accuracy,
    duration, and reach errors.
    """
    print(f"\n--- [1] DRY-RUN BENCHMARK ({num_trials} Trials with Momentum Chaining) ---")
    print(f"Active Checkpoint: {mouse.simulator.model.context_dim}D Extended Kinematic Memory Context")
    print("Testing neural trajectory generator across varied screen distances...")

    sw, sh = mouse.screen_w, mouse.screen_h
    reach_errors = []
    durations = []
    step_counts = []

    print(f"{'Trial':<7} | {'Start Pos':<14} | {'Target Pos':<14} | {'Distance':<10} | {'Steps':<7} | {'Duration':<10} | {'Inflow Mom':<11} | {'Reach Err':<10}")
    print("-" * 96)

    prev_ctx = None
    curr_pos = (float(sw * 0.5), float(sh * 0.5))

    for i in range(1, num_trials + 1):
        s_x, s_y = curr_pos
        t_x = float(np.random.randint(int(sw * 0.1), int(sw * 0.9)))
        t_y = float(np.random.randint(int(sh * 0.1), int(sh * 0.9)))
        nominal_dist = float(np.hypot(t_x - s_x, t_y - s_y))

        traj = mouse.generate_trajectory(
            start_pos=(s_x, s_y),
            target_pos=(t_x, t_y),
            prev_context=prev_ctx,
            intent=1.0,
            target_radius=5.0
        )

        final_pt = traj[-1]
        err = float(np.hypot(final_pt['x'] - t_x, final_pt['y'] - t_y))
        total_time = float(sum(pt['dt_ms'] for pt in traj))
        in_mom = float(np.hypot(prev_ctx[0], prev_ctx[1])) if prev_ctx else 0.0

        reach_errors.append(err)
        durations.append(total_time)
        step_counts.append(len(traj))

        print(f"#{i:<6} | ({int(s_x):>4}, {int(s_y):>4}) | ({int(t_x):>4}, {int(t_y):>4}) | {nominal_dist:>6.1f} px | {len(traj):<7} | {total_time:>6.1f} ms | {in_mom:>7.3f}   | {err:>5.2f} px")

        # Carry arrival velocity directly into the next trial
        prev_ctx = mouse.compute_terminal_momentum(traj, dwell_time_sec=0.08)
        curr_pos = (float(final_pt['x']), float(final_pt['y']))

    mean_err = np.mean(reach_errors)
    mean_dur = np.mean(durations)
    mean_steps = np.mean(step_counts)

    print("-" * 96)
    print(f"📊 SUMMARY: Avg Reach Error: {mean_err:.2f} px | Avg Duration: {mean_dur:.1f} ms | Avg Steps: {mean_steps:.1f}")
    print("✅ Benchmark with Kinematic Chaining completed successfully!\n")


def run_live_cursor_demo(mouse: HumanMouse):
    """
    Executes live cursor movement across screen waypoints using
    Continuous Kinematic Momentum Chaining to produce biological curved arcs
    rather than sharp geometric corners.
    """
    print("\n--- [2] LIVE ON-SCREEN CURSOR DEMO (Kinematic Momentum Chaining) ---")
    print("This mode physically navigates waypoints, carrying dynamic residual momentum across turns.")
    print("Notice how the cursor traces continuous, biological curved arcs instead of sharp geometric corners.")
    print("Safety Reminder: Move your mouse to (0, 0) top-left at any time to abort.")

    run_countdown(seconds=3, message="Cursor control will begin in")

    sw, sh = mouse.screen_w, mouse.screen_h
    waypoints = [
        ("Screen Center", (int(sw * 0.5), int(sh * 0.5))),
        ("Top-Right Box", (int(sw * 0.8), int(sh * 0.25))),
        ("Bottom-Right Box", (int(sw * 0.75), int(sh * 0.75))),
        ("Bottom-Left Box", (int(sw * 0.25), int(sh * 0.75))),
        ("Center Rest", (int(sw * 0.5), int(sh * 0.5))),
    ]

    prev_context = None

    for i, (label, target) in enumerate(waypoints):
        curr = mouse.get_current_position()
        dist = np.hypot(target[0] - curr[0], target[1] - curr[1])
        is_last = (i == len(waypoints) - 1)
        dwell_sec = 0.20 if is_last else 0.04

        if prev_context is not None and len(prev_context) >= 2:
            vx_in, vy_in = prev_context[0], prev_context[1]
            mag = float(np.hypot(vx_in, vy_in))
            print(f" ➔ Navigating to {label} at {target} (Dist: {dist:.1f} px | Inflow Momentum: {mag:.2f} [vx={vx_in:+.2f}, vy={vy_in:+.2f}])...")
        else:
            print(f" ➔ Navigating to {label} at {target} (Dist: {dist:.1f} px | Initial Launch)...")

        start_t = time.perf_counter()
        traj = mouse.move_to(
            target[0],
            target[1],
            prev_context=prev_context,
            dwell_time=dwell_sec,
            delay_after=0.05 if not is_last else 0.3
        )
        elapsed = (time.perf_counter() - start_t) * 1000.0
        final_pos = mouse.get_current_position()
        err = float(np.hypot(final_pos[0] - target[0], final_pos[1] - target[1]))

        # Calculate arrival velocity vector for continuous chaining into subsequent target
        prev_context = mouse.compute_terminal_momentum(traj, dwell_time_sec=dwell_sec)
        print(f"   ✓ Arrived at {final_pos} | Elapsed: {elapsed:.1f} ms | Error: {err:.1f} px")

    print("\n✅ Kinematic momentum chaining demo completed successfully!\n")


def run_precision_click_demo(mouse: HumanMouse):
    """
    Demonstrates moving towards a target and executing a natural click
    with biological deceleration and submovement fine-tuning.
    """
    print("\n--- [3] PRECISION TARGET CLICK DEMO ---")
    print("The cursor will move toward a designated target and perform an authentic human click.")

    run_countdown(seconds=3, message="Starting in")

    sw, sh = mouse.screen_w, mouse.screen_h
    # Simulate an interactive UI button bounding box (x, y, w, h)
    btn_box = (int(sw * 0.55), int(sh * 0.38), 160, 46)
    sampled_target = mouse.sample_target_within_box(btn_box)

    print(f" ➔ Target UI Element Bounding Box: {btn_box} (Center: ({btn_box[0] + btn_box[2]/2:.0f}, {btn_box[1] + btn_box[3]/2:.0f}))")
    print(f" ➔ Biometric Dispersion Sampling: Intent Point ({sampled_target[0]:.1f}, {sampled_target[1]:.1f})...")
    mouse.click_at(sampled_target[0], sampled_target[1])
    final_pos = mouse.get_current_position()
    err = float(np.hypot(final_pos[0] - sampled_target[0], final_pos[1] - sampled_target[1]))
    print(f"   ✓ Click executed at {final_pos} | Reach error relative to sampled target: {err:.1f} px\n")


def run_idle_wandering_demo(mouse: HumanMouse):
    """
    Demonstrates human-like idle wandering and micro-tremor around the current position.
    """
    print("\n--- [4] IDLE WANDERING & MICRO-TREMOR DEMO ---")
    print("Demonstrating biological hesitation and natural cursor wandering behavior...")

    run_countdown(seconds=2, message="Wandering starts in")

    curr = mouse.get_current_position()
    print(f" ➔ Wandering around current location {curr} for 3 sub-movements...")
    for step in range(3):
        mouse.wander(radius=120)
        time.sleep(0.2)

    print("✅ Idle wandering completed!\n")


def run_trajectory_plot_demo(mouse: HumanMouse, output_file: str = "docs/trajectory_demo.png"):
    """
    Generates a multi-segment Kinematic Momentum Chaining visualization plot:
    1. 2D Spatial Route: Segment 1 (A -> B) chained into Segment 2 (B -> C)
       showing how incoming velocity bends the trajectory into a natural arc.
    2. Bell-Shaped Velocity Profile across the chained sequence.
    3. Acceleration & Easing Dynamics showing the smooth transition through waypoint B.
    """
    print(f"\n--- [5] KINEMATIC MOMENTUM CHAINING PLOTTER ---")
    if not MATPLOTLIB_AVAILABLE:
        print("[Warning] 'matplotlib' is not installed. Skipping plot generation.")
        return

    sw, sh = mouse.screen_w, mouse.screen_h
    pt_a = (float(sw * 0.15), float(sh * 0.20))
    pt_b = (float(sw * 0.75), float(sh * 0.35))
    pt_c = (float(sw * 0.40), float(sh * 0.80))

    print(f"Generating chained trajectory route: Point A {pt_a} -> Point B {pt_b} -> Point C {pt_c}...")

    # Segment 1: A -> B from resting position
    traj1 = mouse.generate_trajectory(pt_a, pt_b, prev_context=None, intent=1.0)
    arr_momentum = mouse.compute_terminal_momentum(traj1, dwell_time_sec=0.04)

    # Cleanly drop any trailing duplicate stationary resting steps from traj1 at in-flight junction
    traj1_chain = traj1
    while len(traj1_chain) > 2 and np.hypot(traj1_chain[-1]['x'] - traj1_chain[-2]['x'], traj1_chain[-1]['y'] - traj1_chain[-2]['y']) < 0.2:
        traj1_chain = traj1_chain[:-1]

    # Segment 2: B -> C initialized with the arrival momentum from Segment 1
    actual_b = (float(traj1_chain[-1]['x']), float(traj1_chain[-1]['y']))
    traj2 = mouse.generate_trajectory(actual_b, pt_c, prev_context=arr_momentum, intent=1.0)

    # Combine trajectories and apply global biomechanical safety filter across concatenated multi-segment path
    combined_raw = traj1_chain + traj2[1:]
    split_idx = len(traj1_chain) - 1
    combined_traj = mouse.apply_biomechanical_kinematic_filter(
        combined_raw, max_acceleration=15000.0, min_dt_ms=7.0, split_idx=split_idx
    )

    xs = np.array([pt['x'] for pt in combined_traj], dtype=np.float64)
    ys = np.array([pt['y'] for pt in combined_traj], dtype=np.float64)
    dts = np.array([pt['dt_ms'] for pt in combined_traj], dtype=np.float64)
    timestamps = np.cumsum(dts)

    # Compute continuous kinematics
    dx = np.diff(xs)
    dy = np.diff(ys)
    step_dists = np.hypot(dx, dy)
    dt_mid = dts[1:]
    velocities_px_per_s = np.zeros_like(step_dists)
    valid_dt = dt_mid > 1e-3
    velocities_px_per_s[valid_dt] = (step_dists[valid_dt] / (dt_mid[valid_dt] / 1000.0))

    accelerations = np.zeros_like(velocities_px_per_s)
    if len(velocities_px_per_s) > 1:
        dv = np.diff(velocities_px_per_s)
        dt_acc = 0.5 * (dt_mid[:-1] + dt_mid[1:])
        valid_acc = dt_acc > 1e-3
        accelerations[1:][valid_acc] = dv[valid_acc] / (dt_acc[valid_acc] / 1000.0)

    # Plot figure with 3 subplots
    fig, axes = plt.subplots(1, 3, figsize=(19, 5.5), facecolor='#1e1e1e')

    # Subplot 1: 2D Spatial Route with Chained Curvature
    ax1 = axes[0]
    ax1.set_facecolor('#121212')
    scatter = ax1.scatter(xs[:-1], ys[:-1], c=velocities_px_per_s, cmap='plasma', s=14, alpha=0.85)

    # Draw rigid geometric lines for comparison
    ax1.plot([pt_a[0], pt_b[0], pt_c[0]], [pt_a[1], pt_b[1], pt_c[1]], 'w--', alpha=0.3, label='Polygonal Path (Zero Momentum)')
    ax1.plot(xs, ys, color='#58a6ff', linewidth=1.5, alpha=0.7, label='Kinematic Chained Arc')

    ax1.plot(pt_a[0], pt_a[1], 'go', markersize=9, label='Start Point A')
    ax1.plot(pt_b[0], pt_b[1], 'y^', markersize=10, label='Waypoint B (Momentum Turn)')
    ax1.plot(pt_c[0], pt_c[1], 'r*', markersize=13, label='Destination C')
    ax1.plot(xs[-1], ys[-1], 'mo', markersize=8, fillstyle='none', markeredgewidth=2, label='Final Landing')

    ax1.set_title("2D Route: Kinematic Momentum Chaining (A→B→C)", color='white', fontsize=11, fontweight='bold')
    ax1.set_xlabel("Screen X (px)", color='#c9d1d9')
    ax1.set_ylabel("Screen Y (px)", color='#c9d1d9')
    ax1.tick_params(colors='#8b949e')
    ax1.invert_yaxis()
    ax1.grid(True, color='#30363d', linestyle=':', alpha=0.6)
    cbar = plt.colorbar(scatter, ax=ax1, fraction=0.046, pad=0.04)
    cbar.set_label('Velocity (px/s)', color='#c9d1d9')
    cbar.ax.yaxis.set_tick_params(color='#8b949e')
    plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color='#8b949e')
    ax1.legend(loc='lower left', facecolor='#21262d', edgecolor='#30363d', labelcolor='white', fontsize=8.5)

    # Subplot 2: Continuous Velocity Profile
    split_time = timestamps[len(traj1_chain) - 1]
    ax2 = axes[1]
    ax2.set_facecolor('#121212')
    ax2.plot(timestamps[1:], velocities_px_per_s, color='#3fb950', linewidth=1.8)
    ax2.axvline(split_time, color='#e3b341', linestyle='--', alpha=0.7, label=f'Waypoint B Arrival ({split_time:.0f} ms)')
    ax2.fill_between(timestamps[1:], velocities_px_per_s, color='#238636', alpha=0.25)
    ax2.set_title("Continuous Velocity Profile v(t)", color='white', fontsize=11, fontweight='bold')
    ax2.set_xlabel("Time (ms)", color='#c9d1d9')
    ax2.set_ylabel("Velocity (px/s)", color='#c9d1d9')
    ax2.tick_params(colors='#8b949e')
    ax2.grid(True, color='#30363d', linestyle=':', alpha=0.6)
    ax2.legend(loc='upper right', facecolor='#21262d', edgecolor='#30363d', labelcolor='white', fontsize=8.5)

    # Subplot 3: Acceleration & Deceleration Dynamics
    ax3 = axes[2]
    ax3.set_facecolor('#121212')
    ax3.plot(timestamps[1:], accelerations, color='#f78166', linewidth=1.4)
    ax3.axvline(split_time, color='#e3b341', linestyle='--', alpha=0.7, label='Waypoint B')
    ax3.axhline(0, color='#8b949e', linestyle='--', alpha=0.4)
    ax3.set_title("Acceleration & Deceleration (Smooth Transitions)", color='white', fontsize=11, fontweight='bold')
    ax3.set_xlabel("Time (ms)", color='#c9d1d9')
    ax3.set_ylabel("Acceleration (px/s²)", color='#c9d1d9')
    ax3.tick_params(colors='#8b949e')
    ax3.grid(True, color='#30363d', linestyle=':', alpha=0.6)
    ax3.legend(loc='upper right', facecolor='#21262d', edgecolor='#30363d', labelcolor='white', fontsize=8.5)

    out_dir = os.path.dirname(os.path.abspath(output_file))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_file, dpi=180, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

    print(f"📊 Visualization successfully exported to: {os.path.abspath(output_file)}")
    print(f"   • Route total duration: {timestamps[-1]:.1f} ms")
    print(f"   • Transition momentum at Waypoint B: {np.hypot(arr_momentum[0], arr_momentum[1]):.3f}")
    print(f"   • Destination reach error: {np.hypot(xs[-1] - pt_c[0], ys[-1] - pt_c[1]):.2f} px\n")


def interactive_menu(model_path: Optional[str] = None):
    """Renders interactive CLI selection menu."""
    print_banner()

    mouse = HumanMouse(model_path=model_path)
    print(f"Display Dimensions: {mouse.screen_w}x{mouse.screen_h} px")
    print(f"Current Cursor Position: {mouse.get_current_position()}")

    while True:
        print("""
Select a demonstration mode:
 [1] Dry-Run Accuracy Benchmark (Simulation Only with Momentum Chaining)
 [2] Live On-Screen Cursor Test (Kinematic Momentum Chaining Across Waypoints)
 [3] Precision Target Click Test (Moves & Clicks a Single Target)
 [4] Idle Wandering & Physiological Tremor Test
 [5] Kinematic Trajectory Plotter (Exports trajectory_demo.png analysis graph)
 [6] Run All Tests Sequentially
 [0] Exit
""")
        choice = input("Enter option [0-6]: ").strip()

        if choice == '1':
            run_dry_run_benchmark(mouse)
        elif choice == '2':
            run_live_cursor_demo(mouse)
        elif choice == '3':
            run_precision_click_demo(mouse)
        elif choice == '4':
            run_idle_wandering_demo(mouse)
        elif choice == '5':
            run_trajectory_plot_demo(mouse)
        elif choice == '6':
            run_dry_run_benchmark(mouse)
            run_trajectory_plot_demo(mouse)
            run_live_cursor_demo(mouse)
            run_precision_click_demo(mouse)
            run_idle_wandering_demo(mouse)
        elif choice == '0':
            print("Exiting demo suite. Happy scripting!")
            break
        else:
            print("Invalid selection. Please choose an option from 0 to 6.")


def main():
    parser = argparse.ArgumentParser(description="NaturaleMouseEvent Interactive Demo Suite")
    parser.add_argument("--model", type=str, default=None,
                        help="Path to PyTorch model checkpoint (default: models/pilot_mouse_model.pth)")
    parser.add_argument("--mode", type=str, choices=["dry-run", "live", "click", "wander", "plot", "all"],
                        help="Direct execution mode without interactive prompt")
    parser.add_argument("--trials", type=int, default=5, help="Number of trials for benchmark")
    parser.add_argument("--plot-out", type=str, default="docs/trajectory_demo.png", help="Output path for plot")

    args = parser.parse_args()

    model_path = resolve_model_path(args.model)

    if args.mode:
        print_banner()
        mouse = HumanMouse(model_path=model_path)
        if args.mode == "dry-run":
            run_dry_run_benchmark(mouse, num_trials=args.trials)
        elif args.mode == "live":
            run_live_cursor_demo(mouse)
        elif args.mode == "click":
            run_precision_click_demo(mouse)
        elif args.mode == "wander":
            run_idle_wandering_demo(mouse)
        elif args.mode == "plot":
            run_trajectory_plot_demo(mouse, output_file=args.plot_out)
        elif args.mode == "all":
            run_dry_run_benchmark(mouse, num_trials=args.trials)
            run_trajectory_plot_demo(mouse, output_file=args.plot_out)
            run_live_cursor_demo(mouse)
            run_precision_click_demo(mouse)
            run_idle_wandering_demo(mouse)
    else:
        interactive_menu(model_path=model_path)


if __name__ == '__main__':
    main()
