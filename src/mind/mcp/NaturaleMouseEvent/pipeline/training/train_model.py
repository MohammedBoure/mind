"""
AI Natural Human Mouse Trajectory Generator - PyTorch Training Pipeline
========================================================================
Production-grade training script for generating biologically authentic,
natural human mouse cursor trajectories with behavioral conditioning,
kinematics, and action classification.

Key Architectural & Algorithmic Features:
- Behavioral Biometrics Conditioning (Start, Target, Momentum Context, Intent, Gaussian Noise)
- ConditioningEncoder (MLP with LayerNorm & SiLU activations)
- KinematicDecoder (2-layer GRU with continuous context injection)
- Xavier-Initialized Kinematics Head with Bounded Scaling (max_step_delta=0.08)
  allowing realistic human burst velocities without runaway divergence
- Action Head: 4-class discrete logits (Move, Press, Release, Scroll)
- Dynamic Closed-Loop State Tracking: Incremental coordinate accumulation and rem_x, rem_y
  feedback with screen-boundary clamping
- Multi-Objective DistanceSmoothLoss:
  1) Kinematics Huber Loss on (dx, dy, dt)
  2) Trajectory Path Alignment Loss (Smooth L1 against human intermediate waypoints)
  3) Target Reach Loss (L1 penalty at final valid timestep)
  4) Step-wise Directional Progress Loss (penalizing stagnation along target direction)
  5) Low-weight Jerk Smoothness regularizer (w=0.02) allowing human ballistic motion
  6) Action Cross-Entropy
- Scheduled Sampling: Decaying Teacher Forcing ratio across epochs
- Sample Episode Trajectory Tracking during Evaluation
"""

import os
import sys
import time
import math
import random
import argparse
from typing import Dict, Tuple, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split


# =====================================================================
# 1. Dataset & Data Loading
# =====================================================================

class MouseTrajectoryDataset(Dataset):
    """
    Dataset loader for preprocessed human mouse trajectory episodes.
    Loads and serves tensors from mouse_dataset_fixed_N256_full.npz.

    Shapes:
    - start_positions: (N, 2) normalized [x0, y0]
    - target_positions: (N, 2) normalized [x_tgt, y_tgt]
    - previous_contexts: (N, 4) [vx, vy, click_density, avg_dt_scaled]
    - intents: (N, 1) binary flag (1.0 = click target, 0.0 = wander/idle)
    - seq_tensors: (N, 256, 6) [dx, dy, dt, rem_x, rem_y, action_code]
    - padding_masks: (N, 256) binary mask (1.0 = valid step, 0.0 = padded)
    """
    def __init__(self, npz_path: str):
        if not os.path.exists(npz_path):
            raise FileNotFoundError(f"Dataset file not found at: {npz_path}")

        print(f"[Dataset] Loading preprocessed dataset from: {npz_path}")
        data = np.load(npz_path)

        self.start_positions = torch.from_numpy(data['start_positions']).float()
        self.target_positions = torch.from_numpy(data['target_positions']).float()
        self.previous_contexts = torch.from_numpy(data['previous_contexts']).float()
        self.intents = torch.from_numpy(data['intents']).float()
        self.seq_tensors = torch.from_numpy(data['seq_tensors']).float()
        self.padding_masks = torch.from_numpy(data['padding_masks']).float()
        self.length = len(self.start_positions)

        print(f"[Dataset] Successfully loaded {self.length} trajectory episodes.")

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, ...]:
        return (
            self.start_positions[idx],
            self.target_positions[idx],
            self.previous_contexts[idx],
            self.intents[idx],
            self.seq_tensors[idx],
            self.padding_masks[idx]
        )


# =====================================================================
# 2. Model Architecture
# =====================================================================

