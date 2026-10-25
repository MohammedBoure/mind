import os
import sys
import numpy as np
import torch
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
ENGINE_DIR = os.path.join(REPO_ROOT, "human_mouse_engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

try:
    from human_mouse_engine import HumanMouseSimulator
except ImportError:
    from human_mouse import HumanMouseSimulator

if __name__ == '__main__':
    print("\n--- AI Natural Mouse Trajectory Simulation Test ---")
    sim = HumanMouseSimulator()
    start_pos = (100, 100)
    target_pos = (800, 500)
    print(f"Simulating movement: {start_pos} -> {target_pos}")
    traj = sim.generate_trajectory(start_pos, target_pos)

    print(f"\nGenerated AI Trajectory: {len(traj)} steps")
    print("First 3 steps:")
    for s in traj[:3]:
        print(f"  {s}")
    print("Last 3 steps:")
    for s in traj[-3:]:
        print(f"  {s}")

    total_time_ms = sum(s['dt_ms'] for s in traj)
    final_pos = (traj[-1]['x'], traj[-1]['y'])
    dist_error = np.hypot(final_pos[0] - target_pos[0], final_pos[1] - target_pos[1])
    print(f"\nSummary:")
    print(f"  Total Duration: {total_time_ms:.1f} ms")
    print(f"  Final Position: {final_pos} (Target: {target_pos})")
    print(f"  Final Distance to Target: {dist_error:.2f} px")
    print("---------------------------------------------------\n")
