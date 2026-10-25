# Documentation & Visual Artifacts

This directory stores visual plots, trajectories, and documentation assets for the AI Natural Human Mouse project.

## Files

- **`trajectory_demo.png`**: Multi-panel visualization verifying:
  1. *2D Route Arc*: Segment 1 (Point A $\to$ Waypoint B) momentum-blended into Segment 2 (Waypoint B $\to$ Point C) showing natural trajectory curvature and box dispersion.
  2. *Continuous Velocity Profile $v(t)$*: Symmetric bell curves with global proportional scaling ($V_{\text{target\_max}}(D) \le 2300\text{ px/s}$) and zero flatline plateaus.
  3. *Acceleration Dynamics $a(t)$*: Biomechanically bounded acceleration ($|a| \le 14,000\text{ px/s}^2$) with smoothstep neuromuscular onset and Hann decay relaxation across drive-to-deceleration inflections.
- **`human_vs_bot_comparison.png`**: Side-by-side comparative visual plots highlighting:
  1. *2D Spatial Path*: Authentic curved human trajectory with micro-tremor vs. rigid robotic linear interpolation.
  2. *Velocity Over Time*: Human acceleration/deceleration bell curve vs. robotic step-function velocity profile.
