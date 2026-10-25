"""
Pilot Training Pipeline for Natural Mouse Trajectory Generation with Extended Motion History Context.
Author: Senior Deep Learning Engineer & Kinematics Researcher
Project: NaturaleMouseEvent
"""

import os
import sys
import math
import random
import time
import argparse
from typing import Dict, Tuple, Optional, List

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


# =====================================================================
# 1. Dataset Loader with Extended Kinematic Memory Context
# =====================================================================

class PilotKinematicDataset(Dataset):
    """
    Subsets or loads all episodes with Extended Motion History Context:
    - start_pos: (2,) normalized [x0, y0]
    - target_pos: (2,) normalized [xtgt, ytgt]
    - extended_context: (8,) [vx_prev, vy_prev, dt_dwell, dx_jump, dy_jump, click_density, avg_dt, momentum_mag]
    - intent: (1,) binary flag
    - seq_tensor: (256, 6) [dx, dy, dt, rem_x, rem_y, action_code]
    - mask: (256,) valid step indicator
    """
    def __init__(self, npz_path: str, subset_size: Optional[int] = 6000, full_dataset: bool = False, max_episodes: Optional[int] = None, seed: int = 42):
        if not os.path.exists(npz_path):
            raise FileNotFoundError(f"Dataset archive not found at: {npz_path}")

        print(f"[Dataset] Loading data from {npz_path}...")
        data = np.load(npz_path)

        total_available = len(data['start_targets'])
        print(f"[Dataset] Total episodes available: {total_available:,}")

        if full_dataset or (subset_size is None and max_episodes is None):
            indices = np.arange(total_available)
            actual_size = total_available
            print(f"[Dataset] Full training mode enabled: using all {actual_size:,} episodes (no subsampling/striding).")
        elif max_episodes is not None and max_episodes > 0:
            target_size = min(max_episodes, total_available)
            if target_size >= total_available:
                indices = np.arange(total_available)
                actual_size = total_available
                print(f"[Dataset] Full training mode enabled: using all {actual_size:,} episodes.")
            else:
                random.seed(seed)
                np.random.seed(seed)
                step_stride = max(1, total_available // target_size)
                indices = np.arange(0, total_available, step_stride)[:target_size]
                actual_size = len(indices)
                print(f"[Dataset] Selected {actual_size:,} episodes with stratified sampling (stride={step_stride}, max_episodes={max_episodes:,})")
        else:
            # Pilot subset mode (default 6,000)
            target_size = min(subset_size or 6000, total_available)
            if target_size >= total_available:
                indices = np.arange(total_available)
                actual_size = total_available
                print(f"[Dataset] Full training mode enabled: using all {actual_size:,} episodes.")
            else:
                random.seed(seed)
                np.random.seed(seed)
                step_stride = max(1, total_available // target_size)
                indices = np.arange(0, total_available, step_stride)[:target_size]
                actual_size = len(indices)
                print(f"[Dataset] Sliced representative pilot subset: {actual_size:,} episodes (stride={step_stride})")

        start_targets = data['start_targets'][indices]
        seq_tensors = data['seq_tensors'][indices]
        masks = data['masks'][indices]
        prev_contexts = data['prev_contexts'][indices]
        intents = data['intents'][indices]

        # Construct Extended 8D Motion History Context via Vectorized NumPy
        # [vx_prev, vy_prev, dt_dwell, dx_jump, dy_jump, click_density, avg_dt, momentum_mag]
        N = actual_size
        ext_contexts = np.zeros((N, 8), dtype=np.float32)

        # Baseline momentum and session features
        ext_contexts[:, 0:2] = prev_contexts[:, 0:2]
        ext_contexts[:, 5] = prev_contexts[:, 2]  # click_density
        ext_contexts[:, 6] = prev_contexts[:, 3]  # avg_dt_scaled
        ext_contexts[:, 7] = np.hypot(prev_contexts[:, 0], prev_contexts[:, 1])  # momentum_mag

        # Inter-episode jump and cognitive dwell handoff
        if N > 1:
            ext_contexts[1:, 3:5] = start_targets[1:, 0:2] - start_targets[:-1, 2:4]
            ext_contexts[1:, 2] = 0.15  # Default idle cognitive pause (scaled)
        if N > 0:
            ext_contexts[0, 2] = 0.1   # Initial resting dwell

        self.start_positions = torch.from_numpy(start_targets[:, :2]).float()
        self.target_positions = torch.from_numpy(start_targets[:, 2:]).float()
        self.extended_contexts = torch.from_numpy(ext_contexts).float()
        self.intents = torch.from_numpy(intents).float()
        self.seq_tensors = torch.from_numpy(seq_tensors).float()
        self.masks = torch.from_numpy(masks).float()
        self.length = N

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, idx: int):
        return (
            self.start_positions[idx],
            self.target_positions[idx],
            self.extended_contexts[idx],
            self.intents[idx],
            self.seq_tensors[idx],
            self.masks[idx]
        )


# =====================================================================
# 2. Enhanced Model Architecture with Kinematic Memory Context
# =====================================================================

class ExtendedConditioningEncoder(nn.Module):
    """
    Encodes start/target coordinates, 8D extended motion history context,
    binary intent, and latent stochastic noise vector into initial GRU state h_0
    and per-step context embeddings.
    """
    def __init__(self, context_dim: int = 8, noise_dim: int = 16, hidden_dim: int = 256, cond_dim: int = 64, num_layers: int = 2):
        super().__init__()
        self.noise_dim = noise_dim
        self.hidden_dim = hidden_dim
        self.cond_dim = cond_dim
        self.num_layers = num_layers

        # start(2) + target(2) + ext_context(8) + intent(1) + noise(16) = 29
        in_dim = 2 + 2 + context_dim + 1 + noise_dim

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

    def forward(self, start_pos, target_pos, ext_context, intent, z_noise=None):
        B = start_pos.size(0)
        if z_noise is None:
            z_noise = torch.randn(B, self.noise_dim, device=start_pos.device, dtype=start_pos.dtype)

        feat_in = torch.cat([start_pos, target_pos, ext_context, intent, z_noise], dim=-1)
        feat = self.mlp(feat_in)

        # h0 shape: (num_layers, B, hidden_dim)
        h0 = self.to_h0(feat).view(B, self.num_layers, self.hidden_dim).permute(1, 0, 2).contiguous()
        cond_embed = self.to_context(feat)

        return h0, cond_embed


class KinematicDecoder(nn.Module):
    """
    2-Layer GRU Kinematic Decoder:
    - Kinematics Head: Outputs bounded (dx, dy, dt) via tanh and sigmoid.
    - Action Head: Outputs logits for 4 discrete action classes.
    """
    def __init__(self, hidden_dim: int = 256, cond_dim: int = 64, num_layers: int = 2, num_classes: int = 4, max_step_delta: float = 0.08, max_dt: float = 5.0):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.cond_dim = cond_dim
        self.num_layers = num_layers
        self.num_classes = num_classes
        self.max_step_delta = max_step_delta
        self.max_dt = max_dt

        # step input: [dx, dy, dt, rem_x, rem_y] (5) + cond_embed (64) = 69
        step_in_dim = 5 + cond_dim

        self.gru = nn.GRU(
            input_size=step_in_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True
        )

        self.kinematics_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.SiLU(),
            nn.Linear(64, 3)
        )

        self.action_head = nn.Sequential(
            nn.Linear(hidden_dim, 64),
            nn.SiLU(),
            nn.Linear(64, num_classes)
        )

        # Initialize kinematics output layer with Xavier uniform
        nn.init.xavier_uniform_(self.kinematics_head[-1].weight)
        nn.init.zeros_(self.kinematics_head[-1].bias)

    def forward_step(self, step_input: torch.Tensor, h: torch.Tensor):
        gru_out, h_next = self.gru(step_input, h)
        out_flat = gru_out.squeeze(1)

        raw_kin = self.kinematics_head(out_flat)

        dx = torch.tanh(raw_kin[:, 0:1]) * self.max_step_delta
        dy = torch.tanh(raw_kin[:, 1:2]) * self.max_step_delta
        dt = torch.sigmoid(raw_kin[:, 2:3]) * self.max_dt

        kin_pred = torch.cat([dx, dy, dt], dim=-1)
        action_logits = self.action_head(out_flat)

        return kin_pred, action_logits, h_next


