import time
import os
import sys
import math
import numpy as np
import torch
import torch.nn as nn
import random

try:
    from scipy.signal import savgol_filter
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
WINMM_AVAILABLE = False
USER32_AVAILABLE = False
winmm = None
user32 = None

if os.name == 'nt':
    import ctypes
    try:
        winmm = ctypes.WinDLL('winmm')
        WINMM_AVAILABLE = True
    except Exception:
        winmm = None
    try:
        user32 = ctypes.windll.user32
        USER32_AVAILABLE = True
    except Exception:
        user32 = None

# Enable UTF-8 console output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import pyautogui
    pyautogui.PAUSE = 0.0
    PYAUTOGUI_AVAILABLE = True
except Exception:
    PYAUTOGUI_AVAILABLE = False
    print("[HumanMouse] Notice: 'pyautogui' is not installed or display server unavailable. Running in dry-run mode (simulation only).")

# =====================================================================
# PyTorch Neural Network Architecture Definitions
# =====================================================================
# PyTorch Neural Network Architecture Definitions
# =====================================================================

class ExtendedConditioningEncoder(nn.Module):
    """
    Encodes start/target coordinates, motion history context (8D or 4D),
    binary intent, and latent stochastic noise vector into initial GRU state h_0
    and per-step context embeddings.
    """
    def __init__(self, context_dim=8, noise_dim=16, hidden_dim=256, cond_dim=64, num_layers=2):
        super(ExtendedConditioningEncoder, self).__init__()
        self.context_dim = context_dim
        self.noise_dim = noise_dim
        self.hidden_dim = hidden_dim
        self.cond_dim = cond_dim
        self.num_layers = num_layers

        # start(2) + target(2) + ext_context(context_dim) + intent(1) + noise(16)
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

        h0 = self.to_h0(feat).view(B, self.num_layers, self.hidden_dim).permute(1, 0, 2).contiguous()
        cond_embed = self.to_context(feat)

        return h0, cond_embed


# Backward compatibility alias
ConditioningEncoder = ExtendedConditioningEncoder


class KinematicDecoder(nn.Module):
    def __init__(self, hidden_dim=256, cond_dim=64, num_layers=2, num_classes=4, max_step_delta=0.08, max_dt=5.0):
        super(KinematicDecoder, self).__init__()
        self.hidden_dim = hidden_dim
        self.cond_dim = cond_dim
        self.num_layers = num_layers
        self.num_classes = num_classes
        self.max_step_delta = max_step_delta
        self.max_dt = max_dt

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

    def forward_step(self, step_input, h):
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
    def __init__(self, context_dim=8, noise_dim=16, hidden_dim=256, cond_dim=64, seq_len=256, num_layers=2, num_classes=4, max_step_delta=0.08):
        super(MemoryConditionedMouseGenerator, self).__init__()
        self.context_dim = context_dim
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

    def forward(self, start_pos, target_pos, ext_context, intent, z_noise=None, teacher_forcing_ratio=0.0, true_seq=None, padding_masks=None):
        B = start_pos.size(0)
        h, cond_embed = self.encoder(start_pos, target_pos, ext_context, intent, z_noise)

        curr_pos = start_pos.clone()
        prev_kin = torch.zeros(B, 3, device=start_pos.device, dtype=start_pos.dtype)

        pred_kinematics = []
        pred_actions = []
        pred_traj = []

        for t in range(self.seq_len):
            rem = torch.clamp(target_pos - curr_pos, min=-1.0, max=1.0)
            step_feat = torch.cat([prev_kin, rem, cond_embed], dim=-1).unsqueeze(1)

            kin_step, action_logits, h = self.decoder.forward_step(step_feat, h)

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

            curr_pos = torch.clamp(curr_pos + next_dx_dy, min=-0.1, max=1.1)
            prev_kin = kin_out

            pred_traj.append(curr_pos)

        pred_kinematics = torch.stack(pred_kinematics, dim=1)
        pred_actions = torch.stack(pred_actions, dim=1)
        pred_traj = torch.stack(pred_traj, dim=1)

        return pred_kinematics, pred_actions, pred_traj


# Backward compatibility alias
HumanMouseGenerator = MemoryConditionedMouseGenerator


# =====================================================================
# Target Sampling & Biometric Dispersion Utilities
# =====================================================================

def sample_target_within_box(box_bounds, sigma_scale=6.0, margin=2.0):
    """
    Samples an authentic human landing coordinate within a rectangular UI target bounding box.
    Uses a truncated 2D Gaussian centered on the bounding box center:
      sigma_x = width / sigma_scale (default w / 6, spanning ~99.7% of natural human dispersion within box)
      sigma_y = height / sigma_scale (default h / 6)
    Coordinates are strictly clamped within the box boundaries minus safety margin.

    Args:
        box_bounds (tuple or dict): (x, y, w, h) or dict with keys 'x', 'y', 'w', 'h'
        sigma_scale (float): Divisor for Gaussian standard deviation (default 6.0)
        margin (float): Safety padding from the box edge in pixels

    Returns:
        tuple: (target_x, target_y) as floats
    """
    if isinstance(box_bounds, dict):
        bx = float(box_bounds.get('x', box_bounds.get('left', 0.0)))
        by = float(box_bounds.get('y', box_bounds.get('top', 0.0)))
        bw = float(box_bounds.get('w', box_bounds.get('width', 10.0)))
        bh = float(box_bounds.get('h', box_bounds.get('height', 10.0)))
    else:
        bx, by, bw, bh = [float(v) for v in box_bounds]

    center_x = bx + bw / 2.0
    center_y = by + bh / 2.0

    sigma_x = max(1.0, bw / float(sigma_scale))
    sigma_y = max(1.0, bh / float(sigma_scale))

    offset_x = float(np.random.normal(0.0, sigma_x))
    offset_y = float(np.random.normal(0.0, sigma_y))

    min_x = bx + margin
    max_x = bx + max(margin, bw - margin)
    min_y = by + margin
    max_y = by + max(margin, bh - margin)

    sample_x = max(min_x, min(max_x, center_x + offset_x))
    sample_y = max(min_y, min(max_y, center_y + offset_y))

    return (float(sample_x), float(sample_y))


# =====================================================================
# Trajectory Simulation Engine
# =====================================================================

