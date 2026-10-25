# Data Preparation & Extraction Pipeline

This directory contains data engineering tools to process, clean, and convert raw SQLite mouse telemetry databases into standardized PyTorch training datasets.

## Files

- **`preprocess_all_sqlite.py`**: High-performance batch data preprocessor. Iterates through all SQLite databases (`data/*.sqlite3`), enforces monotonic timestamps, filters robotic staircase / orthogonal grid artifacts, segments prolonged pauses ($> 3.0$ s), and outputs unified padded tensor archives (`data/mouse_dataset_fixed_N256_full.npz`).
- **`prepare_dataset.py`**: Legacy preprocessor utility for single-file or directory database conversions.
- **`scan_dbs.py`**: Diagnostic scanner reporting total event counts, session distributions, and episodes exceeding maximum horizon limits.
- **`analyze_dur.py`**: Statistical distribution analyzer computing step time deltas ($\Delta t$), median durations, and 95th/99th percentile kinematics.
- **`__init__.py`**: Module package initializer.
