"""
Preprocess All SQLite Telemetry Files into Production-Grade PyTorch Training Tensors.
Author: Principal Data Engineer & Deep Learning Researcher
Project: NaturaleMouseEvent
"""

import os
import sys
import glob
import json
import sqlite3
import argparse
import numpy as np
from tqdm import tqdm
import gc

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


def clean_episode_events(events, max_pause_sec=3.0):
    """
    Cleans an episode's event list:
    1. Enforces strict monotonic time order.
    2. Drops non-positive time deltas (duplicate/anomalous clock timestamps).
    3. Splits episode if a pause exceeds max_pause_sec (3.0s).

    Returns a list of contiguous sub-episode event lists.
    """
    if not events:
        return []

    # Sort strictly by t_monotonic_ns ascending
    events.sort(key=lambda ev: ev['t_monotonic_ns'])

    sub_episodes = []
    current_sub = [events[0]]

    for i in range(1, len(events)):
        prev_t = current_sub[-1]['t_monotonic_ns']
        curr_t = events[i]['t_monotonic_ns']
        dt_ns = curr_t - prev_t

        # Discard non-positive time anomaly
        if dt_ns <= 0:
            continue

        dt_sec = dt_ns / 1e9

        # If pause exceeds max_pause_sec, split into a new sub-episode
        if dt_sec > max_pause_sec:
            if len(current_sub) > 0:
                sub_episodes.append(current_sub)
            current_sub = [events[i]]
        else:
            current_sub.append(events[i])

    if len(current_sub) > 0:
        sub_episodes.append(current_sub)

    return sub_episodes


def evaluate_biomechanics(sub_events, min_steps=15, min_displacement=30.0, max_ortho_ratio=0.85):
    """
    Evaluates whether an episode passes strict biometric & functional cleaning:
    - Step count >= min_steps
    - Total spatial displacement >= min_displacement
    - Not an orthogonal/grid staircase artifact
    - Not a flat 1D line (std(x) >= 1.0 and std(y) >= 1.0)

    Returns: (passes_bool, rejection_reason, xs, ys)
    """
    if len(sub_events) < min_steps:
        return False, "<15 steps", None, None

    xs = np.array([ev['x'] for ev in sub_events], dtype=np.float32)
    ys = np.array([ev['y'] for ev in sub_events], dtype=np.float32)

    # Total Euclidean displacement from start to end
    disp = float(np.hypot(xs[-1] - xs[0], ys[-1] - ys[0]))
    if disp < min_displacement:
        return False, "<30px displacement", None, None

    # Check for flat 1D movements
    if np.std(xs) < 1.0 or np.std(ys) < 1.0:
        return False, "flat 1D line", None, None

    # Check for orthogonal grid staircases
    dx = np.diff(xs)
    dy = np.diff(ys)
    steps_count = len(dx)
    pure_ortho = np.sum((dx == 0) | (dy == 0))
    ortho_ratio = pure_ortho / steps_count if steps_count > 0 else 0.0

    if ortho_ratio > max_ortho_ratio:
        return False, "orthogonal grid artifact", None, None

    return True, "valid", xs, ys


def encode_action(event_type, pressed):
    """
    Action ID encoding:
    0: Normal move (event_type == 'move')
    1: Mouse button down (event_type == 'button' & pressed == 1)
    2: Mouse button up (event_type == 'button' & pressed == 0)
    3: Scroll action (event_type == 'scroll')
    """
    if event_type == 'move':
        return 0.0
    elif event_type == 'button':
        return 1.0 if pressed == 1 else 2.0
    elif event_type == 'scroll':
        return 3.0
    return 0.0


