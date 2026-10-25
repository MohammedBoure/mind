import numpy as np
import matplotlib.pyplot as plt
import os
import sys

# Ensure UTF-8 printing
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
    from human_mouse_engine import HumanMouse
except ImportError:
    from human_mouse import HumanMouse

def generate_comparison_plots():
    mouse = HumanMouse()
    start_pos = (200, 200)
    target_pos = (1400, 800)

    # 1. AI Human Trajectory
    ai_traj = mouse.generate_trajectory(start_pos, target_pos)
    ai_x = [p['x'] for p in ai_traj]
    ai_y = [p['y'] for p in ai_traj]
    ai_dts = [p['dt_ms'] for p in ai_traj]

    # Calculate AI speed (px / ms)
    ai_speeds = []
    for i in range(1, len(ai_traj)):
        dist = np.hypot(ai_x[i] - ai_x[i-1], ai_y[i] - ai_y[i-1])
        dt = max(1.0, ai_dts[i])
        ai_speeds.append(dist / dt)

    # 2. Robotic Linear Trajectory (Standard Bot)
    steps = len(ai_traj)
    bot_x = np.linspace(start_pos[0], target_pos[0], steps)
    bot_y = np.linspace(start_pos[1], target_pos[1], steps)
    bot_dist_per_step = np.hypot(target_pos[0] - start_pos[0], target_pos[1] - start_pos[1]) / steps
    bot_speeds = [bot_dist_per_step / 10.0] * (steps - 1)

    # Plotting Side-by-Side Comparison
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Plot 1: Trajectory Paths (2D Space)
    ax1.plot(bot_x, bot_y, 'r--', label='Robotic Bot Path (Straight Line)', linewidth=2)
    ax1.plot(ai_x, ai_y, 'b-', label='AI Human Path (Natural Curve & Micro-variations)', linewidth=2.5)
    ax1.scatter([start_pos[0]], [start_pos[1]], color='green', s=100, zorder=5, label='Start Point')
    ax1.scatter([target_pos[0]], [target_pos[1]], color='red', s=100, zorder=5, label='Target Point')
    ax1.set_title("2D Trajectory Comparison (Spatial Path)", fontsize=14, fontweight='bold')
    ax1.set_xlabel("Screen X (pixels)")
    ax1.set_ylabel("Screen Y (pixels)")
    ax1.set_xlim(0, 1920)
    ax1.set_ylim(0, 1080)
    ax1.invert_yaxis() # Invert Y for screen coordinates
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend(loc='lower left')

    # Plot 2: Velocity Profiles (Speed over Time)
    ax2.plot(bot_speeds, 'r--', label='Robotic Bot Speed (Constant / Artificial)', linewidth=2)
    ax2.plot(ai_speeds, 'b-', label='AI Human Speed (Bell Curve / Acceleration & Deceleration)', linewidth=2.5)
    ax2.set_title("Speed Profile Comparison (Velocity over Steps)", fontsize=14, fontweight='bold')
    ax2.set_xlabel("Movement Step")
    ax2.set_ylabel("Speed (pixels / ms)")
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend(loc='upper right')

    output_path = os.path.join(REPO_ROOT, "docs", "human_vs_bot_comparison.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    print(f"✅ Comparison plot saved successfully to:\n   {output_path}")

if __name__ == '__main__':
    generate_comparison_plots()
