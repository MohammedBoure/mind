import sqlite3
import numpy as np
import json
import os
import argparse
import glob

def prepare_dataset(data_dir, max_len=256, min_len=3, output_dir=None):
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(data_dir))

    if os.path.isfile(data_dir) and data_dir.endswith('.sqlite3'):
        db_files = [data_dir]
        output_dir = os.path.dirname(os.path.abspath(data_dir))
    else:
        db_files = glob.glob(os.path.join(data_dir, "*.sqlite3"))
        
    if not db_files:
        print(f"No .sqlite3 files found in {data_dir}")
        return

    print(f"Found {len(db_files)} database files. Processing...")

    retained_samples = []
    total_episodes = 0
    discarded_micro = 0

    for db_path in db_files:
        print(f"Processing {os.path.basename(db_path)}...")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get monitor resolution mapping from session
        try:
            sessions = cursor.execute("SELECT session_id, monitors_json FROM sessions").fetchall()
        except sqlite3.OperationalError:
            sessions = []

        session_monitors = {}
        for s in sessions:
            try:
                mons = json.loads(s['monitors_json'])
                w = mons[0]['width'] if mons else 1920
                h = mons[0]['height'] if mons else 1080
            except Exception:
                w, h = 1920, 1080
            session_monitors[s['session_id']] = (float(w), float(h))

        cursor.execute("""
            SELECT session_id, COUNT(*) as cnt
            FROM events
            GROUP BY session_id
        """)
        session_info = cursor.fetchall()

        prev_context = np.zeros(4, dtype=np.float32)

        for sess in session_info:
            sess_id = sess['session_id']
            cnt = sess['cnt']

            if cnt < min_len:
                discarded_micro += 1
                continue

            # Fetch all events for the session ordered by time
            rows = cursor.execute("""
                SELECT t_monotonic_ns, event_type, x, y, dx, dy, button, pressed
                FROM events
                WHERE session_id = ?
                ORDER BY event_index ASC
            """, (sess_id,)).fetchall()

            if not rows or len(rows) < min_len:
                discarded_micro += 1
                continue

            W, H = session_monitors.get(sess_id, (1920.0, 1080.0))

            # Group events into 3-second windows
            window_duration_ns = 3.0 * 1e9
            windows = []
            current_window = []
            window_start_t = rows[0]['t_monotonic_ns']

            for r in rows:
                if r['t_monotonic_ns'] - window_start_t > window_duration_ns:
                    if len(current_window) >= min_len:
                        windows.append(current_window)
                    current_window = [r]
                    window_start_t = r['t_monotonic_ns']
                else:
                    current_window.append(r)
            
            if len(current_window) >= min_len:
                windows.append(current_window)
                
            total_episodes += len(windows)

            for win_rows in windows:
                # Truncate to max_len if necessary
                if len(win_rows) > max_len:
                    win_rows = win_rows[:max_len]
                    
                # Calculate Intent (1.0 if there is any click/button press in this window)
                has_click = any(r['event_type'] in ['click', 'button'] for r in win_rows)
                intent = 1.0 if has_click else 0.0

                start_x = float(win_rows[0]['x']) / W
                start_y = float(win_rows[0]['y']) / H
                target_x = float(win_rows[-1]['x']) / W
                target_y = float(win_rows[-1]['y']) / H

                start_pos = np.array([start_x, start_y], dtype=np.float32)
                target_pos = np.array([target_x, target_y], dtype=np.float32)

                context_vec = np.copy(prev_context)

                seq_tensor = np.zeros((max_len, 6), dtype=np.float32)
                mask = np.zeros(max_len, dtype=np.float32)

                prev_t = win_rows[0]['t_monotonic_ns']
                prev_x = float(win_rows[0]['x'])
                prev_y = float(win_rows[0]['y'])

                t0 = win_rows[0]['t_monotonic_ns']
                t_end = win_rows[-1]['t_monotonic_ns']
                dur_sec = (t_end - t0) / 1e9
                
                # Calculate metrics for the NEXT context
                clicks = sum(1 for r in win_rows if r['event_type'] in ['click', 'button'])
                avg_dt_ms = (dur_sec / len(win_rows)) * 1000 if len(win_rows) > 0 else 0
                
                if dur_sec > 0:
                    total_dx = (win_rows[-1]['x'] - win_rows[0]['x']) / W
                    total_dy = (win_rows[-1]['y'] - win_rows[0]['y']) / H
                    prev_context = np.array([total_dx / dur_sec, total_dy / dur_sec, clicks / float(max_len), avg_dt_ms / 100.0], dtype=np.float32)
                else:
                    prev_context = np.zeros(4, dtype=np.float32)

                for i, r in enumerate(win_rows):
                    dt_ms = (r['t_monotonic_ns'] - prev_t) / 1e6
                    dx = (r['x'] - prev_x) / W
                    dy = (r['y'] - prev_y) / H

                    curr_x = r['x'] / W
                    curr_y = r['y'] / H

                    rem_x = target_x - curr_x
                    rem_y = target_y - curr_y

                    action_code = 0.0
                    if r['event_type'] == 'click' or r['event_type'] == 'button':
                        action_code = 1.0 if r['pressed'] else 2.0
                    elif r['event_type'] == 'scroll':
                        action_code = 3.0

                    dt_ms = min(dt_ms, 500.0)

                    seq_tensor[i] = [dx, dy, dt_ms / 100.0, rem_x, rem_y, action_code]
                    mask[i] = 1.0

                    prev_t = r['t_monotonic_ns']
                    prev_x = float(r['x'])
                    prev_y = float(r['y'])

                retained_samples.append({
                    "start_pos": start_pos,
                    "target_pos": target_pos,
                    "previous_context": context_vec,
                    "intent": np.array([intent], dtype=np.float32),
                    "seq_tensor": seq_tensor,
                    "padding_mask": mask
                })
                
        conn.close()

    num_samples = len(retained_samples)

    if num_samples == 0:
        print("No samples retained!")
        return None

    print(f"\nProcessing complete. Assembling tensors for {num_samples} samples...")

    start_positions = np.stack([s['start_pos'] for s in retained_samples])
    target_positions = np.stack([s['target_pos'] for s in retained_samples])
    previous_contexts = np.stack([s['previous_context'] for s in retained_samples]) if num_samples > 0 else np.empty((0, 4))
    intents = np.stack([s['intent'] for s in retained_samples]) if num_samples > 0 else np.empty((0, 1))
    seq_tensors = np.stack([s['seq_tensor'] for s in retained_samples])
    padding_masks = np.stack([s['padding_mask'] for s in retained_samples])

    npz_path = os.path.join(output_dir, f"mouse_dataset_fixed_N{max_len}_full.npz")
    print(f"Saving NPZ to {npz_path} (This might take a minute)...")
    np.savez_compressed(
        npz_path,
        start_positions=start_positions,
        target_positions=target_positions,
        previous_contexts=previous_contexts,
        intents=intents,
        seq_tensors=seq_tensors,
        padding_masks=padding_masks
    )

    json_summary = {
        "dataset_name": f"Mouse Trajectories Full Dataset N={max_len}",
        "max_length_N": max_len,
        "total_episodes_in_db": total_episodes,
        "retained_samples_count": num_samples,
        "discarded_micro": discarded_micro,
        "tensor_shapes": {
            "start_positions": list(start_positions.shape),
            "target_positions": list(target_positions.shape),
            "previous_contexts": list(previous_contexts.shape),
            "intents": list(intents.shape),
            "seq_tensors": list(seq_tensors.shape),
            "padding_masks": list(padding_masks.shape)
        }
    }

    json_path = os.path.join(output_dir, f"mouse_dataset_fixed_N{max_len}_full_metadata.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_summary, f, indent=2, ensure_ascii=False)

    print("\n=======================================================")
    print("      PHASE 1 DATASET PREPROCESSING COMPLETE           ")
    print("=======================================================")
    print(f"Total Database Episodes:  {total_episodes}")
    print(f"Total Model Samples:      {num_samples}")
    print(f"Discarded (< {min_len}):         {discarded_micro}")
    print(f"Tensors NPZ Saved To:      {npz_path}")
    print(f"Metadata JSON Saved To:   {json_path}")
    print("=======================================================")

    return json_summary

if __name__ == '__main__':
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
    default_data = os.path.join(REPO_ROOT, "data")

    parser = argparse.ArgumentParser(description="Full Dataset Preprocessor for Mouse Event AI")
    parser.add_argument("--data_dir", type=str, default=default_data, help="Directory containing .sqlite3 files")
    parser.add_argument("--max_len", type=int, default=256)
    parser.add_argument("--min_len", type=int, default=3)
    args = parser.parse_args()

    prepare_dataset(args.data_dir, max_len=args.max_len, min_len=args.min_len)