def build_episode_tensors(sub_events, width, height, max_len=256):
    """
    Converts a validated list of events into the fixed N=256 tensor representation.
    Chunks episodes longer than max_len into 256-step windows.
    """
    samples = []
    num_events = len(sub_events)

    # Chunking / windowing
    chunk_starts = range(0, num_events, max_len)
    for start_idx in chunk_starts:
        chunk = sub_events[start_idx : start_idx + max_len]
        K = len(chunk)
        if K < 15:
            continue

        # Start and target normalized coordinates
        start_x = float(chunk[0]['x']) / width
        start_y = float(chunk[0]['y']) / height
        target_x = float(chunk[-1]['x']) / width
        target_y = float(chunk[-1]['y']) / height

        # Verify displacement for this specific chunk
        chunk_disp_px = np.hypot(chunk[-1]['x'] - chunk[0]['x'], chunk[-1]['y'] - chunk[0]['y'])
        if chunk_disp_px < 20.0 and K < max_len:
            continue

        start_target = np.array([start_x, start_y, target_x, target_y], dtype=np.float32)

        seq_tensor = np.zeros((max_len, 6), dtype=np.float32)
        mask = np.zeros(max_len, dtype=np.float32)

        prev_t = chunk[0]['t_monotonic_ns']
        prev_x = float(chunk[0]['x'])
        prev_y = float(chunk[0]['y'])

        action_counts = 0

        for t, ev in enumerate(chunk):
            curr_x = float(ev['x']) / width
            curr_y = float(ev['y']) / height

            if t == 0:
                dx = 0.0
                dy = 0.0
                dt_scaled = 0.0
            else:
                dx = (float(ev['x']) - prev_x) / width
                dy = (float(ev['y']) - prev_y) / height
                dt_sec = (ev['t_monotonic_ns'] - prev_t) / 1e9
                dt_scaled = min(5.0, dt_sec * 10.0)  # dt_ms / 100.0

            rem_x = target_x - curr_x
            rem_y = target_y - curr_y

            act_code = encode_action(ev['event_type'], ev.get('pressed', None))
            if act_code in (1.0, 2.0):
                action_counts += 1

            seq_tensor[t] = [dx, dy, dt_scaled, rem_x, rem_y, act_code]
            mask[t] = 1.0

            prev_t = ev['t_monotonic_ns']
            prev_x = float(ev['x'])
            prev_y = float(ev['y'])

        # Compute 4D Behavioral Momentum Context
        # 1. Initial velocities over first min(5, K-1) steps
        m = min(5, K - 1)
        t_m_sec = (chunk[m]['t_monotonic_ns'] - chunk[0]['t_monotonic_ns']) / 1e9
        if t_m_sec > 0:
            vx0 = ((chunk[m]['x'] - chunk[0]['x']) / width) / t_m_sec
            vy0 = ((chunk[m]['y'] - chunk[0]['y']) / height) / t_m_sec
        else:
            vx0, vy0 = 0.0, 0.0

        # 2. Click density
        click_density = float(action_counts) / 256.0

        # 3. Hardware polling cadence (avg_dt scaled)
        total_dur_sec = (chunk[-1]['t_monotonic_ns'] - chunk[0]['t_monotonic_ns']) / 1e9
        avg_dt_sec = total_dur_sec / (K - 1) if K > 1 else 0.008
        avg_dt_scaled = avg_dt_sec * 10.0

        context_vec = np.array([vx0, vy0, click_density, avg_dt_scaled], dtype=np.float32)
        intent_val = np.array([1.0 if action_counts > 0 else 0.0], dtype=np.float32)

        samples.append({
            "seq_tensor": seq_tensor,
            "prev_context": context_vec,
            "start_target": start_target,
            "mask": mask,
            "intent": intent_val,
            "duration_sec": total_dur_sec,
            "valid_steps": K
        })

    return samples