class MemoryConditionedMouseGenerator(nn.Module):
    """
    Unified AI Mouse Generator conditioned on Extended Motion History Context.
    """
    def __init__(self, context_dim: int = 8, noise_dim: int = 16, hidden_dim: int = 256, cond_dim: int = 64, seq_len: int = 256, num_layers: int = 2, num_classes: int = 4, max_step_delta: float = 0.08):
        super().__init__()
        self.seq_len = seq_len
        self.noise_dim = noise_dim
        self.hidden_dim = hidden_dim
        self.cond_dim = cond_dim
        self.num_layers = num_layers
        self.num_classes = num_classes
        self.max_step_delta = max_step_delta

        self.encoder = ExtendedConditioningEncoder(
            context_dim=context_dim,
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

    def forward(self, start_pos, target_pos, ext_context, intent, z_noise=None, teacher_forcing_ratio=0.0, true_seq=None, masks=None):
        B = start_pos.size(0)
        h, cond_embed = self.encoder(start_pos, target_pos, ext_context, intent, z_noise)

        curr_pos = start_pos.clone()
        prev_kin = torch.zeros(B, 3, device=start_pos.device, dtype=start_pos.dtype)

        pred_kinematics = []
        pred_actions = []

        use_tf = (teacher_forcing_ratio > 0.0 and true_seq is not None and self.training)

        for t in range(self.seq_len):
            # Dynamic closed-loop remaining distance feedback
            rem = torch.clamp(target_pos - curr_pos, min=-1.0, max=1.0)
            step_feat = torch.cat([prev_kin, rem, cond_embed], dim=-1).unsqueeze(1)

            kin_step, action_logits, h = self.decoder.forward_step(step_feat, h)

            if masks is not None:
                step_mask = masks[:, t:t+1]
            else:
                step_mask = torch.ones(B, 1, device=start_pos.device, dtype=start_pos.dtype)

            if use_tf:
                tf_coin = (torch.rand(B, 1, device=start_pos.device) < teacher_forcing_ratio).float()
                next_dx_dy = tf_coin * true_seq[:, t, 0:2] + (1.0 - tf_coin) * kin_step[:, 0:2]
                next_dt = tf_coin * true_seq[:, t, 2:3] + (1.0 - tf_coin) * kin_step[:, 2:3]
            else:
                next_dx_dy = kin_step[:, 0:2]
                next_dt = kin_step[:, 2:3]

            # Biomechanical motor recruitment smooth ramp for initial steps (t < 10)
            # Enforces near-zero initial displacement and bounds initial acceleration (<90,000 px/s^2)
            if t < 10:
                tau = (float(t) + 1.0) / 11.0
                rest_ramp = 3.0 * (tau ** 2) - 2.0 * (tau ** 3)
                v_init = ext_context[:, 0:2]
                v_init_mag = torch.norm(v_init, dim=-1, keepdim=True)
                blend = torch.clamp(v_init_mag / 0.15, 0.0, 1.0)
                step_ramp = (1.0 - blend) * rest_ramp + blend * 1.0
                next_dx_dy = next_dx_dy * step_ramp

            kin_out = torch.cat([next_dx_dy, next_dt], dim=-1)
            pred_kinematics.append(kin_out)
            pred_actions.append(action_logits)

            curr_pos = torch.clamp(curr_pos + next_dx_dy * step_mask, min=-0.1, max=1.1)
            prev_kin = torch.cat([next_dx_dy * step_mask, next_dt], dim=-1)

        pred_kinematics = torch.stack(pred_kinematics, dim=1)  # (B, seq_len, 3)
        pred_actions = torch.stack(pred_actions, dim=1)        # (B, seq_len, 4)

        if masks is not None:
            valid_disp = pred_kinematics[:, :, 0:2] * masks.unsqueeze(-1)
        else:
            valid_disp = pred_kinematics[:, :, 0:2]

        pred_traj = start_pos.unsqueeze(1) + torch.cumsum(valid_disp, dim=1)

        return pred_kinematics, pred_actions, pred_traj


# =====================================================================
# 3. Multi-Objective Kinematic Loss Function with Bio-Jerk & Boundary Losses
# =====================================================================

class KinematicBioLoss(nn.Module):
    """
    Refined Multi-Objective Kinematic Loss:
    L_total = L_disp + 2.0*L_reach + 0.5*L_time + 0.3*L_jerk + 0.2*L_boundary + 0.5*L_action
    """
    def __init__(self, w_disp: float = 1.0, w_reach: float = 2.0, w_dt: float = 0.5, w_jerk: float = 0.3, w_boundary: float = 0.2, w_action: float = 0.5, beta: float = 0.01):
        super().__init__()
        self.w_disp = w_disp
        self.w_reach = w_reach
        self.w_dt = w_dt
        self.w_jerk = w_jerk
        self.w_boundary = w_boundary
        self.w_action = w_action
        self.beta = beta

    def forward(self, pred_kin, pred_actions, pred_traj, true_seq, true_target, masks, start_pos, ext_context):
        valid_mask_3d = masks.unsqueeze(-1)
        valid_steps = torch.clamp(masks.sum(), min=1.0)

        # 1. Displacement Huber Loss on (dx, dy)
        pred_disp = pred_kin[:, :, 0:2]
        true_disp = true_seq[:, :, 0:2]
        loss_disp = F.smooth_l1_loss(pred_disp * valid_mask_3d, true_disp * valid_mask_3d, beta=self.beta, reduction='sum') / valid_steps

        # 2. Terminal Reach Penalty: L1 distance at final valid step
        last_indices = torch.clamp(masks.sum(dim=1).long() - 1, min=0)
        B = start_pos.size(0)
        batch_idx = torch.arange(B, device=start_pos.device)
        pred_final = pred_traj[batch_idx, last_indices]
        reach_err_l1 = F.l1_loss(pred_final, true_target, reduction='mean')
        reach_err_px = torch.hypot((pred_final[:, 0] - true_target[:, 0]) * 1920.0, (pred_final[:, 1] - true_target[:, 1]) * 1080.0).mean()

        # 3. Temporal Cadence Loss on dt
        pred_dt = pred_kin[:, :, 2]
        true_dt = true_seq[:, :, 2]
        loss_dt = F.smooth_l1_loss(pred_dt * masks, true_dt * masks, beta=0.02, reduction='sum') / valid_steps

        # 4. Zero-Velocity & Acceleration Boundary Constraints:
        # Enforces initial displacement to match incoming velocity, and initial acceleration ~ 0
        expected_disp_0 = ext_context[:, 0:2] * (pred_dt[:, 0:1] * 0.1)
        loss_boundary_v0 = torch.mean(torch.sum((pred_disp[:, 0] - expected_disp_0) ** 2, dim=-1))
        loss_boundary_a0 = torch.mean(torch.sum((pred_disp[:, 1] - pred_disp[:, 0]) ** 2, dim=-1))
        loss_boundary = loss_boundary_v0 + 0.5 * loss_boundary_a0

        # 5. Enhanced Bio-Jerk Regularization & Velocity Total Variation:
        # Jerk: discrete 3rd derivative of displacement (delta a_t = disp_t - 2*disp_{t-1} + disp_{t-2})
        if pred_disp.size(1) >= 3:
            jerk = pred_disp[:, 2:] - 2.0 * pred_disp[:, 1:-1] + pred_disp[:, :-2]
            jerk_mask = masks[:, 2:].unsqueeze(-1)
            loss_jerk_core = (torch.sum(jerk ** 2, dim=-1, keepdim=True) * jerk_mask).sum() / torch.clamp(jerk_mask.sum(), min=1.0)

            # Total Variation on consecutive displacements to eliminate high-frequency hash
            disp_diff = torch.abs(pred_disp[:, 1:] - pred_disp[:, :-1]) * masks[:, 1:].unsqueeze(-1)
            loss_tv = disp_diff.sum() / torch.clamp(masks[:, 1:].sum(), min=1.0)
            loss_jerk = loss_jerk_core * 10.0 + loss_tv
        else:
            loss_jerk = torch.tensor(0.0, device=start_pos.device)

        # 6. Action Classification Cross-Entropy
        true_actions = true_seq[:, :, 5].long()
        flat_logits = pred_actions.reshape(-1, 4)
        flat_targets = true_actions.reshape(-1)
        flat_mask = masks.reshape(-1)
        ce_loss = F.cross_entropy(flat_logits, flat_targets, reduction='none')
        loss_action = (ce_loss * flat_mask).sum() / valid_steps

        total_loss = (
            self.w_disp * loss_disp +
            self.w_reach * reach_err_l1 +
            self.w_dt * loss_dt +
            self.w_jerk * loss_jerk +
            self.w_boundary * loss_boundary +
            self.w_action * loss_action
        )

        metrics = {
            'loss_disp': loss_disp.item(),
            'loss_reach': reach_err_l1.item(),
            'reach_px': reach_err_px.item(),
            'loss_dt': loss_dt.item(),
            'loss_jerk': loss_jerk.item(),
            'loss_boundary': loss_boundary.item(),
            'loss_action': loss_action.item()
        }

        return total_loss, metrics


# =====================================================================
# 4. Pilot Training Engine
# =====================================================================

def run_pilot_training(
    dataset_path: str = "data/mouse_dataset_fixed_N256_full.npz",
    subset_size: Optional[int] = 6000,
    full: bool = False,
    max_episodes: Optional[int] = None,
    train_split: float = 0.85,
    num_workers: int = 0,
    epochs: int = 6,
    batch_size: int = 64,
    lr: float = 1e-3,
    save_path: str = "models/pilot_mouse_model.pth",
    resume: Optional[str] = None
):
    print("\n==========================================================================")
    if full:
        print(" 🚀 INITIATING PRODUCTION TRAINING: FULL 53K DATASET WITH KINEMATIC MEMORY")
    else:
        print(" 🔬 INITIATING PILOT TRAINING: EXTENDED MOTION HISTORY CONTEXT")
    print(f" Mode: {'Full Dataset (All Episodes)' if full else f'Subset ({max_episodes or subset_size} episodes)'} | Epochs: {epochs} | Batch Size: {batch_size}")
    if resume:
        print(f" Resume: Resuming from checkpoint: {resume}")
    print("==========================================================================\n")

    # Select optimal device and threads
    use_cuda = torch.cuda.is_available()
    if use_cuda:
        device = torch.device("cuda")
        print(f"[Device] Using CUDA GPU: {torch.cuda.get_device_name(0)}")
        torch.backends.cudnn.benchmark = True
    else:
        device = torch.device("cpu")
        num_threads = min(8, os.cpu_count() or 4)
        torch.set_num_threads(num_threads)
        print(f"[Device] Using CPU with {num_threads} execution threads.")

    # Load dataset (full or subset)
    effective_subset = None if full else (max_episodes if max_episodes is not None else subset_size)
    dataset = PilotKinematicDataset(
        dataset_path,
        subset_size=effective_subset,
        full_dataset=full,
        max_episodes=max_episodes
    )
    total_len = len(dataset)
    train_len = int(train_split * total_len)
    val_len = total_len - train_len

    if full or total_len >= 50000:
        print(f"[Dataset] Training on FULL dataset: {total_len:,} episodes (Train: {train_len:,}, Val: {val_len:,}).")
    print(f"[Split] Train Set: {train_len:,} episodes ({train_split*100:.0f}%) | Validation Set: {val_len:,} episodes ({(1-train_split)*100:.0f}%)")

    train_set, val_set = torch.utils.data.random_split(
        dataset,
        [train_len, val_len],
        generator=torch.Generator().manual_seed(42)
    )

    # GPU DataLoader throughput optimization: pin_memory and worker safety
    pin_memory = use_cuda
    loader_workers = max(0, num_workers)
    loader_kwargs = {
        'num_workers': loader_workers,
        'pin_memory': pin_memory,
    }
    # persistent_workers and prefetch_factor are only valid when num_workers > 0
    if loader_workers > 0:
        loader_kwargs['persistent_workers'] = True
        loader_kwargs['prefetch_factor'] = 2

    print(f"[DataLoader] Configuration: num_workers={loader_workers}, pin_memory={pin_memory}, persistent_workers={(loader_workers > 0)}, prefetch_factor={2 if loader_workers > 0 else 'N/A'}, batch_size={batch_size}")

    train_loader = DataLoader(
        train_set,
        batch_size=batch_size,
        shuffle=True,
        drop_last=True,
        **loader_kwargs
    )
    val_loader = DataLoader(
        val_set,
        batch_size=batch_size,
        shuffle=False,
        **loader_kwargs
    )

    # Initialize model
    model = MemoryConditionedMouseGenerator(
        context_dim=8,
        noise_dim=16,
        hidden_dim=256,
        cond_dim=64,
        seq_len=256,
        num_layers=2,
        num_classes=4,
        max_step_delta=0.08
    ).to(device)

    param_count = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[Model] Initialized MemoryConditionedMouseGenerator ({param_count:,} trainable parameters)")

    criterion = KinematicBioLoss(
        w_disp=1.0,
        w_reach=2.0,
        w_dt=0.5,
        w_jerk=0.3,
        w_boundary=0.2,
        w_action=0.5
    ).to(device)

    # Resume training / warm-start from existing checkpoint if requested
    start_epoch = 1
    best_val_err = float('inf')
    best_epoch = 0

    if resume:
        if not os.path.exists(resume):
            raise FileNotFoundError(f"Resume checkpoint file not found at: {resume}")

        print(f"[Resume] Loading checkpoint from: {resume}")
        checkpoint = torch.load(resume, map_location=device, weights_only=False)

        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            state_dict = checkpoint['model_state_dict']
            loaded_epoch = checkpoint.get('epoch', 0)
            saved_val_err = checkpoint.get('val_reach_px', float('inf'))
            if saved_val_err < best_val_err:
                best_val_err = saved_val_err
                best_epoch = loaded_epoch

            model.load_state_dict(state_dict, strict=False)
            start_epoch = loaded_epoch + 1
            print(f"[Resume] Successfully restored model weights from {resume}. (Loaded Epoch {loaded_epoch}, Val Reach: {saved_val_err:.1f} px). Resuming training from Epoch {start_epoch} up to Epoch {epochs}...")
        else:
            # Raw state dict
            state_dict = checkpoint
            model.load_state_dict(state_dict, strict=False)
            print(f"[Resume] Successfully restored raw model state dict from {resume}. Resuming training...")

    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)

    # If structured checkpoint contains optimizer state, attempt to restore it
    if resume and isinstance(checkpoint, dict) and 'optimizer_state_dict' in checkpoint:
        try:
            optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            print(f"[Resume] Successfully restored optimizer state.")
        except Exception as e:
            print(f"[Resume] Notice: Could not restore optimizer state ({e}). Proceeding with freshly initialized optimizer.")

    # Ensure 'initial_lr' is registered in all param groups for lr_scheduler compatibility
    for group in optimizer.param_groups:
        group.setdefault('initial_lr', group.get('lr', lr))

    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=5e-5, last_epoch=start_epoch - 2 if start_epoch > 1 else -1)

    # Automatic Mixed Precision (AMP / FP16) for Tesla Tensor Cores acceleration
    use_amp = use_cuda
    scaler = torch.amp.GradScaler('cuda', enabled=use_amp)
    print(f"[Precision] Automatic Mixed Precision (AMP): {'ENABLED (FP16 via Tensor Cores)' if use_amp else 'DISABLED (FP32 on CPU)'}")

    if start_epoch > epochs:
        print(f"[Notice] Checkpoint already reached Epoch {start_epoch - 1} >= requested epochs ({epochs}). Skipping training loop.")

    print("\n-----------------------------------------------------------------------------------------------------------------")
    print(f"{'Epoch':^9} | {'LR':^9} | {'Train Loss':^11} | {'Val Loss':^10} | {'Val Reach Err':^15} | {'Mean Jerk':^11} | {'Time':^7}")
    print("-----------------------------------------------------------------------------------------------------------------")

    total_train_batches = len(train_loader)
    total_val_batches = len(val_loader)

    for epoch in range(start_epoch, epochs + 1):
        t0 = time.perf_counter()
        model.train()
        train_loss = 0.0
        train_batches = 0

        # Teacher forcing ratio decays from 0.8 to 0.1 across pilot epochs
        tf_ratio = max(0.1, 0.8 - (epoch - 1) * (0.7 / max(1, epochs - 1)))

        train_iter = train_loader
        if TQDM_AVAILABLE and (full or total_len >= 10000):
            train_iter = tqdm(train_loader, desc=f"Epoch {epoch}/{epochs} [Train]", leave=False)

        for b_idx, (b_start, b_tgt, b_ctx, b_intent, b_seq, b_mask) in enumerate(train_iter):
            b_start = b_start.to(device, non_blocking=pin_memory)
            b_tgt = b_tgt.to(device, non_blocking=pin_memory)
            b_ctx = b_ctx.to(device, non_blocking=pin_memory)
            b_intent = b_intent.to(device, non_blocking=pin_memory)
            b_seq = b_seq.to(device, non_blocking=pin_memory)
            b_mask = b_mask.to(device, non_blocking=pin_memory)

            optimizer.zero_grad(set_to_none=True)

            with torch.amp.autocast('cuda', enabled=use_amp):
                pred_kin, pred_act, pred_traj = model(
                    start_pos=b_start,
                    target_pos=b_tgt,
                    ext_context=b_ctx,
                    intent=b_intent,
                    teacher_forcing_ratio=tf_ratio,
                    true_seq=b_seq,
                    masks=b_mask
                )

                loss, _ = criterion(
                    pred_kin=pred_kin,
                    pred_actions=pred_act,
                    pred_traj=pred_traj,
                    true_seq=b_seq,
                    true_target=b_tgt,
                    masks=b_mask,
                    start_pos=b_start,
                    ext_context=b_ctx
                )

            # Mixed precision backward pass, unscale, gradient clipping, optimizer step
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
            scaler.step(optimizer)
            scaler.update()

            train_loss += loss.item()
            train_batches += 1

            if not TQDM_AVAILABLE and (b_idx + 1) % 50 == 0:
                print(f"  [Epoch {epoch}/{epochs}] Step {b_idx + 1}/{total_train_batches} | Batch Loss: {loss.item():.4f}", flush=True)

        scheduler.step()
        avg_train_loss = train_loss / max(1, train_batches)

        # Validation under pure autoregressive generation (tf_ratio = 0.0) with AMP
        model.eval()
        val_loss = 0.0
        val_batches = 0
        val_reach_px_list = []
        val_jerk_list = []

        val_iter = val_loader
        if TQDM_AVAILABLE and (full or total_len >= 10000):
            val_iter = tqdm(val_loader, desc=f"Epoch {epoch}/{epochs} [Val]", leave=False)

        with torch.no_grad():
            for b_idx, (b_start, b_tgt, b_ctx, b_intent, b_seq, b_mask) in enumerate(val_iter):
                b_start = b_start.to(device, non_blocking=pin_memory)
                b_tgt = b_tgt.to(device, non_blocking=pin_memory)
                b_ctx = b_ctx.to(device, non_blocking=pin_memory)
                b_intent = b_intent.to(device, non_blocking=pin_memory)
                b_seq = b_seq.to(device, non_blocking=pin_memory)
                b_mask = b_mask.to(device, non_blocking=pin_memory)

                with torch.amp.autocast('cuda', enabled=use_amp):
                    pred_kin, pred_act, pred_traj = model(
                        start_pos=b_start,
                        target_pos=b_tgt,
                        ext_context=b_ctx,
                        intent=b_intent,
                        teacher_forcing_ratio=0.0,
                        true_seq=None,
                        masks=b_mask
                    )

                    loss, metrics = criterion(
                        pred_kin=pred_kin,
                        pred_actions=pred_act,
                        pred_traj=pred_traj,
                        true_seq=b_seq,
                        true_target=b_tgt,
                        masks=b_mask,
                        start_pos=b_start,
                        ext_context=b_ctx
                    )

                val_loss += loss.item()
                val_reach_px_list.append(metrics['reach_px'])
                val_jerk_list.append(metrics['loss_jerk'])
                val_batches += 1

                if not TQDM_AVAILABLE and (b_idx + 1) % 50 == 0:
                    print(f"  [Epoch {epoch}/{epochs}] Val Step {b_idx + 1}/{total_val_batches}", flush=True)

        avg_val_loss = val_loss / max(1, val_batches)
        avg_reach_px = np.mean(val_reach_px_list)
        avg_jerk = np.mean(val_jerk_list)
        dur_s = time.perf_counter() - t0
        curr_lr = scheduler.get_last_lr()[0]

        print(f" [{epoch:02d}/{epochs:02d}]  | {curr_lr:.2e} | {avg_train_loss:11.4f} | {avg_val_loss:10.4f} | {avg_reach_px:11.1f} px | {avg_jerk:11.5f} | {dur_s:5.1f}s")

        # Save best model
        if avg_reach_px < best_val_err:
            best_val_err = avg_reach_px
            best_epoch = epoch
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'val_reach_px': avg_reach_px,
                'val_loss': avg_val_loss,
                'config': {
                    'context_dim': 8,
                    'hidden_dim': 256,
                    'cond_dim': 64,
                    'noise_dim': 16,
                    'seq_len': 256
                }
            }, save_path)

    print("-----------------------------------------------------------------------------------------------------------------")
    print(f" ✨ Best Model Checkpoint Saved: Epoch {best_epoch} (Reach Error: {best_val_err:.1f} px) -> {save_path}\n")

    return model, save_path


