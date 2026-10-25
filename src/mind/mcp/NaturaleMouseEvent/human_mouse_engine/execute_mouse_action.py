import argparse
import sys
import time
import numpy as np
try:
    from human_mouse import HumanMouse, PYAUTOGUI_AVAILABLE
except ImportError:
    from human_mouse_engine.human_mouse import HumanMouse, PYAUTOGUI_AVAILABLE

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DEFAULT_DEMO_TARGETS = [
    (400, 300),
    (1200, 200),
    (1500, 700),
    (900, 900),
    (300, 800),
    (600, 400),
    (1400, 400),
    (1000, 600),
    (500, 200),
    (800, 500)
]

def parse_sequence_string(seq_str):
    """Parses sequence string like '400,300;1200,200' into list of tuple coordinates [(400, 300), (1200, 200)]."""
    targets = []
    pairs = seq_str.strip().split(';')
    for pair in pairs:
        if not pair.strip():
            continue
        parts = pair.split(',')
        if len(parts) == 2:
            targets.append((int(parts[0].strip()), int(parts[1].strip())))
    return targets

def main():
    parser = argparse.ArgumentParser(description="AI Natural Human Mouse Action Executor")
    parser.add_argument("--model", type=str, default=None, help="Path to PyTorch model checkpoint")
    parser.add_argument("--x", type=int, help="Target X coordinate")
    parser.add_argument("--y", type=int, help="Target Y coordinate")
    parser.add_argument("--click", action="store_true", help="Perform click after moving to target")
    parser.add_argument("--sequence", type=str, help="Sequence of targets separated by semicolon: '400,300;1200,200'")
    parser.add_argument("--demo", action="store_true", help="Run full 10-target AI trajectory demo")
    parser.add_argument("--wander", action="store_true", help="Demonstrate natural idle wandering behavior")
    parser.add_argument("--wander_radius", type=int, default=200, help="Radius for wandering movement")
    parser.add_argument("--delay", type=float, default=0.4, help="Delay between sequence targets in seconds")
    parser.add_argument("--no-failsafe", action="store_true", help="Disable PyAutoGUI failsafe mechanism")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run simulation mode (do not move real mouse)")
    
    args = parser.parse_args()

    # Initialize HumanMouse engine
    failsafe = not args.no_failsafe
    mouse = HumanMouse(model_path=args.model, failsafe=failsafe, dry_run=args.dry_run)

    print(f"\n=======================================================")
    print(f" 🤖 AI HUMAN MOUSE ACTION EXECUTOR")
    print(f" Display Resolution: {mouse.screen_w}x{mouse.screen_h}")
    current_pos = mouse.get_current_position()
    print(f" Starting Mouse Position: {current_pos}")
    if args.dry_run:
        print(f" Mode: DRY-RUN (Simulation only, cursor will not move)")
    print(f"=======================================================\n")

    if args.sequence:
        targets = parse_sequence_string(args.sequence)
        if not targets:
            print("Error: Invalid sequence format. Use format: --sequence '400,300;1200,200'")
            sys.exit(1)
        print(f"Executing sequence of {len(targets)} targets...")
        mouse.move_sequence(targets, click_targets=args.click, delay_between=args.delay)
        print(f"\n ✅ Successfully executed sequence of {len(targets)} targets!")

    elif args.wander:
        count = 5
        print(f"Executing sequence of {count} natural wandering movements (Radius={args.wander_radius})...")
        for i in range(1, count + 1):
            print(f"[Wander {i}/{count}] Simulating reading/idle hesitation...")
            traj = mouse.wander(radius=args.wander_radius, delay_after=args.delay)
            print(f" ➔ Generated {len(traj)} idle trajectory steps.")
        print(f"\n ✅ Completed {count} natural wandering actions successfully!")

    elif args.x is not None and args.y is not None:
        target = (args.x, args.y)
        print(f"Moving to target {target} (Click={args.click})...")
        traj = mouse.move_to(args.x, args.y, click=args.click, delay_after=args.delay)
        final_pos = (traj[-1]['x'], traj[-1]['y'])
        dist_err = np.hypot(final_pos[0] - args.x, final_pos[1] - args.y)
        print(f" ➔ Completed action in {len(traj)} steps (Final position: {final_pos}, Reach Error: {dist_err:.2f} px)")
        print(f" ✅ Target reached successfully!")

    else:
        # Full realistic human browsing session: Wander -> Move -> Click -> Wander
        print(f"Running realistic human session simulation (Wandering + Targeted Clicks)...")
        for i, target in enumerate(DEFAULT_DEMO_TARGETS[:5], 1):
            print(f"\n--- [Step {i}/5] ---")
            print("1. Idle reading / Wandering around current location...")
            mouse.wander(radius=150, delay_after=0.2)
            
            start = mouse.get_current_position()
            print(f"2. Decisive movement to target {target} and clicking...")
            traj = mouse.move_to(target[0], target[1], click=args.click, delay_after=args.delay)
            print(f" ➔ Completed action in {len(traj)} steps.")

        print("\n=======================================================")
        print(f" ✅ REALISTIC HUMAN SESSION SIMULATION COMPLETED SUCCESSFULLY! ")
        print("=======================================================\n")

if __name__ == '__main__':
    main()