class HumanMouseSimulator:
    def __init__(self, model_path=None, display_w=1920, display_h=1080):
        self.display_w = float(display_w)
        self.display_h = float(display_h)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.context_dim = 8

        # Dynamic model checkpoint discovery with priority order:
        # 1. User-supplied model_path
        # 2. models/pilot_mouse_model.pth (trained extended-context model)
        # 3. best_model.pth
        # 4. human_mouse_model.pt
        resolved_path = None
        script_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(script_dir)

        candidate_paths = []
        if model_path:
            candidate_paths.extend([
                model_path,
                os.path.join(script_dir, model_path),
                os.path.join(parent_dir, model_path)
            ])
        candidate_paths.extend([
            "models/production_mouse_model.pth",
            os.path.join(parent_dir, "models", "production_mouse_model.pth"),
            os.path.join(script_dir, "models", "production_mouse_model.pth"),
            "models/pilot_mouse_model.pth",
            os.path.join(parent_dir, "models", "pilot_mouse_model.pth"),
            os.path.join(script_dir, "models", "pilot_mouse_model.pth"),
            "models/best_model.pth",
            os.path.join(parent_dir, "models", "best_model.pth"),
            "models/human_mouse_model.pt",
            os.path.join(parent_dir, "models", "human_mouse_model.pt"),
            os.path.join(script_dir, "human_mouse_model.pt"),
            os.path.join(script_dir, "human_mouse_engine", "human_mouse_model.pt")
        ])

        for p in candidate_paths:
            if p and os.path.exists(p):
                resolved_path = os.path.abspath(p)
                break

        if resolved_path:
            checkpoint = torch.load(resolved_path, map_location=self.device, weights_only=False)

            # Auto-detect context dimension from checkpoint config or weight shapes
            detected_context_dim = 8
            if isinstance(checkpoint, dict) and 'config' in checkpoint:
                detected_context_dim = checkpoint['config'].get('context_dim', 8)
            elif isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                state = checkpoint['model_state_dict']
                if 'encoder.mlp.0.weight' in state:
                    detected_context_dim = state['encoder.mlp.0.weight'].shape[1] - 21
            elif isinstance(checkpoint, dict) and 'encoder.mlp.0.weight' in checkpoint:
                detected_context_dim = checkpoint['encoder.mlp.0.weight'].shape[1] - 21

            self.context_dim = max(4, detected_context_dim)
            self.model = MemoryConditionedMouseGenerator(
                context_dim=self.context_dim,
                noise_dim=16,
                hidden_dim=256,
                cond_dim=64,
                seq_len=256,
                num_layers=2,
                num_classes=4,
                max_step_delta=0.08
            ).to(self.device)

            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                self.model.load_state_dict(checkpoint['model_state_dict'])
            else:
                self.model.load_state_dict(checkpoint)

            print(f"[HumanMouse] Loaded trained AI mouse model from: {resolved_path} (context_dim={self.context_dim})")
        else:
            self.context_dim = 8
            self.model = MemoryConditionedMouseGenerator(
                context_dim=8,
                noise_dim=16,
                hidden_dim=256,
                cond_dim=64,
                seq_len=256,
                num_layers=2,
                num_classes=4,
                max_step_delta=0.08
            ).to(self.device)
            print(f"[HumanMouse] Warning: Model file {model_path} not found. Using untrained weights.")

        self.model.eval()

    def generate_trajectory(self, start_pos, target_pos, prev_context=None, intent=1.0, target_radius=5.0):
        """
        Generates realistic human mouse trajectory from start_pos to target_pos
        conditioned on continuous kinematic memory context.
        
        Args:
            start_pos: Tuple (x, y) in screen coordinates.
            target_pos: Tuple (x, y) in screen coordinates.
            prev_context: Optional context tuple (8D or 4D) carrying residual momentum.
            intent: 1.0 for targeted movement/click, 0.0 for idle wandering.
            target_radius: Acceptable distance threshold (in px) to consider target reached.
            
        Returns:
            List of dict steps: [{'x': int, 'y': int, 'dt_ms': float, 'type': str}]
        """
        start_x, start_y = float(start_pos[0]), float(start_pos[1])
        target_x, target_y = float(target_pos[0]), float(target_pos[1])

        # If already at destination within target tolerance, return stationary point
        init_dist = np.hypot(target_x - start_x, target_y - start_y)
        if init_dist <= target_radius and intent > 0.5:
            return [{
                "x": int(round(start_x)),
                "y": int(round(start_y)),
                "dt_ms": 0.0,
                "type": "move"
            }]

        sx_norm = start_x / self.display_w
        sy_norm = start_y / self.display_h
        tx_norm = target_x / self.display_w
        ty_norm = target_y / self.display_h

        start_t = torch.tensor([[sx_norm, sy_norm]], dtype=torch.float32, device=self.device)
        target_t = torch.tensor([[tx_norm, ty_norm]], dtype=torch.float32, device=self.device)
        intent_t = torch.tensor([[intent]], dtype=torch.float32, device=self.device)

        # Context alignment across 8D and 4D representations
        if prev_context is None:
            if self.context_dim == 8:
                ctx_arr = [0.0, 0.0, 0.1, 0.0, 0.0, 0.0, 0.1, 0.0]
            else:
                ctx_arr = [0.0, 0.0, 0.0, 0.1]
        elif len(prev_context) == 4 and self.context_dim == 8:
            vx0, vy0, clicks, avg_dt = prev_context
            mag = float(np.hypot(vx0, vy0))
            ctx_arr = [float(vx0), float(vy0), 0.1, 0.0, 0.0, float(clicks), float(avg_dt), mag]
        elif len(prev_context) == 8 and self.context_dim == 4:
            ctx_arr = [float(prev_context[0]), float(prev_context[1]), float(prev_context[5]), float(prev_context[6])]
        elif len(prev_context) == self.context_dim:
            ctx_arr = [float(c) for c in prev_context]
        else:
            ctx_arr = [float(c) for c in list(prev_context)[:self.context_dim]]

        # Directional Momentum Gating (Anti-Kink / No Backtracking):
        # Prevent acute retrograde hooks when incoming velocity opposes target direction (angle >= 90 deg)
        dx_tgt = target_x - start_x
        dy_tgt = target_y - start_y
        dist_tgt = math.hypot(dx_tgt, dy_tgt)

        vx_residual = float(ctx_arr[0] * self.display_w)
        vy_residual = float(ctx_arr[1] * self.display_h)
        v_residual_mag = float(math.hypot(vx_residual, vy_residual))
        vx_gated = vx_residual
        vy_gated = vy_residual

        if dist_tgt > 1e-3 and v_residual_mag > 1e-3:
            u_x = dx_tgt / dist_tgt
            u_y = dy_tgt / dist_tgt

            # Dot product / projection onto target vector
            v_parallel = vx_residual * u_x + vy_residual * u_y
            cos_sim = v_parallel / v_residual_mag

            # Decompose into parallel and perpendicular (normal/tangential) components
            v_para_x = v_parallel * u_x
            v_para_y = v_parallel * u_y
            v_perp_x = vx_residual - v_para_x
            v_perp_y = vy_residual - v_para_y

            if cos_sim <= 0.0:
                # Opposing momentum (angle >= 90 deg):
                # Suppress retrograde component so momentum does not project backward into negative progress.
                # Retain only the perpendicular (tangential) component with graceful turning decay.
                turn_damping = max(0.0, float(1.0 + cos_sim) ** 1.5)
                vx_gated = v_perp_x * turn_damping
                vy_gated = v_perp_y * turn_damping
            else:
                # Aligned momentum (acute angle < 90 deg):
                # Retain forward and tangential components for fluid Bezier-like corner rounding
                vx_gated = vx_residual
                vy_gated = vy_residual

            ctx_arr[0] = float(vx_gated / self.display_w)
            ctx_arr[1] = float(vy_gated / self.display_h)
            if self.context_dim == 8:
                ctx_arr[7] = float(math.hypot(ctx_arr[0], ctx_arr[1]))

        ctx_t = torch.tensor([ctx_arr], dtype=torch.float32, device=self.device)

        with torch.no_grad():
            pred_kin, pred_actions, pred_traj = self.model(
                start_t, target_t, ctx_t, intent_t, teacher_forcing_ratio=0.0
            )

        pred_kin = pred_kin[0].cpu().numpy()
        pred_actions = pred_actions[0].cpu().numpy()
        pred_traj = pred_traj[0].cpu().numpy()

        trajectory = []
        trajectory.append({
            "x": float(start_x),
            "y": float(start_y),
            "dt_ms": 0.0,
            "type": "move"
        })

        # Fitts's Law Dynamic Step & Duration Allocation:
        # N_steps = int(N_base + k * log2(1 + distance / W_ref))
        # Shorter trajectories (200-300 px) complete faster (~250-350 ms, 35-45 steps)
        # Longer trajectories (800-1200 px) scale naturally (~550-750 ms, 65-85 steps)
        w_ref = 50.0
        fitts_index = math.log2(1.0 + max(0.0, init_dist) / w_ref)
        target_steps = int(round(4.0 + 15.5 * fitts_index))
        target_steps = max(30, min(95, target_steps))

        min_ballistic_steps = max(16, int(round(target_steps * 0.65)))
        max_ballistic_steps = max(min_ballistic_steps + 4, target_steps - 6)

        min_dist = float('inf')
        min_step = 0

        # 8-12 Hz Physiological Tremor via Ornstein-Uhlenbeck (OU) Continuous Process
        # dx = -theta * x * dt + sigma * sqrt(dt) * dW
        theta_ou = 15.0   # Relaxation parameter for 10-12 Hz biological tremor bandwidth
        sigma_ou = 0.22   # Physiological tremor amplitude (px)
        tremor_x, tremor_y = 0.0, 0.0
        prev_raw_x, prev_raw_y = start_x, start_y

        # Step through model output
        for step in range(len(pred_traj)):
            x_px = float(pred_traj[step, 0] * self.display_w)
            y_px = float(pred_traj[step, 1] * self.display_h)

            # Clamp coordinates to physical screen dimensions
            x_px = max(0.0, min(self.display_w - 1.0, x_px))
            y_px = max(0.0, min(self.display_h - 1.0, y_px))

            dist_to_target = float(np.hypot(target_x - x_px, target_y - y_px))
            if dist_to_target < min_dist:
                min_dist = dist_to_target
                min_step = step

            dt_scaled = float(pred_kin[step, 2]) * 100.0
            dt_ms = max(7.0, min(dt_scaled, 35.0))
            dt_sec = dt_ms / 1000.0

            # Instantaneous speed for biomechanical tremor suppression
            step_disp = np.hypot(x_px - prev_raw_x, y_px - prev_raw_y)
            cur_speed_px_s = step_disp / max(1e-4, dt_sec)
            prev_raw_x, prev_raw_y = x_px, y_px

            # Update Ornstein-Uhlenbeck colored noise process
            decay = max(0.0, 1.0 - theta_ou * dt_sec)
            noise_std = sigma_ou * math.sqrt(max(1e-4, dt_sec))
            tremor_x = decay * tremor_x + float(np.random.normal(0.0, noise_std))
            tremor_y = decay * tremor_y + float(np.random.normal(0.0, noise_std))

            # High ballistic velocities naturally suppress tremor amplitude
            speed_suppression = 1.0 / (1.0 + (cur_speed_px_s / 300.0) ** 2)
            final_x = max(0.0, min(self.display_w - 1.0, x_px + tremor_x * speed_suppression))
            final_y = max(0.0, min(self.display_h - 1.0, y_px + tremor_y * speed_suppression))

            action_idx = int(np.argmax(pred_actions[step]))
            action_type = "move"
            if action_idx == 1:
                action_type = "click_down"
            elif action_idx == 2:
                action_type = "click_up"
            elif action_idx == 3:
                action_type = "scroll"

            trajectory.append({
                "x": float(final_x),
                "y": float(final_y),
                "dt_ms": round(dt_ms, 2),
                "type": action_type
            })

            # Stopping conditions coordinated with Fitts's Law dynamic step target
            if intent > 0.5:
                # 1. Reached destination within target tolerance and met minimum ballistic steps
                if dist_to_target <= target_radius and step >= min_ballistic_steps:
                    break

                # 2. Overshoot or loitering near target
                if step > min_step + 4 and min_dist < 28.0 and step >= min_ballistic_steps:
                    if dist_to_target > min_dist + 2.5 or cur_speed_px_s < 100.0:
                        trajectory = trajectory[:min_step + 1]
                        break

                # 3. Terminal deceleration near target
                if step >= min_ballistic_steps and dist_to_target < 28.0 and cur_speed_px_s < 85.0:
                    break

                # 4. Ballistic step ceiling
                if step >= max_ballistic_steps:
                    break

        # Natural Human Settlement & Landing Phase:
        # Decelerate smoothly to the authentic human endpoint without artificial 0.00px snapping.
        if intent > 0.5 and len(trajectory) > 0:
            last_pt = trajectory[-1]
            p0_x, p0_y = float(last_pt["x"]), float(last_pt["y"])

            # Authentic human terminal landing dispersion:
            # Humans never snap with mathematical 0.00px precision to the target center.
            # Intrinsic dispersion standard deviation (~0.8 - 1.6 px)
            sigma_disp = max(0.6, min(1.6, target_radius * 0.35))
            disp_x = float(np.random.normal(0.0, sigma_disp))
            disp_y = float(np.random.normal(0.0, sigma_disp))
            disp_mag = math.hypot(disp_x, disp_y)
            if disp_mag > target_radius:
                disp_x = (disp_x / disp_mag) * target_radius
                disp_y = (disp_y / disp_mag) * target_radius

            authentic_target_x = target_x + disp_x
            authentic_target_y = target_y + disp_y

            rem_x = authentic_target_x - p0_x
            rem_y = authentic_target_y - p0_y
            rem_dist = float(np.hypot(rem_x, rem_y))

            if rem_dist > 0.8:
                # Estimate incoming velocity from preceding steps
                if len(trajectory) >= 3:
                    prev_pt = trajectory[-2]
                    dt_last = max(7.0, float(last_pt.get("dt_ms", 10.0))) / 1000.0
                    v_in = float(np.hypot(last_pt["x"] - prev_pt["x"], last_pt["y"] - prev_pt["y"])) / dt_last
                else:
                    v_in = 60.0

                v0 = max(25.0, min(150.0, v_in))
                T_dec = max(0.08, min(0.18, 0.5 * rem_dist / v0))
                D_dec = 0.5 * v0 * T_dec

                if rem_dist > D_dec:
                    D_coast = rem_dist - D_dec
                    T_coast = D_coast / v0
                    T_total = max(0.10, min(0.45, T_coast + T_dec))
                else:
                    D_coast = 0.0
                    T_coast = 0.0
                    T_total = max(0.08, 2.0 * rem_dist / v0)
                    T_dec = T_total
                    D_dec = rem_dist

                target_dt_ms = 8.5
                remaining_budget = max(4, target_steps - len(trajectory))
                num_sub_steps = min(22, max(remaining_budget, int(round((T_total * 1000.0) / target_dt_ms))))
                actual_dt_sec = T_total / float(num_sub_steps)
                sub_dt_ms = actual_dt_sec * 1000.0

                f_c = min(0.70, D_coast / max(1e-4, rem_dist)) if rem_dist > D_dec else 0.0

                for step_k in range(1, num_sub_steps + 1):
                    tau = step_k / float(num_sub_steps)
                    if step_k == num_sub_steps:
                        curr_sub_x = float(authentic_target_x)
                        curr_sub_y = float(authentic_target_y)
                    else:
                        if tau <= f_c and f_c > 0.0:
                            frac = tau
                        else:
                            sig = (tau - f_c) / max(1e-4, 1.0 - f_c)
                            frac = f_c + (1.0 - f_c) * (1.0 - (1.0 - sig) ** 2)

                        frac = max(0.0, min(1.0, frac))
                        curr_sub_x = p0_x + rem_x * frac
                        curr_sub_y = p0_y + rem_y * frac

                    trajectory.append({
                        "x": float(curr_sub_x),
                        "y": float(curr_sub_y),
                        "dt_ms": round(sub_dt_ms, 2),
                        "type": "move"
                    })

        # Neuromuscular Kinematic Shaping:
        # Case 1: Neuromuscular Onset Inertia (Quintic Smoothstep Ramp from Rest)
        # When starting from rest (residual inflow momentum <= 15.0 px/s), arm inertia and motor unit
        # recruitment latency prevent instantaneous acceleration jumps. Modulate early displacements
        # via quintic smoothstep w(t) = 6*tau^5 - 15*tau^4 + 10*tau^3 (where w'(0)=0, w''(0)=0) over the
        # initial K_ramp steps (~30-50 ms) so acceleration builds smoothly from zero.
        if v_residual_mag <= 15.0 and len(trajectory) >= 10:
            K_ramp = min(7, len(trajectory) - 2)
            p0_x, p0_y = trajectory[0]['x'], trajectory[0]['y']
            for step_k in range(1, K_ramp + 1):
                tau = step_k / float(K_ramp)
                w = 6.0 * (tau ** 5) - 15.0 * (tau ** 4) + 10.0 * (tau ** 3)
                trajectory[step_k]['x'] = p0_x + (trajectory[step_k]['x'] - p0_x) * w
                trajectory[step_k]['y'] = p0_y + (trajectory[step_k]['y'] - p0_y) * w

        # Case 2: Waypoint Momentum Bleed & Symmetrized Relaunch
        # At waypoint transitions (momentum chaining with v_residual_mag > 15.0 px/s), smoothly fade out
        # residual inflow momentum using a cosine envelope while modulating newly directed departure velocity
        # over K_trans = 10 to 14 steps (~40-60 ms) so acceleration rises symmetrically to Point A.
        elif v_residual_mag > 15.0 and len(trajectory) >= 16:
            K_trans = min(12, len(trajectory) - 2)
            orig_pts = [(p['x'], p['y']) for p in trajectory[:K_trans + 1]]

            v_mod_xs = [(orig_pts[i][0] - orig_pts[i-1][0]) / max(0.007, trajectory[i]['dt_ms'] / 1000.0) for i in range(1, K_trans + 1)]
            v_mod_ys = [(orig_pts[i][1] - orig_pts[i-1][1]) / max(0.007, trajectory[i]['dt_ms'] / 1000.0) for i in range(1, K_trans + 1)]

            for step_i in range(1, K_trans + 1):
                tau = step_i / float(K_trans)
                w = 3.0 * (tau ** 2) - 2.0 * (tau ** 3)
                fade = 0.5 * (1.0 + math.cos(math.pi * tau))

                dt_i = max(0.007, trajectory[step_i]['dt_ms'] / 1000.0)
                v_blended_x = fade * vx_residual + (1.0 - fade) * v_mod_xs[step_i - 1] * w
                v_blended_y = fade * vy_residual + (1.0 - fade) * v_mod_ys[step_i - 1] * w

                new_x = trajectory[step_i - 1]['x'] + v_blended_x * dt_i
                new_y = trajectory[step_i - 1]['y'] + v_blended_y * dt_i

                trajectory[step_i]['x'] = float(new_x)
                trajectory[step_i]['y'] = float(new_y)

            # Feather coordinate offset smoothly across subsequent steps to prevent trajectory drift
            delta_x = trajectory[K_trans]['x'] - orig_pts[K_trans][0]
            delta_y = trajectory[K_trans]['y'] - orig_pts[K_trans][1]
            feather_steps = min(14, len(trajectory) - 1 - K_trans)
            for j in range(1, feather_steps + 1):
                idx = K_trans + j
                decay = 1.0 - (j / float(feather_steps + 1))
                trajectory[idx]['x'] += delta_x * decay
                trajectory[idx]['y'] += delta_y * decay


        return trajectory