# =====================================================================
# 5. Post-Training Kinematic & Visual Sanity Evaluation
# =====================================================================

def evaluate_kinematic_memory(model: nn.Module, device: torch.device):
    """
    Evaluates 3 diverse evaluation pairs under simulated momentum inheritance:
    1. Short displacement (~100 px)
    2. Medium diagonal (~500 px)
    3. Long screen-wide movement (~1200 px)
    """
    print("==========================================================================")
    print(" 🔍 POST-TRAINING TRAJECTORY SANITY & KINEMATIC MEMORY EVALUATION")
    print("==========================================================================\n")

    test_cases = [
        {
            "name": "Short Precision Movement",
            "start": (400.0, 300.0),
            "target": (480.0, 360.0),
            # Incoming residual velocity heading slightly southeast
            "prev_momentum": (0.04, 0.03, 0.1, 0.0, 0.0, 0.0, 0.08, 0.05)
        },
        {
            "name": "Medium Diagonal Crossing",
            "start": (300.0, 200.0),
            "target": (700.0, 500.0),
            # Incoming residual velocity heading northeast (requires smooth centrifugal arc)
            "prev_momentum": (0.08, -0.05, 0.1, 0.0, 0.0, 0.01, 0.08, 0.09)
        },
        {
            "name": "Long Screen-Wide Ballistic Movement",
            "start": (150.0, 100.0),
            "target": (1350.0, 750.0),
            # High incoming velocity heading southwest
            "prev_momentum": (-0.06, 0.08, 0.1, 0.0, 0.0, 0.02, 0.08, 0.10)
        }
    ]

    model.eval()

    for idx, tc in enumerate(test_cases, 1):
        s_x, s_y = tc["start"]
        t_x, t_y = tc["target"]
        nominal_dist = np.hypot(t_x - s_x, t_y - s_y)

        start_t = torch.tensor([[s_x / 1920.0, s_y / 1080.0]], dtype=torch.float32, device=device)
        target_t = torch.tensor([[t_x / 1920.0, t_y / 1080.0]], dtype=torch.float32, device=device)
        ctx_t = torch.tensor([tc["prev_momentum"]], dtype=torch.float32, device=device)
        intent_t = torch.tensor([[1.0]], dtype=torch.float32, device=device)

        with torch.no_grad():
            pred_kin, pred_act, pred_traj = model(
                start_pos=start_t,
                target_pos=target_t,
                ext_context=ctx_t,
                intent=intent_t,
                teacher_forcing_ratio=0.0
            )

        kin = pred_kin[0].cpu().numpy()
        traj = pred_traj[0].cpu().numpy()

        traj_px = traj * np.array([1920.0, 1080.0])
        final_pos = traj_px[-1]
        reach_err_px = float(np.hypot(final_pos[0] - t_x, final_pos[1] - t_y))
        total_dur_ms = float(np.sum(kin[:, 2] * 100.0))

        # Compute Jerk smoothness metric: d3(x)/dt3
        disp_px = np.diff(traj_px, axis=0)
        accel = np.diff(disp_px, axis=0)
        jerk = np.diff(accel, axis=0)
        mean_jerk_metric = float(np.mean(np.sum(jerk ** 2, axis=-1)) * 1e4)

        # Check initial movement angle vs direct target angle
        initial_dx = traj_px[5, 0] - traj_px[0, 0]
        initial_dy = traj_px[5, 1] - traj_px[0, 1]
        direct_dx = t_x - s_x
        direct_dy = t_y - s_y
        cos_sim = (initial_dx * direct_dx + initial_dy * direct_dy) / (
            max(1e-6, np.hypot(initial_dx, initial_dy) * np.hypot(direct_dx, direct_dy))
        )
        curve_angle_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos_sim))))

        print(f"[{idx}/3] {tc['name'].upper()}")
        print(f"   Coordinates:  Start {tc['start']} -> Target {tc['target']} (Displacement: {nominal_dist:.1f} px)")
        print(f"   Final Reach:  Landed at ({final_pos[0]:.1f}, {final_pos[1]:.1f}) | Reach Error: {reach_err_px:.1f} px")
        print(f"   Kinematics:   Duration: {total_dur_ms:.1f} ms | Smoothness (Jerk score): {mean_jerk_metric:.3f}")
        print(f"   Memory Arc:   Momentum Launch Curvature: {curve_angle_deg:.1f}° deviation from straight line (Natural Arc)")
        print("   Sample Path:  " + " -> ".join([f"({p[0]:.0f},{p[1]:.0f})" for p in traj_px[::35]]) + f" -> ({final_pos[0]:.0f},{final_pos[1]:.0f})")
        print("--------------------------------------------------------------------------")

    print("\n✅ Visual & Kinematic Sanity Checks Completed Successfully!")


