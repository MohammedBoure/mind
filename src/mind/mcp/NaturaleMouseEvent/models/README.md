# Trained Models Directory

This directory stores trained PyTorch neural network checkpoints, weights, and evaluation artifacts for the AI Natural Human Mouse system.

## Checkpoints

### 1. `production_mouse_model.pth`
- **Architecture**: `MemoryConditionedMouseGenerator` (901,767 parameters).
  - `ExtendedConditioningEncoder`: Encodes 8D Extended Motion History Context (`[vx_prev, vy_prev, dt_dwell, dx_jump, dy_jump, click_density, avg_dt, momentum_mag]`), start/target screen positions, binary intent flag, and 16D Gaussian stochastic noise ($z \sim \mathcal{N}(0, I)$).
  - `KinematicDecoder`: 2-layer GRU with step-wise context projection injection, bounded continuous kinematics head ($\tanh$-scaled $\le 0.08$ step displacement, sigmoid-scaled $\Delta t$), and 4-class discrete action classification (`Move`, `Press`, `Release`, `Scroll`).
- **Target Ingestion**: Trained across 100% of the trajectory archive (`data/mouse_dataset_fixed_N256_full.npz`, all 53,028 human episodes).
- **Split**: 85/15 stratified train/val split (45,073 train / 7,955 validation episodes).
- **Execution**: Run with `--full` on GPU (`pin_memory=True`, `num_workers=4`). Auto-discovered by `HumanMouse` API, CLI utilities, and MCP server with top priority.
- **Biomechanical Kinematic Safeguards**:
  - *Acceleration Spike Elimination*: Initial displacement modulated by a 10-step smoothstep muscle recruitment ramp ($\tau^2(3-2\tau)$), strictly bounding initial acceleration below $90,000\text{ px/s}^2$.
  - *Physiological Tremor Modeling*: Continuous 8–12 Hz Ornstein-Uhlenbeck (OU) process ($\theta=15.0, \sigma=0.22$) with ballistic velocity suppression.
  - *Tail Plateau Elimination*: Flash & Hogan (1985) quintic minimum-jerk polynomial deceleration down to a terminal $0.00\text{ px/s}$ resting state.

### 2. `human_mouse_model.pt`
- **Architecture**: Compact deployment PyTorch checkpoint containing model state dict and evaluation validation metrics for lightweight deployment across MCP tools and CLI runners.

---
> [!NOTE]
> Redundant intermediate checkpoints (`pilot_mouse_model.pth` and `best_model.pth`) have been pruned to keep repository footprint lean while preserving full production weights.
