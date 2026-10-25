# PyTorch Training Pipeline

This directory contains production and pilot training pipelines for training neural mouse trajectory models.

## Files

- **`train_pilot.py`**: Production-grade training script with Extended Motion History Context (Kinematic Memory):
  - Integrates 8D inter-episode history context vector $[v_{x0}, v_{y0}, \Delta t_{\text{dwell}}, \Delta x_{\text{jump}}, \Delta y_{\text{jump}}, \text{click\_density}, \text{avg\_dt}, \|\mathbf{v}_0\|]$ to maintain biomechanical momentum continuity across sequential goals.
  - Multi-objective `KinematicBioLoss` combining Smooth L1 kinematics, endpoint terminal reach, temporal cadence, discrete bio-jerk regularizer, boundary acceleration constraints, and Action Cross-Entropy.
  - Supports `--full` flag for full dataset training (53k episodes) with Automatic Mixed Precision (AMP FP16) and direct in-memory indexing.
- **`train_model.py`**: Baseline training pipeline implementing GRU decoder, scheduled sampling teacher forcing decay ($1.0 \to 0.1$), and multi-objective Huber distance smooth loss.
- **`__init__.py`**: Module package initializer.