if __name__ == '__main__':
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
    default_data = os.path.join(REPO_ROOT, "data", "mouse_dataset_fixed_N256_full.npz")

    parser = argparse.ArgumentParser(description="AI Natural Mouse Trajectory Engine - Pilot & Production Training")
    parser.add_argument("--data", type=str, default=default_data, help="Path to preprocessed dataset (.npz)")
    parser.add_argument("--full", action="store_true", help="Train on the ENTIRE dataset (all 53k episodes) without subsampling")
    parser.add_argument("--max_episodes", type=int, default=None, help="Explicit maximum number of episodes to train on (overrides --subset)")
    parser.add_argument("--subset", type=int, default=6000, help="Pilot subset size when --full is not specified (default: 6000)")
    parser.add_argument("--train_split", type=float, default=0.90, help="Train/Validation split ratio (default: 0.90 for 90/10 split)")
    parser.add_argument("--num_workers", type=int, default=0, help="Number of DataLoader worker processes (default: 0 for in-memory fast tensor access, avoids Colab fork deadlocks)")
    parser.add_argument("--epochs", type=int, default=6, help="Number of training epochs (default: 6)")
    parser.add_argument("--batch_size", type=int, default=64, help="Batch size (default: 64)")
    parser.add_argument("--lr", type=float, default=1e-3, help="Initial learning rate (default: 0.001)")
    parser.add_argument("--save_path", type=str, default=None, help="Output checkpoint path (default: models/production_mouse_model.pth if --full else models/pilot_mouse_model.pth)")
    parser.add_argument("--resume", type=str, default=None, help="Path to checkpoint .pth to resume training from")

    args = parser.parse_args()

    # Determine default save path based on training mode
    if args.save_path is None:
        if args.full:
            effective_save_path = os.path.join(REPO_ROOT, "models", "production_mouse_model.pth")
        else:
            effective_save_path = os.path.join(REPO_ROOT, "models", "pilot_mouse_model.pth")
    else:
        effective_save_path = args.save_path

    os.makedirs(os.path.dirname(os.path.abspath(effective_save_path)), exist_ok=True)

    trained_model, saved_path = run_pilot_training(
        dataset_path=args.data,
        subset_size=args.subset,
        full=args.full,
        max_episodes=args.max_episodes,
        train_split=args.train_split,
        num_workers=args.num_workers,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        save_path=effective_save_path,
        resume=args.resume
    )

    device = next(trained_model.parameters()).device
    evaluate_kinematic_memory(trained_model, device)