def process_all_sqlite(
    data_dir="./data",
    output_npz="data/mouse_dataset_fixed_N256_full.npz",
    max_len=256,
    min_steps=15,
    min_displacement=30.0,
    max_ortho_ratio=0.85,
    max_pause_sec=3.0,
    max_files=None
):
    """
    Sequentially processes all SQLite telemetry files in data_dir, extracts valid
    human trajectory episodes, and saves the consolidated compressed dataset.
    """
    db_pattern = os.path.join(data_dir, "mouse_events_*.sqlite3")
    db_files = sorted(glob.glob(db_pattern))

    if not db_files:
        # Fallback to any sqlite3 file in data_dir
        db_files = sorted(glob.glob(os.path.join(data_dir, "*.sqlite3")))

    if not db_files:
        raise FileNotFoundError(f"No SQLite database files found in: {data_dir}")

    if max_files is not None:
        db_files = db_files[:max_files]

    print("==========================================================================")
    print(" 🚀 PRINCIPAL DATA ENGINEERING PIPELINE: NATURAL MOUSE DATASET EXTRACTION")
    print(f" Target Directory: {data_dir} ({len(db_files)} database files)")
    print(f" Output NPZ:       {output_npz}")
    print(f" Parameters:       Horizon={max_len}, MinSteps={min_steps}, MinDisp={min_displacement}px, OrthoThresh={max_ortho_ratio}")
    print("==========================================================================\n")

    retained_seq_tensors = []
    retained_prev_contexts = []
    retained_start_targets = []
    retained_masks = []
    retained_intents = []

    global_stats = {
        "total_files": len(db_files),
        "total_raw_events": 0,
        "total_raw_episodes": 0,
        "total_sub_episodes": 0,
        "rejections": {
            "<15 steps": 0,
            "<30px displacement": 0,
            "orthogonal grid artifact": 0,
            "flat 1D line": 0,
            "time anomalies": 0
        },
        "durations_sec": [],
        "steps_counts": [],
        "action_distribution": {0: 0, 1: 0, 2: 0, 3: 0}
    }

    # Iterate over all database files with memory cleanup per database
    for db_idx, db_path in enumerate(tqdm(db_files, desc="Databases Progress", unit="db"), 1):
        db_name = os.path.basename(db_path)
        file_retained_count = 0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Load session monitors resolution mapping
        session_monitors = {}
        try:
            for s_row in c.execute("SELECT session_id, monitors_json FROM sessions").fetchall():
                s_id = s_row['session_id']
                try:
                    mons = json.loads(s_row['monitors_json'])
                    w = float(mons[0]['width']) if mons else 1920.0
                    h = float(mons[0]['height']) if mons else 1080.0
                except Exception:
                    w, h = 1920.0, 1080.0
                session_monitors[s_id] = (w, h)
        except Exception:
            pass

        # Stream all events grouped by composite key (session_id, episode_index)
        query = """
        SELECT session_id, episode_index, t_monotonic_ns, event_type, x, y, button, pressed
        FROM events
        WHERE episode_index IS NOT NULL
        ORDER BY session_id, episode_index, t_monotonic_ns ASC
        """

        current_key = None
        current_events = []

        for row in c.execute(query):
            global_stats["total_raw_events"] += 1
            sess_id = row['session_id']
            ep_idx = row['episode_index']
            comp_key = (sess_id, ep_idx)

            if comp_key != current_key:
                if current_key is not None and len(current_events) > 0:
                    global_stats["total_raw_episodes"] += 1
                    s_id_prev = current_key[0]
                    W, H = session_monitors.get(s_id_prev, (1920.0, 1080.0))

                    # 1. Clean time anomalies & split pauses > 3s
                    sub_eps = clean_episode_events(current_events, max_pause_sec=max_pause_sec)
                    for sub in sub_eps:
                        global_stats["total_sub_episodes"] += 1
                        passes, reason, xs, ys = evaluate_biomechanics(
                            sub,
                            min_steps=min_steps,
                            min_displacement=min_displacement,
                            max_ortho_ratio=max_ortho_ratio
                        )
                        if not passes:
                            global_stats["rejections"][reason] = global_stats["rejections"].get(reason, 0) + 1
                            continue

                        # 2. Extract tensors
                        samples = build_episode_tensors(sub, width=W, height=H, max_len=max_len)
                        for s in samples:
                            retained_seq_tensors.append(s["seq_tensor"])
                            retained_prev_contexts.append(s["prev_context"])
                            retained_start_targets.append(s["start_target"])
                            retained_masks.append(s["mask"])
                            retained_intents.append(s["intent"])

                            global_stats["durations_sec"].append(s["duration_sec"])
                            global_stats["steps_counts"].append(s["valid_steps"])

                            # Tally action distribution
                            act_codes = s["seq_tensor"][:s["valid_steps"], 5].astype(int)
                            for ac in act_codes:
                                if ac in global_stats["action_distribution"]:
                                    global_stats["action_distribution"][ac] += 1

                            file_retained_count += 1

                current_key = comp_key
                current_events = []

            # Filter corrupted/null coordinates
            if row['x'] is not None and row['y'] is not None:
                current_events.append({
                    't_monotonic_ns': row['t_monotonic_ns'],
                    'event_type': row['event_type'],
                    'x': row['x'],
                    'y': row['y'],
                    'button': row['button'],
                    'pressed': row['pressed']
                })

        # Process final episode in database
        if current_key is not None and len(current_events) > 0:
            global_stats["total_raw_episodes"] += 1
            s_id_prev = current_key[0]
            W, H = session_monitors.get(s_id_prev, (1920.0, 1080.0))

            sub_eps = clean_episode_events(current_events, max_pause_sec=max_pause_sec)
            for sub in sub_eps:
                global_stats["total_sub_episodes"] += 1
                passes, reason, xs, ys = evaluate_biomechanics(
                    sub,
                    min_steps=min_steps,
                    min_displacement=min_displacement,
                    max_ortho_ratio=max_ortho_ratio
                )
                if not passes:
                    global_stats["rejections"][reason] = global_stats["rejections"].get(reason, 0) + 1
                    continue

                samples = build_episode_tensors(sub, width=W, height=H, max_len=max_len)
                for s in samples:
                    retained_seq_tensors.append(s["seq_tensor"])
                    retained_prev_contexts.append(s["prev_context"])
                    retained_start_targets.append(s["start_target"])
                    retained_masks.append(s["mask"])
                    retained_intents.append(s["intent"])

                    global_stats["durations_sec"].append(s["duration_sec"])
                    global_stats["steps_counts"].append(s["valid_steps"])

                    act_codes = s["seq_tensor"][:s["valid_steps"], 5].astype(int)
                    for ac in act_codes:
                        if ac in global_stats["action_distribution"]:
                            global_stats["action_distribution"][ac] += 1

                    file_retained_count += 1

        # Memory Cleanup after each file
        conn.close()
        del current_events
        gc.collect()

    total_retained = len(retained_seq_tensors)
    if total_retained == 0:
        raise ValueError("Pipeline Error: 0 episodes qualified after preprocessing!")

    print(f"\n[Stacking Arrays] Assembling contiguous memory buffers for {total_retained:,} episodes...")

    seq_tensors = np.stack(retained_seq_tensors, axis=0).astype(np.float32)
    prev_contexts = np.stack(retained_prev_contexts, axis=0).astype(np.float32)
    start_targets = np.stack(retained_start_targets, axis=0).astype(np.float32)
    masks = np.stack(retained_masks, axis=0).astype(np.float32)
    intents = np.stack(retained_intents, axis=0).astype(np.float32)

    # Free list references
    del retained_seq_tensors, retained_prev_contexts, retained_start_targets, retained_masks, retained_intents
    gc.collect()

    # Meta summary dictionary
    meta = {
        "dataset_name": "NaturaleMouseEvent Fixed N=256 Unified Telemetry Dataset",
        "total_files_processed": len(db_files),
        "total_raw_events": global_stats["total_raw_events"],
        "total_raw_episodes": global_stats["total_raw_episodes"],
        "total_retained_episodes": total_retained,
        "max_horizon_N": max_len,
        "rejection_breakdown": global_stats["rejections"],
        "mean_duration_sec": float(np.mean(global_stats["durations_sec"])),
        "median_duration_sec": float(np.median(global_stats["durations_sec"])),
        "mean_steps": float(np.mean(global_stats["steps_counts"])),
        "median_steps": float(np.median(global_stats["steps_counts"])),
        "action_distribution": {
            "move_0": global_stats["action_distribution"][0],
            "button_down_1": global_stats["action_distribution"][1],
            "button_up_2": global_stats["action_distribution"][2],
            "scroll_3": global_stats["action_distribution"][3]
        }
    }

    # Export compressed NPZ
    os.makedirs(os.path.dirname(os.path.abspath(output_npz)), exist_ok=True)
    print(f"[Compressing] Writing unified archive to: {output_npz} ...")

    np.savez_compressed(
        output_npz,
        seq_tensors=seq_tensors,
        prev_contexts=prev_contexts,
        start_targets=start_targets,
        masks=masks,
        meta=meta,
        # Canonical aliases ensuring full backward compatibility with train_model.py
        start_positions=start_targets[:, :2],
        target_positions=start_targets[:, 2:],
        previous_contexts=prev_contexts,
        intents=intents,
        padding_masks=masks
    )

    # Export metadata JSON
    meta_json_path = output_npz.replace(".npz", "_metadata.json")
    with open(meta_json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    npz_size_mb = os.path.getsize(output_npz) / (1024 * 1024)

    print("\n==========================================================================")
    print("      🎉 FULL DATASET PREPROCESSING COMPLETED SUCCESSFULLY                ")
    print("==========================================================================")
    print(f" Total Databases:           {len(db_files)}")
    print(f" Total Raw Telemetry Events: {global_stats['total_raw_events']:,}")
    print(f" Total Retained Episodes:    {total_retained:,}")
    print(f" Output Archive Size:        {npz_size_mb:.2f} MB")
    print(f" Output Archive Path:        {output_npz}")
    print(f" Metadata JSON Path:         {meta_json_path}")
    print("--------------------------------------------------------------------------")
    print(f" Rejection Breakdown:")
    for reason, count in global_stats["rejections"].items():
        print(f"   - {reason:25s}: {count:,}")
    print("--------------------------------------------------------------------------")
    print(f" Kinematic Summary:")
    print(f"   - Mean Episode Duration:   {meta['mean_duration_sec']:.2f} s (Median: {meta['median_duration_sec']:.2f} s)")
    print(f"   - Mean Episode Steps:      {meta['mean_steps']:.1f} steps (Median: {meta['median_steps']:.1f} steps)")
    print(f" Action Distribution:")
    tot_act = sum(global_stats["action_distribution"].values())
    for code, name in [(0, "Move"), (1, "Press"), (2, "Release"), (3, "Scroll")]:
        cnt = global_stats["action_distribution"][code]
        pct = (cnt / tot_act * 100.0) if tot_act > 0 else 0.0
        print(f"   - {name:8s} (Code {code}): {cnt:,} ({pct:.2f}%)")
    print("==========================================================================\n")

    return meta


if __name__ == '__main__':
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
    default_data = os.path.join(REPO_ROOT, "data")
    default_output = os.path.join(REPO_ROOT, "data", "mouse_dataset_fixed_N256_full.npz")

    parser = argparse.ArgumentParser(description="Preprocess All SQLite Mouse Telemetry Databases")
    parser.add_argument("--data_dir", type=str, default=default_data, help="Directory containing .sqlite3 databases")
    parser.add_argument("--output", type=str, default=default_output, help="Output .npz path")
    parser.add_argument("--horizon", type=int, default=256, help="Fixed horizon length N")
    parser.add_argument("--min_steps", type=int, default=15, help="Minimum step count")
    parser.add_argument("--min_displacement", type=float, default=30.0, help="Minimum Euclidean displacement in px")
    parser.add_argument("--max_ortho_ratio", type=float, default=0.85, help="Max orthogonal staircase ratio")
    parser.add_argument("--max_pause_sec", type=float, default=3.0, help="Max pause before splitting sub-episode")
    parser.add_argument("--max_files", type=int, default=None, help="Limit number of database files (for testing)")

    args = parser.parse_args()

    process_all_sqlite(
        data_dir=args.data_dir,
        output_npz=args.output,
        max_len=args.horizon,
        min_steps=args.min_steps,
        min_displacement=args.min_displacement,
        max_ortho_ratio=args.max_ortho_ratio,
        max_pause_sec=args.max_pause_sec,
        max_files=args.max_files
    )