# =====================================================================
# High-Level HumanMouse Developer API
# =====================================================================

class HumanMouse:
    """
    High-level Programmatic API for natural AI human mouse movement.
    Uses trained PyTorch neural network weights to generate realistic human mouse trajectories.
    """
    def __init__(self, model_path=None, failsafe=True, dry_run=False):
        self.dry_run = dry_run
        self.failsafe = failsafe
        self._virtual_pos = (960, 540)

        # Headless Linux environment detection
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            self.dry_run = True

        if PYAUTOGUI_AVAILABLE and not self.dry_run:
            try:
                self.screen_w, self.screen_h = pyautogui.size()
                pyautogui.FAILSAFE = failsafe
                pos = pyautogui.position()
                self._virtual_pos = (int(pos[0]), int(pos[1]))
            except Exception:
                self.screen_w, self.screen_h = 1920, 1080
                self.dry_run = True
        else:
            self.screen_w, self.screen_h = 1920, 1080

        self.simulator = HumanMouseSimulator(
            model_path=model_path,
            display_w=self.screen_w,
            display_h=self.screen_h
        )
        self.prev_context = None

    def get_current_position(self):
        """Returns current mouse (x, y) position on screen."""
        if not self.dry_run and PYAUTOGUI_AVAILABLE:
            try:
                pos = pyautogui.position()
                return (int(pos[0]), int(pos[1]))
            except Exception:
                pass
        return getattr(self, "_virtual_pos", (960, 540))

    def generate_trajectory(self, start_pos, target_pos, prev_context=None, intent=1.0, target_radius=5.0):
        """Generates AI trajectory sequence without executing physical mouse movement."""
        ctx = prev_context if prev_context is not None else self.prev_context
        raw_traj = self.simulator.generate_trajectory(
            start_pos=start_pos,
            target_pos=target_pos,
            prev_context=ctx,
            intent=intent,
            target_radius=target_radius
        )
        in_vel = (ctx[0] * self.screen_w, ctx[1] * self.screen_h) if (ctx is not None and len(ctx) >= 2) else None
        return self.apply_biomechanical_kinematic_filter(raw_traj, incoming_velocity=in_vel)

    @staticmethod
    def apply_biomechanical_kinematic_filter(trajectory, v_threshold=None, max_velocity=None, max_acceleration=15000.0, min_dt_ms=7.0, split_idx=None, incoming_velocity=None):
        """
        Global Biomechanical Safety Filter.
        Enforces continuous physiological constraints across single or multi-segment paths:
          1. Strict hardware polling lower bound: dt >= min_dt_ms (default 7.0 ms, 125-142 Hz polling).
          2. Continuous Savitzky-Golay coordinate smoothing (eliminates quantization staircasing)
             with boundary anchoring.
          3. Neuromuscular Onset Inertia (Smoothstep / Cubic Ramp):
             For movements initiated from rest, modulates early displacements by w(t) = 3(t/K)^2 - 2(t/K)^3
             over the initial K_ramp steps (~30-50 ms), building acceleration smoothly from zero.
          4. Waypoint Transition Momentum Blending & Symmetrized Relaunch:
             When chained across waypoints (split_idx provided), applies a cosine/smoothstep blend
             over K_trans = 10 to 14 steps (~40-60 ms), symmetrizing departing acceleration with Point A.
          5. Distance-Adaptive Peak Velocity Rescaling (Soft Elastic Cap):
             Calculates biologically plausible peak velocity V_max(D) = V_base + alpha * sqrt(D)
             (V_base ~ 800 px/s, softly guided between 1500 and 2300 px/s).
             Smoothly rescales velocity profile via soft algebraic compression, preserving bell-curve geometry.
          6. Forward-backward velocity profiling bounding acceleration |a| <= max_acceleration (default 15,000 px/s^2, effective <= 13,800 px/s^2).
          7. Acceleration-to-Deceleration Transition Shaping (Hann Relaxation Window):
             Applies a Hann/cosine smoothing window (K_relax = 7 steps) across the acceleration cutoff
             at peak velocity and braking onset, ensuring continuous, finite da/dt (Jerk continuity).
        """
        if not trajectory or len(trajectory) < 3:
            return trajectory

        out = [dict(p) for p in trajectory]
        N = len(out)

        # 1. Enforce strict hardware polling lower bound
        for i in range(1, N):
            out[i]['dt_ms'] = max(min_dt_ms, float(out[i]['dt_ms']))

        # 2. Extract discrete positions and apply continuous smoothing to eliminate staircasing
        xs = np.array([p['x'] for p in out], dtype=np.float64)
        ys = np.array([p['y'] for p in out], dtype=np.float64)

        if N >= 9:
            if SCIPY_AVAILABLE:
                s_xs = savgol_filter(xs, window_length=9, polyorder=2)
                s_ys = savgol_filter(ys, window_length=9, polyorder=2)
            else:
                kernel = np.array([0.05, 0.25, 0.40, 0.25, 0.05])
                s_xs = np.convolve(xs, kernel, mode='same')
                s_ys = np.convolve(ys, kernel, mode='same')
            # Strict boundary anchor to preserve starting coordinate and exact target landing
            s_xs[0], s_ys[0] = xs[0], ys[0]
            s_xs[-1], s_ys[-1] = xs[-1], ys[-1]
        else:
            s_xs, s_ys = xs.copy(), ys.copy()

        # 3. Neuromuscular Onset Inertia (Quintic Smoothstep Ramp from Rest)
        # Apply quintic ramp if movement starts from rest (no incoming momentum or < 15 px/s).
        # Ensures a(0) = 0 px/s^2 and ascends smoothly without sudden leaps.
        K_ramp = min(7, N - 2)
        if (incoming_velocity is None or np.hypot(incoming_velocity[0], incoming_velocity[1]) < 15.0) and K_ramp >= 2:
            p0_x, p0_y = s_xs[0], s_ys[0]
            for t in range(1, K_ramp + 1):
                tau = t / float(K_ramp)
                w = 6.0 * (tau ** 5) - 15.0 * (tau ** 4) + 10.0 * (tau ** 3)
                s_xs[t] = p0_x + (s_xs[t] - p0_x) * w
                s_ys[t] = p0_y + (s_ys[t] - p0_y) * w

        # 4. Waypoint Transition Momentum Bleed & Symmetrized Relaunch
        if split_idx is not None and 0 < split_idx < N - 14:
            K_trans = min(12, N - 1 - split_idx)
            dt_pre = max(min_dt_ms, out[split_idx]['dt_ms']) / 1000.0
            v_arr_x = (s_xs[split_idx] - s_xs[split_idx - 1]) / dt_pre
            v_arr_y = (s_ys[split_idx] - s_ys[split_idx - 1]) / dt_pre

            curr_x, curr_y = s_xs[split_idx], s_ys[split_idx]
            orig_seg2_x = s_xs[split_idx:split_idx + K_trans + 1].copy()
            orig_seg2_y = s_ys[split_idx:split_idx + K_trans + 1].copy()

            v_mod_xs = [(orig_seg2_x[i] - orig_seg2_x[i-1]) / (max(min_dt_ms, out[split_idx + i]['dt_ms']) / 1000.0) for i in range(1, K_trans + 1)]
            v_mod_ys = [(orig_seg2_y[i] - orig_seg2_y[i-1]) / (max(min_dt_ms, out[split_idx + i]['dt_ms']) / 1000.0) for i in range(1, K_trans + 1)]

            for step_i in range(1, K_trans + 1):
                idx = split_idx + step_i
                tau = step_i / float(K_trans)
                w = 3.0 * (tau ** 2) - 2.0 * (tau ** 3)
                fade = 0.5 * (1.0 + math.cos(math.pi * tau))
                dt_i = max(min_dt_ms, out[idx]['dt_ms']) / 1000.0

                v_blend_x = fade * v_arr_x + (1.0 - fade) * v_mod_xs[step_i - 1] * w
                v_blend_y = fade * v_arr_y + (1.0 - fade) * v_mod_ys[step_i - 1] * w

                curr_x += v_blend_x * dt_i
                curr_y += v_blend_y * dt_i
                s_xs[idx] = curr_x
                s_ys[idx] = curr_y

            # Feather coordinate difference smoothly over next downstream steps
            delta_x = s_xs[split_idx + K_trans] - orig_seg2_x[-1]
            delta_y = s_ys[split_idx + K_trans] - orig_seg2_y[-1]
            feather_steps = min(14, N - 1 - (split_idx + K_trans))
            for j in range(1, feather_steps + 1):
                decay = 1.0 - (j / float(feather_steps + 1))
                s_xs[split_idx + K_trans + j] += delta_x * decay
                s_ys[split_idx + K_trans + j] += delta_y * decay

        for i in range(N):
            out[i]['x'] = s_xs[i]
            out[i]['y'] = s_ys[i]

        dists = np.hypot(np.diff(s_xs), np.diff(s_ys))  # length N-1
        raw_dts = np.array([p['dt_ms'] / 1000.0 for p in out[1:]], dtype=np.float64)
        v_raw = dists / np.maximum(1e-4, raw_dts)

        # 5. Global Proportional Bell Rescaling
        # Preserves 100% of the neural model's continuous bell-curve convexity (d^2v/dt^2 != 0).
        # Eliminates horizontal plateau deadzones and zero-acceleration machine fingerprints.
        total_dist = float(np.sum(dists))
        v_base = 800.0
        alpha = 42.0
        v_target_max = float(np.clip(v_base + alpha * math.sqrt(max(1.0, total_dist)), 1600.0, 2300.0))
        if max_velocity is not None and max_velocity > 0:
            v_target_max = min(float(max_velocity), v_target_max)

        v_peak = float(np.max(v_raw))
        if v_peak > v_target_max and v_peak > 1e-4:
            s = v_target_max / v_peak
        else:
            s = 1.0

        v_scaled = v_raw * s
        dt_clamped = np.maximum(min_dt_ms / 1000.0, dists / np.maximum(1e-4, v_scaled))

        # 6. Dynamic Forward-Backward Acceleration Limiting
        # Bounded within physiological desktop human acceleration envelope (~12,000 to 14,000 px/s^2)
        effective_a_max = min(13800.0, max_acceleration * 0.90)

        for i in range(len(v_scaled)):
            if dists[i] < 0.1:
                v_scaled[i] = 0.0

        # Forward pass: v[i] <= v[i-1] + a_max * dt
        for i in range(1, len(v_scaled)):
            dt_step = dt_clamped[i]
            if v_scaled[i-1] == 0.0 and v_scaled[i] > 0.0:
                min_dt_launch = math.sqrt(dists[i] / effective_a_max)
                dt_clamped[i] = max(dt_clamped[i], min_dt_launch)
                v_scaled[i] = dists[i] / dt_clamped[i]
            else:
                max_allowed_v = v_scaled[i-1] + effective_a_max * dt_step
                if v_scaled[i] > max_allowed_v:
                    v_scaled[i] = max_allowed_v
                    if v_scaled[i] > 1e-4:
                        dt_clamped[i] = max(min_dt_ms / 1000.0, dists[i] / v_scaled[i])

        # Backward pass: v[i] <= v[i+1] + a_max * dt
        for i in range(len(v_scaled) - 2, -1, -1):
            dt_step = dt_clamped[i]
            if v_scaled[i+1] == 0.0 and v_scaled[i] > 0.0:
                min_dt_stop = math.sqrt(dists[i] / effective_a_max)
                dt_clamped[i] = max(dt_clamped[i], min_dt_stop)
                v_scaled[i] = dists[i] / dt_clamped[i]
            else:
                max_allowed_v = v_scaled[i+1] + effective_a_max * dt_step
                if v_scaled[i] > max_allowed_v:
                    v_scaled[i] = max_allowed_v
                    if v_scaled[i] > 1e-4:
                        dt_clamped[i] = max(min_dt_ms / 1000.0, dists[i] / v_scaled[i])

        # 7. Acceleration-to-Deceleration Transition Shaping (Hann Relaxation Window)
        # Smooths discrete acceleration cutoff at peak velocity and transition into braking,
        # ensuring continuous, finite da/dt (Jerk continuity) across drive-to-deceleration inflection.
        if N >= 15:
            K_relax = 7
            hann_kernel = np.hanning(K_relax)
            hann_kernel /= np.sum(hann_kernel)
            half_k = K_relax // 2

            v_smoothed = np.convolve(v_scaled, hann_kernel, mode='same')
            v_scaled[half_k : -half_k] = v_smoothed[half_k : -half_k]

            for i in range(len(v_scaled)):
                if v_scaled[i] > 1e-4:
                    dt_clamped[i] = max(min_dt_ms / 1000.0, dists[i] / v_scaled[i])

        # Re-apply updated dt_ms smoothly
        for i in range(1, N):
            out[i]['dt_ms'] = round(dt_clamped[i-1] * 1000.0, 3)

        return out


    def _execute_trajectory(self, trajectory, perform_click=False, button='left'):
        """Executes generated trajectory points with sub-millisecond precision timing and Windows multimedia timer."""
        if not trajectory or self.dry_run:
            return

        # Boost Windows system timer resolution to 1ms
        timer_boosted = False
        if winmm is not None:
            try:
                winmm.timeBeginPeriod(1)
                timer_boosted = True
            except Exception:
                pass

        try:
            start_time = time.perf_counter()
            cumulative_target_sec = 0.0

            for step in trajectory:
                dt_base_sec = step['dt_ms'] / 1000.0
                # Hardware Polling Micro-Jitter (Live Execution Layer):
                # Emulate real USB HID 125 Hz polling with OS scheduling jitter
                # Delta t ~ N(mu=0.008s, sigma=0.0006s) clamped to [0.004, 0.012]s
                jitter = float(np.random.normal(0.0, 0.0006))
                dt_jittered = max(0.004, min(0.012, dt_base_sec + jitter))

                cumulative_target_sec += dt_jittered
                step_target_time = start_time + cumulative_target_sec

                # Sub-millisecond hybrid sleep-spinwait pacing
                while True:
                    rem = step_target_time - time.perf_counter()
                    if rem <= 0.0:
                        break
                    # If remaining time > 2ms, sleep coarsened by 1.2ms to avoid scheduler oversleep
                    if rem > 0.002:
                        time.sleep(rem - 0.0012)
                    # For final sub-millisecond fraction, spin-wait to eliminate quantum latency

                x = int(step['x'])
                y = int(step['y'])

                # Fail-safe check: escape to screen corner (0, 0) if not starting at (0, 0)
                if self.failsafe and (x, y) == (0, 0) and (trajectory[0]['x'], trajectory[0]['y']) != (0, 0):
                    raise pyautogui.FailSafeException("PyAutoGUI fail-safe triggered from mouse moving to corner (0, 0)")

                self._virtual_pos = (x, y)

                # Low-latency direct kernel cursor positioning on Windows, fallback to pyautogui
                if not self.dry_run:
                    if user32 is not None:
                        user32.SetCursorPos(x, y)
                    elif PYAUTOGUI_AVAILABLE:
                        try:
                            pyautogui.moveTo(x, y)
                        except Exception:
                            self.dry_run = True

            if perform_click and not self.dry_run and PYAUTOGUI_AVAILABLE:
                try:
                    pyautogui.click(button=button)
                except Exception:
                    pass

        finally:
            # Restore system timer resolution
            if timer_boosted and winmm is not None:
                try:
                    winmm.timeEndPeriod(1)
                except Exception:
                    pass

    def compute_terminal_momentum(self, trajectory, dwell_time_sec=0.08, jump_offset=(0.0, 0.0)):
        """
        Computes the residual arrival velocity vector (vx, vy) and builds the full
        kinematic memory context vector for smooth momentum chaining across waypoints.
        Enforces strict physiological limits (v <= 1800 px/s), normalized coordinates,
        and exponential dwell time dissipation (tau = 0.08s).
        """
        if not trajectory or len(trajectory) < 2:
            if getattr(self.simulator, 'context_dim', 8) == 8:
                return (0.0, 0.0, float(dwell_time_sec), 0.0, 0.0, 0.0, 0.1, 0.0)
            return (0.0, 0.0, 0.0, 0.1)

        # 1. Identify arrival velocity from moving steps prior to terminal rest
        # Look back up to 28 steps to capture the approach momentum before final settling
        k = min(28, len(trajectory) - 1)
        tail = trajectory[-k:]
        moving_steps = [s for s in tail if s.get('dt_ms', 0) > 0]

        if len(moving_steps) >= 6:
            eval_steps = moving_steps[:max(2, len(moving_steps) - 6)]
            dx_px = float(eval_steps[-1]['x'] - eval_steps[0]['x'])
            dy_px = float(eval_steps[-1]['y'] - eval_steps[0]['y'])
            dt_sum_sec = float(sum(s['dt_ms'] for s in eval_steps[1:]) / 1000.0)
            if dt_sum_sec > 1e-4:
                vx_px_s = dx_px / dt_sum_sec
                vy_px_s = dy_px / dt_sum_sec
            else:
                vx_px_s, vy_px_s = 0.0, 0.0
        elif len(moving_steps) >= 2:
            dx_px = float(moving_steps[-1]['x'] - moving_steps[0]['x'])
            dy_px = float(moving_steps[-1]['y'] - moving_steps[0]['y'])
            dt_sum_sec = float(sum(s['dt_ms'] for s in moving_steps[1:]) / 1000.0)
            if dt_sum_sec > 1e-4:
                vx_px_s = dx_px / dt_sum_sec
                vy_px_s = dy_px / dt_sum_sec
            else:
                vx_px_s, vy_px_s = 0.0, 0.0
        else:
            vx_px_s, vy_px_s = 0.0, 0.0

        # 2. Cap to realistic physiological bounds (v_max_human ~ 1800 px/s)
        v_mag_px_s = float(np.hypot(vx_px_s, vy_px_s))
        if v_mag_px_s > 1800.0:
            scale_cap = 1800.0 / v_mag_px_s
            vx_px_s *= scale_cap
            vy_px_s *= scale_cap
            v_mag_px_s = 1800.0

        # 3. Exponential dwell dissipation: v_inflow = v_terminal * exp(-dwell / tau_decay)
        tau_decay = 0.08  # 80ms decay constant
        dwell_s = max(0.0, float(dwell_time_sec))
        decay_factor = math.exp(-dwell_s / tau_decay)

        # If pause/dwell exceeds 100ms or decayed speed is negligible (<10 px/s), dissipate to complete rest
        if dwell_s > 0.10 or (v_mag_px_s * decay_factor) < 10.0:
            vx_inflow = 0.0
            vy_inflow = 0.0
        else:
            vx_inflow = vx_px_s * decay_factor
            vy_inflow = vy_px_s * decay_factor

        # 4. Strict screen normalization (W, H)
        vx_final = float(vx_inflow / self.screen_w)
        vy_final = float(vy_inflow / self.screen_h)
        norm_mag = float(np.hypot(vx_final, vy_final))

        # Clamp normalized magnitude to <= 1.0
        if norm_mag > 1.0:
            vx_final /= norm_mag
            vy_final /= norm_mag
            norm_mag = 1.0

        clicks = float(sum(1 for step in trajectory if step['type'] in ['click_down', 'click_up']) / 256.0)
        avg_dt = float((sum(step['dt_ms'] for step in trajectory) / len(trajectory)) / 100.0)
        scaled_dwell = max(0.01, min(1.0, float(dwell_time_sec)))

        if getattr(self.simulator, 'context_dim', 8) == 8:
            return (
                float(vx_final),
                float(vy_final),
                float(scaled_dwell),
                float(jump_offset[0] / self.screen_w),
                float(jump_offset[1] / self.screen_h),
                float(clicks),
                float(avg_dt),
                float(norm_mag)
            )
        else:
            return (float(vx_final), float(vy_final), float(clicks), float(avg_dt))

    def _update_context(self, trajectory, dwell_time_sec=0.1):
        """Updates internal momentum context vector from the most recent movement."""
        self.prev_context = self.compute_terminal_momentum(trajectory, dwell_time_sec=dwell_time_sec)

    def set_context(self, vx=0.0, vy=0.0, dwell_time=0.1, clicks=0.0, avg_dt=0.1):
        """
        Manually sets or overrides the velocity/momentum context vector.
        """
        mag = float(np.hypot(vx, vy))
        if getattr(self.simulator, 'context_dim', 8) == 8:
            self.prev_context = (float(vx), float(vy), float(dwell_time), 0.0, 0.0, float(clicks), float(avg_dt), mag)
        else:
            self.prev_context = (float(vx), float(vy), float(clicks), float(avg_dt))

    def get_context(self):
        """Returns current context vector."""
        return self.prev_context

    def move_to(self, target_x, target_y, click=False, button='left', delay_after=0.1, prev_context=None, target_radius=5.0, dwell_time=0.1):
        """
        Smoothly moves mouse from current position to (target_x, target_y) naturally using AI.
        prev_context: Optional context tuple to override velocity context.
        target_radius: Distance tolerance (px) to consider destination reached.
        dwell_time: Inter-waypoint dwell time (sec) for kinematic chaining.
        """
        start_x, start_y = self.get_current_position()
        ctx = prev_context if prev_context is not None else self.prev_context
        trajectory = self.generate_trajectory((start_x, start_y), (target_x, target_y), prev_context=ctx, intent=1.0, target_radius=target_radius)

        self._execute_trajectory(trajectory, perform_click=click, button=button)
        self._update_context(trajectory, dwell_time_sec=dwell_time)

        if delay_after > 0:
            time.sleep(delay_after)

        return trajectory

    sample_target_within_box = staticmethod(sample_target_within_box)

    def click_at(self, target_x, target_y=None, button='left', delay_after=0.1, prev_context=None, target_radius=5.0, target_box=None):
        """
        Moves mouse naturally to target and clicks with human kinematics.
        If target_box=(x, y, w, h) is provided, samples an authentic human landing
        coordinate within the box using a truncated 2D Gaussian.
        """
        if target_box is not None:
            target_x, target_y = sample_target_within_box(target_box)
        elif target_y is None and isinstance(target_x, (tuple, list, dict)):
            target_x, target_y = sample_target_within_box(target_x)

        return self.move_to(target_x, target_y, click=True, button=button, delay_after=delay_after, prev_context=prev_context, target_radius=target_radius)

    def wander(self, radius=200, delay_after=0.1):
        """Generates a natural idle wandering movement around the current area without intending to click."""
        start_x, start_y = self.get_current_position()
        target_x = max(0, min(self.screen_w, start_x + random.randint(-radius, radius)))
        target_y = max(0, min(self.screen_h, start_y + random.randint(-radius, radius)))
        
        trajectory = self.generate_trajectory((start_x, start_y), (target_x, target_y), prev_context=self.prev_context, intent=0.0)
        self._execute_trajectory(trajectory, perform_click=False)
        self._update_context(trajectory, dwell_time_sec=0.2)

        if delay_after > 0:
            time.sleep(delay_after)

        return trajectory

    def move_sequence(self, target_list, click_targets=False, delay_between=0.05, target_radius=5.0, continuous_chaining=True):
        """
        Moves mouse smoothly across a sequence of targets (x, y) maintaining continuous
        kinematic momentum chaining to avoid sharp geometric/polygonal turns.
        """
        results = []
        for i, target in enumerate(target_list):
            target_x, target_y = target
            is_last = (i == len(target_list) - 1)
            dwell = 0.20 if is_last else (0.04 if continuous_chaining else 0.15)
            traj = self.move_to(
                target_x,
                target_y,
                click=(click_targets if is_last else False),
                delay_after=(delay_between if not is_last else 0.0),
                target_radius=target_radius,
                dwell_time=dwell
            )
            results.append(traj)
        return results

if __name__ == '__main__':
    print("Testing self-contained HumanMouse module dry-run...")
    mouse = HumanMouse()
    pos = mouse.get_current_position()
    print(f"Current Position: {pos}")
    traj = mouse.generate_trajectory(pos, (500, 500))
    print(f"Generated trajectory length: {len(traj)} steps")
