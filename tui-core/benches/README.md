# `tui-core/benches/` — High-Performance Benchmarking Harness

> **Automated Latency, Throughput, Memory & CPU Benchmark Harness** for the compiled multi-agent TUI engine.
> Maintained by Testing & Benchmarking Engineer (`agy100`).

---

## 1. Overview & Architectural Scope

This directory contains the standalone performance benchmarking harness for `tui-core`. It establishes comparative performance baselines against the legacy Python implementation (`Textual`, `Rich`, `Pyte`, and `asyncio`), proving sub-millisecond frame rendering latency, micro-overhead resident memory footprint, ultra-high-throughput PTY stream processing, and minimal CPU utilization under 100 FPS screen updates.

### Target Performance Goals & Baselines

| Metric | Target (Compiled Rust) | Legacy Python Textual Baseline | Target Improvement |
|---|---|---|---|
| **Frame Rendering Latency** | Sub-millisecond (< 1.0 ms) | ~15.0 - 30.0 ms (15,000 - 30,000 µs) | >200x Faster |
| **Dirty-Frame Cache Check** | Sub-microsecond (< 1.0 µs) | Not Supported (Full re-layout) | >10,000x Faster |
| **Resident Memory (RSS)** | < 10.0 MB (8 worker swarm) | ~150 - 240 MB (Python + GIL runtime) | >85% Memory Reduction |
| **PTY Stream Ingestion** | > 500,000 ops/sec, > 50 MB/s | ~2.5 - 5.0 MB/s (Pyte/GIL bound) | >25x Throughput |
| **CPU Load @ 100 FPS Updates** | < 2.0% CPU Utilization | ~45% - 75% CPU Utilization | >95% CPU Efficiency |

---

## 2. Itemized Breakdown of Files

| File | Purpose | Key Benchmarks Measured |
|---|---|---|
| [`benchmarks.rs`](file:///home/pluto/projects/mind/tui-core/benches/benchmarks.rs) | Standalone benchmark harness entrypoint | Harness bootstrap executable via `cargo bench` or `cargo run --bench benchmarks`. |
| [`../src/benchmarks.rs`](file:///home/pluto/projects/mind/tui-core/src/benchmarks.rs) | Core benchmark implementation | Four primary benchmark routines: (1) Frame Latency & Dirty-Frame Caching, (2) PTY Throughput, (3) Resident Memory Footprint, (4) CPU Utilization @ 100 FPS. |
| [`../BENCHMARKS.md`](file:///home/pluto/projects/mind/tui-core/BENCHMARKS.md) | Official Comparative Analysis Report | Detailed breakdown of empirical benchmark numbers, statistical percentiles (min, mean, p50, p95, p99), and architecture comparisons vs Python. |

---

## 3. Step-by-Step Instructions for Running Benchmarks Locally

### Option 1: Via Central CLI Command
```bash
cargo run --manifest-path tui-core/Cargo.toml -- bench
```

### Option 2: Via Cargo Bench
```bash
cargo bench --manifest-path tui-core/Cargo.toml
```

### Option 3: Via Standalone Bench Runner
```bash
cargo run --manifest-path tui-core/Cargo.toml --bench benchmarks
```

### Reproducing Benchmark Edge Cases
- **High-Resolution Stress (160x50 cells / 8,000 cells)**: Automatically executed as part of suite (Section 1B).
- **Quad-Pane Multiplexer Under Full Load**: Renders a complete swarm dashboard with 4 active terminal screens in a 2x2 grid alongside system gauges and worker lists (Section 1D).
- **100 FPS Sustained Updates**: Runs 200 real-time frames at 10 ms intervals, measuring kernel clock ticks (`utime` + `stime`) from `/proc/self/stat`.

---

## 4. Dependencies & Measurement Methodology

1. **Linux Process Introspection (`/proc/self`)**:
   - `VmRSS` is read directly from `/proc/self/status` in kilobytes to accurately capture resident physical pages.
   - User mode CPU ticks (`utime`, field 14) and system mode CPU ticks (`stime`, field 15) are sampled before and after the 100 FPS animation loop from `/proc/self/stat`.
2. **Double-Buffered Ratatui Canvas (`TestBackend`)**:
   - The benchmark renders into a zero-I/O in-memory terminal buffer to measure pure computation and memory-copy latency without terminal device driver throttling.
3. **Statistical Latency Percentiles**:
   - Every frame time is captured using `std::time::Instant` and aggregated into Min, Mean, Median (P50), P95, and P99 latency percentiles.