class ConditioningEncoder(nn.Module):
    """
    MLP Conditioning Encoder for behavioral and kinematic conditioning.
    Maps:
      [start_pos(2), target_pos(2), context(4), intent(1), noise_z(noise_dim)] (total 9 + noise_dim)
    To:
      1) Initial GRU hidden state h_0: (num_layers, B, hidden_dim)
      2) Task Context Embedding: (B, cond_dim) concatenated at each decoding timestep.
    """
    def __init__(
        self,
        noise_dim: int = 16,
        hidden_dim: int = 256,
        cond_dim: int = 64,
        num_layers: int = 2
    ):
        super().__init__()
        self.noise_dim = noise_dim
        self.hidden_dim = hidden_dim
        self.cond_dim = cond_dim
        self.num_layers = num_layers

        in_dim = 2 + 2 + 4 + 1 + noise_dim  # 9 + noise_dim

        self.mlp = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU()
        )

        self.to_h0 = nn.Linear(hidden_dim, num_layers * hidden_dim)
        self.to_context = nn.Linear(hidden_dim, cond_dim)

    def forward(
        self,
        start_pos: torch.Tensor,
        target_pos: torch.Tensor,
        prev_context: torch.Tensor,
        intent: torch.Tensor,
        z_noise: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        B = start_pos.size(0)
        if z_noise is None:
            z_noise = torch.randn(B, self.noise_dim, device=start_pos.device, dtype=start_pos.dtype)

        # Concatenate conditioning vector
        x = torch.cat([start_pos, target_pos, prev_context, intent, z_noise], dim=-1)
        feat = self.mlp(x)

        # Map to h0: (num_layers, B, hidden_dim)
        h0 = self.to_h0(feat).view(B, self.num_layers, self.hidden_dim).permute(1, 0, 2).contiguous()
        # Context embedding to condition every recurrent step
        cond_embed = self.to_context(feat)

        return h0, cond_embed


class KinematicDecoder(nn.Module):
    """
    2-Layer GRU Kinematic Decoder with Dual-Head Output:
    - Kinematics Head: Outputs (dx, dy, dt) initialized with Xavier uniform
      and bounded via tanh and sigmoid to allow human burst velocities without runaway divergence.
    - Action Head: Outputs raw logits for 4 discrete action classes.
    """
    def __init__(
        self,
        hidden_dim: int = 256,
        cond_dim: int = 64,
        num_layers: int = 2,
        num_classes: int = 4,
        max_step_delta: float = 0.08,
        max_dt: float = 5.0
    ):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.cond_dim = cond_dim
        self.num_layers = num_layers
        self.num_classes = num_classes
        self.max_step_delta = max_step_delta
        self.max_dt = max_dt

        # Step input: [dx, dy, dt, rem_x, rem_y] (5) + cond_embed (cond_dim)
        step_in_dim = 5 + cond_dim

        self.gru = nn.GRU(
            input_size=step_in_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True
        )

        # Kinematics Head: outputs (dx, dy, dt)
        self.kinematics_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.SiLU(),
            nn.Linear(64, 3)
        )

        # Standard Xavier/Glorot uniform initialization to avoid lazy zero-movement local minima
        nn.init.xavier_uniform_(self.kinematics_head[-1].weight)
        nn.init.zeros_(self.kinematics_head[-1].bias)

        # Action Head: outputs logits for 4 discrete actions (Move, Press, Release, Scroll)
        self.action_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.SiLU(),
            nn.Linear(64, num_classes)
        )

    def forward_step(
        self,
        step_input: torch.Tensor,
        h: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Executes a single recurrent step with bounded output scaling.
        step_input: (B, 1, step_in_dim)
        h: (num_layers, B, hidden_dim)
        """
        gru_out, h_next = self.gru(step_input, h)
        out_flat = gru_out.squeeze(1)

        raw_kin = self.kinematics_head(out_flat)

        # Physical Output Bounding:
        # dx, dy: Tanh activation scaled to max_step_delta (~0.08 normalized screen units)
        # dt: Sigmoid activation scaled to max_dt (~5.0, i.e., 500ms max)
        dx = torch.tanh(raw_kin[:, 0:1]) * self.max_step_delta
        dy = torch.tanh(raw_kin[:, 1:2]) * self.max_step_delta
        dt = torch.sigmoid(raw_kin[:, 2:3]) * self.max_dt

        kin_pred = torch.cat([dx, dy, dt], dim=-1)
        action_logits = self.action_head(out_flat)

        return kin_pred, action_logits, h_next


class HumanMouseGenerator(nn.Module):
    """
    Full AI Natural Human Mouse Model.
    Combines ConditioningEncoder and KinematicDecoder with support for:
    - Bounded kinematic outputs preventing runaway compound error
    - Closed-loop dynamic coordinate & rem_x, rem_y state tracking
    - Vectorized scheduled sampling per batch item
    - Trajectory reconstruction with padding step freezing
    """
    def __init__(
        self,
        noise_dim: int = 16,
        hidden_dim: int = 256,
        cond_dim: int = 64,
        seq_len: int = 256,
        num_layers: int = 2,
        num_classes: int = 4,
        max_step_delta: float = 0.08
    ):
        super().__init__()
        self.seq_len = seq_len
        self.noise_dim = noise_dim
        self.hidden_dim = hidden_dim
        self.cond_dim = cond_dim
        self.num_layers = num_layers
        self.num_classes = num_classes
        self.max_step_delta = max_step_delta

        self.encoder = ConditioningEncoder(
            noise_dim=noise_dim,
            hidden_dim=hidden_dim,
            cond_dim=cond_dim,
            num_layers=num_layers
        )

        self.decoder = KinematicDecoder(
            hidden_dim=hidden_dim,
            cond_dim=cond_dim,
            num_layers=num_layers,
            num_classes=num_classes,
            max_step_delta=max_step_delta
        )

    def forward(
        self,
        start_pos: torch.Tensor,
        target_pos: torch.Tensor,
        prev_context: torch.Tensor,
        intent: torch.Tensor,
        z_noise: Optional[torch.Tensor] = None,
        teacher_forcing_ratio: float = 0.0,
        true_seq: Optional[torch.Tensor] = None,
        padding_masks: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Autoregressive rollout over seq_len timesteps.

        Args:
            start_pos: (B, 2) initial normalized coordinates
            target_pos: (B, 2) destination coordinates
            prev_context: (B, 4) historical momentum context
            intent: (B, 1) target click intent (1.0 or 0.0)
            z_noise: Optional (B, noise_dim) latent stochastic vector
            teacher_forcing_ratio: float in [0.0, 1.0] for scheduled sampling
            true_seq: Optional (B, seq_len, 6) ground truth sequence for teacher forcing
            padding_masks: Optional (B, seq_len) binary mask for valid vs padded steps

        Returns:
            pred_kinematics: (B, seq_len, 3) -> [dx, dy, dt]
            pred_actions: (B, seq_len, 4) -> action logits
            pred_traj: (B, seq_len, 2) -> accumulated coordinates [x_curr, y_curr]
        """
        B = start_pos.size(0)
        h, cond_embed = self.encoder(start_pos, target_pos, prev_context, intent, z_noise)

        curr_pos = start_pos.clone()
        prev_kin = torch.zeros(B, 3, device=start_pos.device, dtype=start_pos.dtype)

        pred_kinematics = []
        pred_actions = []

        use_tf = (teacher_forcing_ratio > 0.0 and true_seq is not None and self.training)

        for t in range(self.seq_len):
            # Dynamic closed-loop remaining distance feedback (clamped to [-1.0, 1.0])
            rem = torch.clamp(target_pos - curr_pos, min=-1.0, max=1.0)
            step_feat = torch.cat([prev_kin, rem, cond_embed], dim=-1).unsqueeze(1)

            # GRU step output
            kin_step, action_logits, h = self.decoder.forward_step(step_feat, h)

            pred_kinematics.append(kin_step)
            pred_actions.append(action_logits)

            # Step mask: freeze updates if padded step
            if padding_masks is not None:
                step_mask = padding_masks[:, t:t+1]
            else:
                step_mask = torch.ones(B, 1, device=start_pos.device, dtype=start_pos.dtype)

            # Scheduled sampling: vectorized coin flip per batch element
            if use_tf:
                tf_coin = (torch.rand(B, 1, device=start_pos.device) < teacher_forcing_ratio).float()
                next_dx_dy = tf_coin * true_seq[:, t, 0:2] + (1.0 - tf_coin) * kin_step[:, 0:2]
                next_dt = tf_coin * true_seq[:, t, 2:3] + (1.0 - tf_coin) * kin_step[:, 2:3]
            else:
                next_dx_dy = kin_step[:, 0:2]
                next_dt = kin_step[:, 2:3]

            # Accumulate displacement only on valid steps and clamp coordinates to screen safety boundary
            disp_update = next_dx_dy * step_mask
            curr_pos = torch.clamp(curr_pos + disp_update, min=-0.1, max=1.1)
            prev_kin = torch.cat([next_dx_dy * step_mask, next_dt], dim=-1)

        pred_kinematics = torch.stack(pred_kinematics, dim=1) # (B, seq_len, 3)
        pred_actions = torch.stack(pred_actions, dim=1)       # (B, seq_len, 4)

        # Reconstruct full cumulative predicted trajectory from model's predicted displacements
        # Gradients from trajectory & reach losses flow directly through cumsum into pred_kinematics
        if padding_masks is not None:
            valid_pred_disp = pred_kinematics[:, :, 0:2] * padding_masks.unsqueeze(-1)
        else:
            valid_pred_disp = pred_kinematics[:, :, 0:2]

        pred_traj = start_pos.unsqueeze(1) + torch.cumsum(valid_pred_disp, dim=1)

        return pred_kinematics, pred_actions, pred_traj

    @torch.no_grad()
    def generate(
        self,
        start_pos: torch.Tensor,
        target_pos: torch.Tensor,
        prev_context: torch.Tensor,
        intent: torch.Tensor,
        z_noise: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Free-running inference generator.
        """
        was_training = self.training
        self.eval()
        outputs = self.forward(
            start_pos=start_pos,
            target_pos=target_pos,
            prev_context=prev_context,
            intent=intent,
            z_noise=z_noise,
            teacher_forcing_ratio=0.0,
            true_seq=None,
            padding_masks=None
        )
        self.train(was_training)
        return outputs


# =====================================================================
# 3. Loss Function & Optimization Objectives
# =====================================================================

class DistanceSmoothLoss(nn.Module):
    """
    Active Masked Multi-Task Kinematic Trajectory Loss:
    - Kinematics Loss: Masked Huber (Smooth L1) loss on (dx, dy, dt).
    - Trajectory Path Loss (w=15.0): Intermediate position tracking along human trajectory path.
    - Target Reach Loss (w=25.0): L1 penalty at final valid timestep.
    - Directional Progress Loss (w=5.0): Penalize stagnation/backward motion along target vector.
    - Jerk / Smoothness Penalty (w=0.02): Low weight regularizer to avoid penalizing human ballistic motion.
    - Action Classification Loss: Masked Cross-Entropy for 4-class discrete actions.
    - Masking: Padded steps (padding_mask == 0) have strictly zero contribution to all losses.
    """
    def __init__(
        self,
        w_kin: float = 5.0,
        w_traj: float = 15.0,
        w_reach: float = 25.0,
        w_progress: float = 5.0,
        w_smooth: float = 0.02,
        w_action: float = 1.0,
        huber_beta: float = 0.01
    ):
        super().__init__()
        self.w_kin = w_kin
        self.w_traj = w_traj
        self.w_reach = w_reach
        self.w_progress = w_progress
        self.w_smooth = w_smooth
        self.w_action = w_action
        self.huber_beta = huber_beta

    def forward(
        self,
        pred_kinematics: torch.Tensor,
        pred_action_logits: torch.Tensor,
        pred_traj: torch.Tensor,
        true_seq: torch.Tensor,
        true_target: torch.Tensor,
        padding_masks: torch.Tensor,
        start_pos: torch.Tensor
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        B, seq_len, _ = pred_kinematics.shape
        eps = 1e-8

        # -------------------------------------------------------------
        # 1. Kinematics Loss: Masked Smooth L1 on (dx, dy, dt)
        # -------------------------------------------------------------
        true_kin = true_seq[:, :, 0:3]
        kin_diff = F.smooth_l1_loss(pred_kinematics, true_kin, reduction='none', beta=self.huber_beta)
        mask_3d = padding_masks.unsqueeze(-1)
        loss_kin = (kin_diff * mask_3d).sum() / (mask_3d.sum() * 3.0 + eps)

        # -------------------------------------------------------------
        # 2. Trajectory Path Loss: Intermediate position tracking
        # -------------------------------------------------------------
        true_traj = start_pos.unsqueeze(1) + torch.cumsum(true_seq[:, :, 0:2] * mask_3d, dim=1)
        traj_diff = F.smooth_l1_loss(pred_traj, true_traj, reduction='none', beta=self.huber_beta).sum(dim=-1)
        loss_traj = (traj_diff * padding_masks).sum() / (padding_masks.sum() + eps)

        # -------------------------------------------------------------
        # 3. Target Reach Loss: Endpoint L1 error at final valid step
        # -------------------------------------------------------------
        last_indices = torch.clamp(padding_masks.sum(dim=1).long() - 1, min=0, max=seq_len - 1)
        batch_indices = torch.arange(B, device=pred_traj.device)
        final_pred_pos = pred_traj[batch_indices, last_indices]
        loss_reach = F.l1_loss(final_pred_pos, true_target, reduction='mean')

        # Real screen-pixel reach error for logging (1920x1080 display standard)
        scale_px = torch.tensor([1920.0, 1080.0], device=pred_traj.device)
        reach_dist_px = torch.norm((final_pred_pos - true_target) * scale_px, dim=-1).mean()

        # -------------------------------------------------------------
        # 4. Directional Progress Loss: Penalize stagnation along target direction
        # -------------------------------------------------------------
        target_vec = true_target.unsqueeze(1) - pred_traj # (B, seq_len, 2)
        target_dist = torch.norm(target_vec, dim=-1, keepdim=True) + 1e-6
        target_unit_dir = target_vec / target_dist

        step_disp = pred_kinematics[:, :, 0:2]
        progress_along_target = (step_disp * target_unit_dir).sum(dim=-1) # (B, seq_len)

        # Penalize lack of positive movement towards target when still outside arrival radius
        active_progress_mask = padding_masks * (target_dist.squeeze(-1) > 0.015).float()
        progress_penalty = F.relu(0.001 - progress_along_target)
        loss_progress = (progress_penalty * active_progress_mask).sum() / (active_progress_mask.sum() + eps)

        # -------------------------------------------------------------
        # 5. Jerk / Smoothness Penalty (Low weight 0.02)
        # -------------------------------------------------------------
        dx_dy = pred_kinematics[:, :, 0:2]
        accel = dx_dy[:, 1:, :] - dx_dy[:, :-1, :]
        jerk = accel[:, 1:, :] - accel[:, :-1, :]

        jerk_mask = (padding_masks[:, 2:] * padding_masks[:, 1:-1] * padding_masks[:, :-2]).unsqueeze(-1)
        loss_smooth = (torch.square(jerk) * jerk_mask).sum() / (jerk_mask.sum() * 2.0 + eps)

        # -------------------------------------------------------------
        # 6. Action Classification Loss: Masked Cross-Entropy
        # -------------------------------------------------------------
        true_actions = true_seq[:, :, 5].long()
        ce_loss_raw = F.cross_entropy(
            pred_action_logits.view(-1, 4),
            true_actions.view(-1),
            reduction='none'
        ).view(B, seq_len)
        loss_action = (ce_loss_raw * padding_masks).sum() / (padding_masks.sum() + eps)

        # Action Accuracy (%) on valid timesteps
        pred_classes = torch.argmax(pred_action_logits, dim=-1)
        correct_actions = (pred_classes == true_actions).float()
        action_acc = (correct_actions * padding_masks).sum() / (padding_masks.sum() + eps) * 100.0

        # Kinematic Displacement MSE
        mse_kin = (torch.square(pred_kinematics[:, :, 0:2] - true_kin[:, :, 0:2]).sum(dim=-1) * padding_masks).sum() / (padding_masks.sum() * 2.0 + eps)

        # Total Weighted Multi-Task Loss
        total_loss = (
            self.w_kin * loss_kin +
            self.w_traj * loss_traj +
            self.w_reach * loss_reach +
            self.w_progress * loss_progress +
            self.w_smooth * loss_smooth +
            self.w_action * loss_action
        )

        metrics = {
            'loss_kin': loss_kin.item(),
            'loss_traj': loss_traj.item(),
            'loss_reach': loss_reach.item(),
            'loss_progress': loss_progress.item(),
            'loss_smooth': loss_smooth.item(),
            'loss_action': loss_action.item(),
            'reach_error_px': reach_dist_px.item(),
            'action_acc': action_acc.item(),
            'mse_kin': mse_kin.item()
        }

        return total_loss, metrics


# =====================================================================
# 4. Training Utilities & Scheduled Sampling
# =====================================================================

def get_scheduled_sampling_ratio(epoch: int, total_epochs: int, tf_start: float = 1.0, tf_end: float = 0.2) -> float:
    """
    Decay schedule for Teacher Forcing ratio across epochs.
    From tf_start down to tf_end.
    """
    if total_epochs <= 1:
        return tf_start
    progress = (epoch - 1) / (total_epochs - 1)
    return max(tf_end, tf_start - progress * (tf_start - tf_end))


def select_optimal_device(requested_device: str = "auto") -> torch.device:
    """
    Selects optimal execution device (CUDA -> MPS -> CPU).
    """
    if requested_device != "auto":
        return torch.device(requested_device)

    if torch.cuda.is_available():
        device = torch.device("cuda")
        print(f"[Hardware] Using CUDA GPU: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
        print("[Hardware] Using Apple Silicon MPS Acceleration.")
    else:
        device = torch.device("cpu")
        num_cores = os.cpu_count() or 4
        torch.set_num_threads(num_cores)
        print(f"[Hardware] Using CPU with {num_cores} active execution threads.")

    return device


def set_seed(seed: int = 42):
    """
    Sets global deterministic random seeds for full reproducibility.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# =====================================================================
# 5. Core Training & Validation Engine
# =====================================================================

def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: optim.Optimizer,
    device: torch.device,
    tf_ratio: float,
    clip_grad_norm: float = 1.0
) -> Tuple[float, Dict[str, float]]:
    """
    Executes one full training epoch with Scheduled Sampling and gradient clipping.
    """
    model.train()
    total_loss = 0.0
    accumulated_metrics = {
        'loss_kin': 0.0,
        'loss_traj': 0.0,
        'loss_reach': 0.0,
        'loss_progress': 0.0,
        'loss_smooth': 0.0,
        'loss_action': 0.0,
        'reach_error_px': 0.0,
        'action_acc': 0.0,
        'mse_kin': 0.0
    }
    total_samples = 0

    for b_start, b_target, b_ctx, b_intent, b_seq, b_mask in loader:
        b_start = b_start.to(device)
        b_target = b_target.to(device)
        b_ctx = b_ctx.to(device)
        b_intent = b_intent.to(device)
        b_seq = b_seq.to(device)
        b_mask = b_mask.to(device)

        batch_size = b_start.size(0)
        optimizer.zero_grad()

        # Forward pass with Scheduled Sampling and padding masks
        pred_kin, pred_actions, pred_traj = model(
            start_pos=b_start,
            target_pos=b_target,
            prev_context=b_ctx,
            intent=b_intent,
            teacher_forcing_ratio=tf_ratio,
            true_seq=b_seq,
            padding_masks=b_mask
        )

        loss, metrics = criterion(
            pred_kinematics=pred_kin,
            pred_action_logits=pred_actions,
            pred_traj=pred_traj,
            true_seq=b_seq,
            true_target=b_target,
            padding_masks=b_mask,
            start_pos=b_start
        )

        loss.backward()

        # Recurrent gradient clipping to prevent gradient explosion
        if clip_grad_norm > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=clip_grad_norm)

        optimizer.step()

        total_loss += loss.item() * batch_size
        for k in accumulated_metrics:
            accumulated_metrics[k] += metrics[k] * batch_size
        total_samples += batch_size

    avg_loss = total_loss / total_samples
    avg_metrics = {k: accumulated_metrics[k] / total_samples for k in accumulated_metrics}
    return avg_loss, avg_metrics


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    print_sample: bool = False
) -> Tuple[float, Dict[str, float]]:
    """
    Evaluates model performance under pure autoregressive rollout (tf_ratio = 0.0).
    Optionally prints sample episode trajectory coordinates to verify active physical movement.
    """
    model.eval()
    total_loss = 0.0
    accumulated_metrics = {
        'loss_kin': 0.0,
        'loss_traj': 0.0,
        'loss_reach': 0.0,
        'loss_progress': 0.0,
        'loss_smooth': 0.0,
        'loss_action': 0.0,
        'reach_error_px': 0.0,
        'action_acc': 0.0,
        'mse_kin': 0.0
    }
    total_samples = 0
    sample_logged = None

    for b_start, b_target, b_ctx, b_intent, b_seq, b_mask in loader:
        b_start = b_start.to(device)
        b_target = b_target.to(device)
        b_ctx = b_ctx.to(device)
        b_intent = b_intent.to(device)
        b_seq = b_seq.to(device)
        b_mask = b_mask.to(device)

        batch_size = b_start.size(0)

        # Autoregressive free-running rollout (tf_ratio = 0.0)
        pred_kin, pred_actions, pred_traj = model(
            start_pos=b_start,
            target_pos=b_target,
            prev_context=b_ctx,
            intent=b_intent,
            teacher_forcing_ratio=0.0,
            true_seq=None,
            padding_masks=b_mask
        )

        loss, metrics = criterion(
            pred_kinematics=pred_kin,
            pred_action_logits=pred_actions,
            pred_traj=pred_traj,
            true_seq=b_seq,
            true_target=b_target,
            padding_masks=b_mask,
            start_pos=b_start
        )

        total_loss += loss.item() * batch_size
        for k in accumulated_metrics:
            accumulated_metrics[k] += metrics[k] * batch_size
        total_samples += batch_size

        # Record first sample episode coordinates for verification
        if print_sample and sample_logged is None:
            s_px = (b_start[0] * torch.tensor([1920.0, 1080.0], device=device)).cpu().numpy()
            t_px = (b_target[0] * torch.tensor([1920.0, 1080.0], device=device)).cpu().numpy()
            last_idx = int(b_mask[0].sum().item()) - 1
            f_px = (pred_traj[0, last_idx] * torch.tensor([1920.0, 1080.0], device=device)).cpu().numpy()
            d_init = np.linalg.norm(t_px - s_px)
            d_final = np.linalg.norm(t_px - f_px)
            d_traversed = np.linalg.norm(f_px - s_px)
            sample_logged = (s_px, t_px, f_px, d_init, d_final, d_traversed)

    if sample_logged is not None:
        s_px, t_px, f_px, d_init, d_final, d_traversed = sample_logged
        print(f"\n   [Sample Eval Track] Start: ({s_px[0]:.1f}, {s_px[1]:.1f}) -> Target: ({t_px[0]:.1f}, {t_px[1]:.1f}) -> Final: ({f_px[0]:.1f}, {f_px[1]:.1f})")
        print(f"                       Start-to-Target: {d_init:.1f} px | Final Reach Error: {d_final:.1f} px | Traversed: {d_traversed:.1f} px")

    avg_loss = total_loss / total_samples
    avg_metrics = {k: accumulated_metrics[k] / total_samples for k in accumulated_metrics}
    return avg_loss, avg_metrics


