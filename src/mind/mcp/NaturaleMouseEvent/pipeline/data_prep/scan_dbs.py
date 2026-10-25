import sqlite3
import os
import glob
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, "data")
db_files = glob.glob(os.path.join(data_dir, "*.sqlite3"))

total_events = 0
total_episodes = 0
total_discarded_exceeded = 0

max_len = 256

for db_path in db_files:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM events")
        events_cnt = cursor.fetchone()[0]
        total_events += events_cnt
        
        cursor.execute("""
            SELECT COUNT(*) as cnt
            FROM events
            GROUP BY session_id, episode_index
        """)
        episodes = cursor.fetchall()
        total_episodes += len(episodes)
        
        for ep in episodes:
            if ep[0] > max_len:
                total_discarded_exceeded += 1
                
    except Exception as e:
        print(f"Error in {db_path}: {e}")
    conn.close()

print(f"Total DB Files: {len(db_files)}")
print(f"Total Events: {total_events}")
print(f"Total Episodes: {total_episodes}")
print(f"Episodes > {max_len}: {total_discarded_exceeded}")
