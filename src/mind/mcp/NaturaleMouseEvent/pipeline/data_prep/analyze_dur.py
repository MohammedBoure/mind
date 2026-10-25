import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))

dataset_candidates = [
    sys.argv[1] if len(sys.argv) > 1 else None,
    os.path.join(REPO_ROOT, "data", "mouse_dataset_fixed_N256_full.npz"),
    "data/mouse_dataset_fixed_N256_full.npz",
    os.path.join(REPO_ROOT, "data", "mouse_dataset_fixed_N256.npz"),
    "mouse_dataset_fixed_N256.npz"
]
dataset_path = next((p for p in dataset_candidates if p and os.path.exists(p)), None)
if not dataset_path:
    print("Error: Could not locate dataset .npz file.")
    sys.exit(1)

data = np.load(dataset_path)
masks = data['padding_masks'].astype(bool)
seqs = data['seq_tensors']
dts = []
episode_durs = []

for i in range(len(seqs)):
    valid_seq = seqs[i][masks[i]]
    # dt_ms = seq[:, 2] * 100
    ep_dts = valid_seq[:, 2] * 100
    dts.extend(ep_dts)
    episode_durs.append(np.sum(ep_dts))

dts = np.array(dts)
episode_durs = np.array(episode_durs)

print('=== Step DTs (ms) ===')
print('Mean:', np.mean(dts))
print('Median:', np.median(dts))
print('Min:', np.min(dts))
print('Max:', np.max(dts))
print('95th percentile:', np.percentile(dts, 95))
print('99th percentile:', np.percentile(dts, 99))

print('\n=== Episode Durations (ms) ===')
print('Mean:', np.mean(episode_durs))
print('Median:', np.median(episode_durs))
print('95th percentile:', np.percentile(episode_durs, 95))
print('99th percentile:', np.percentile(episode_durs, 99))