# =====================================================================
# 6. Main Training Routine
# =====================================================================

def main():
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
    default_data = os.path.join(REPO_ROOT, "data", "mouse_dataset_fixed_N256_full.npz")
    default_save = os.path.join(REPO_ROOT, "models", "best_model.pth")
    default_legacy = os.path.join(REPO_ROOT, "models", "human_mouse_model.pt")

    parser = argparse.ArgumentParser(
        description="Production PyTorch Training Script for AI Natural Human Mouse Kinematic Generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--data",
        type=str,
        default=default_data,
        help="Path to preprocessed .npz trajectory dataset"
    )
    parser.add_argument("--epochs", type=int, default=40, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=64, help="Batch size for training and validation")
    parser.add_argument("--lr", type=float, default=1e-3, help="Peak initial learning rate")
    parser.add_argument("--weight_decay", type=float, default=1e-4, help="AdamW weight decay regularizer")
    parser.add_argument("--hidden_dim", type=int, default=256, help="Hidden state dimension of GRU decoder")
    parser.add_argument("--cond_dim", type=int, default=64, help="Context conditioning embedding dimension")
    parser.add_argument("--noise_dim", type=int, default=16, help="Latent Gaussian stochasticity dimension")
    parser.add_argument("--max_step_delta", type=float, default=0.08, help="Maximum physical single-step displacement")
    parser.add_argument("--tf_start", type=float, default=1.0, help="Initial Teacher Forcing ratio")
    parser.add_argument("--tf_end", type=float, default=0.1, help="Final Teacher Forcing ratio (Scheduled Sampling)")
    parser.add_argument("--clip_grad", type=float, default=1.0, help="Max gradient norm clipping threshold")
    parser.add_argument("--val_split", type=float, default=0.2, help="Validation dataset split ratio")
    parser.add_argument("--save_path", type=str, default=default_save, help="Filepath for saving the best model checkpoint")
    parser.add_argument("--legacy_weights", type=str, default=default_legacy, help="Secondary weights file path for engine compatibility")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--device", type=str, default="auto", help="Device selector: auto, cuda, mps, cpu")

    args = parser.parse_args()

    # Ensure parent directories exist
    os.makedirs(os.path.dirname(os.path.abspath(args.save_path)), exist_ok=True)
    if args.legacy_weights:
        os.makedirs(os.path.dirname(os.path.abspath(args.legacy_weights)), exist_ok=True)

    # Set deterministic seeds
    set_seed(args.seed)
    device = select_optimal_device(args.device)

    # 1. Load Dataset
    dataset = MouseTrajectoryDataset(args.data)
    total_samples = len(dataset)

    val_size = int(args.val_split * total_samples)
    train_size = total_samples - val_size

    generator = torch.Generator().manual_seed(args.seed)
    train_set, val_set = random_split(dataset, [train_size, val_size], generator=generator)

    train_loader = DataLoader(
        train_set,
        batch_size=args.batch_size,
        shuffle=True,
        drop_last=False,
        pin_memory=(device.type == "cuda")
    )
    val_loader = DataLoader(
        val_set,
        batch_size=args.batch_size,
        shuffle=False,
        drop_last=False,
        pin_memory=(device.type == "cuda")
    )

    print(f"\n[Split] Total Samples: {total_samples} | Train: {train_size} | Validation: {val_size}")

    # 2. Instantiate Model & Loss
    model = HumanMouseGenerator(
        noise_dim=args.noise_dim,
        hidden_dim=args.hidden_dim,
        cond_dim=args.cond_dim,
        seq_len=256,
        num_layers=2,
        num_classes=4,
        max_step_delta=args.max_step_delta
    ).to(device)

    criterion = DistanceSmoothLoss(
        w_kin=5.0,
        w_traj=15.0,
        w_reach=25.0,
        w_progress=5.0,
        w_smooth=0.02,
        w_action=1.0,
        huber_beta=0.01
    ).to(device)

    # Count parameters
    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[Model] Initialized HumanMouseGenerator with {total_params:,} trainable parameters.")

    # 3. Optimizer & Learning Rate Scheduler
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)

    print("\n" + "=" * 90)
    print(f"      STARTING TRAINING PIPELINE WITH SCHEDULED SAMPLING (TF: {args.tf_start:.1f} -> {args.tf_end:.1f})")
    print("=" * 90)
    header = f"{'Epoch':^7} | {'TF':^5} | {'LR':^9} | {'Train Loss':^10} | {'Val Loss':^10} | {'Val Reach Err':^13} | {'Val Act Acc':^11} | {'Time':^6}"
    print(header)
    print("-" * 90)

    best_val_loss = float('inf')
    best_metrics = {}

    for epoch in range(1, args.epochs + 1):
        t_start = time.perf_counter()

        # Dynamic Teacher Forcing ratio for current epoch
        current_tf = get_scheduled_sampling_ratio(epoch, args.epochs, args.tf_start, args.tf_end)
        current_lr = optimizer.param_groups[0]['lr']

        # Training phase
        train_loss, train_metrics = train_one_epoch(
            model=model,
            loader=train_loader,
            criterion=criterion,
            optimizer=optimizer,
            device=device,
            tf_ratio=current_tf,
            clip_grad_norm=args.clip_grad
        )

        # Validation phase (pure autoregressive rollout)
        val_loss, val_metrics = evaluate(
            model=model,
            loader=val_loader,
            criterion=criterion,
            device=device,
            print_sample=True
        )

        scheduler.step()
        epoch_dur = time.perf_counter() - t_start

        # Log epoch summary
        log_line = (
            f"[{epoch:02d}/{args.epochs:02d}] | "
            f"{current_tf:^5.2f} | "
            f"{current_lr:^9.2e} | "
            f"{train_loss:^10.4f} | "
            f"{val_loss:^10.4f} | "
            f"{val_metrics['reach_error_px']:>9.1f} px   | "
            f"{val_metrics['action_acc']:>8.2f}%   | "
            f"{epoch_dur:>5.1f}s"
        )
        print(log_line)

        # Save best model checkpoint
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_metrics = val_metrics.copy()

            checkpoint = {
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'scheduler_state_dict': scheduler.state_dict(),
                'val_loss': val_loss,
                'val_metrics': val_metrics,
                'config': {
                    'noise_dim': args.noise_dim,
                    'hidden_dim': args.hidden_dim,
                    'cond_dim': args.cond_dim,
                    'seq_len': 256,
                    'num_layers': 2,
                    'num_classes': 4,
                    'max_step_delta': args.max_step_delta
                }
            }

            torch.save(checkpoint, args.save_path)

            # Also save legacy-compatible state dict
            if args.legacy_weights:
                torch.save({
                    'model_state_dict': model.state_dict(),
                    'epochs': epoch,
                    'val_loss': val_loss,
                    'val_target_dist_px': val_metrics['reach_error_px']
                }, args.legacy_weights)

    print("=" * 90)
    print("                      TRAINING PIPELINE FINISHED                       ")
    print("=" * 90)
    print(f" Best Validation Loss:        {best_val_loss:.4f}")
    print(f" Best Reach Error:           {best_metrics.get('reach_error_px', 0.0):.2f} px")
    print(f" Best Action Accuracy:       {best_metrics.get('action_acc', 0.0):.2f}%")
    print(f" Best Checkpoint Saved To:   {os.path.abspath(args.save_path)}")
    if args.legacy_weights:
        print(f" Weights File Saved To:      {os.path.abspath(args.legacy_weights)}")
    print("=" * 90)


if __name__ == '__main__':
    main()
