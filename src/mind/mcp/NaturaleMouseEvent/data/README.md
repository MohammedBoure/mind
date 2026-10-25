# Mouse Dataset Directory

This directory contains preprocessed trajectory datasets used for training the AI Natural Human Mouse models.

## Files

- **`mouse_dataset_fixed_N256_full.npz`**: Compressed NumPy archive containing 53,028 goal-directed human mouse movement episodes extracted from 8,335,207 raw telemetry events across 12 SQLite databases (`mouse_events_*.sqlite3`). Padded/chunked to a fixed sequence horizon of $N = 256$.
  - `seq_tensors`: `(53028, 256, 6)` float32 — Step features $[\Delta x, \Delta y, \Delta t, rem_x, rem_y, \text{action\_code}]$.
  - `prev_contexts`: `(53028, 4)` float32 — 4D momentum context $[v_{x0}, v_{y0}, \text{click\_density}, \text{avg\_dt\_scaled}]$.
  - `start_targets`: `(53028, 4)` float32 — Concatenated coordinates $[x_0, y_0, x_{\text{tgt}}, y_{\text{tgt}}]$.
  - `masks`: `(53028, 256)` float32 — Binary mask (1.0 = valid recorded step, 0.0 = padded).
  - `meta`: Summary dictionary (total files, total raw events, rejection breakdown, duration & step kinematics, action distribution).
  - `start_positions`: `(53028, 2)` float32 — Normalized start coordinates.
  - `target_positions`: `(53028, 2)` float32 — Normalized destination coordinates.
  - `previous_contexts`: `(53028, 4)` float32 — Canonical alias for `prev_contexts`.
  - `padding_masks`: `(53028, 256)` float32 — Canonical alias for `masks`.
  - `intents`: `(53028, 1)` float32 — Binary flag (1.0 = target click action, 0.0 = movement/wandering).
- **`mouse_dataset_fixed_N256_full_metadata.json`**: JSON export of dataset metadata and biometric statistics.
- **`mouse_events_*.sqlite3`**: Raw telemetry database files (12 SQLite databases) capturing authentic user mouse interactions.
