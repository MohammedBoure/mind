# `docs/` — Project Architecture & Specifications

This directory contains technical architecture specifications, environment setup guides, and operational manuals for `mind` and the `agi` multi-agent orchestrator.

## Files

| File | Purpose |
|---|---|
| [`ENVIRONMENT_SETUP_AND_AGENT_FLEET.md`](file:///home/pluto/projects/mind/docs/ENVIRONMENT_SETUP_AND_AGENT_FLEET.md) | **Primary Workstation & Fleet Setup Guide**: Complete manual on preparing the host machine (Bubblewrap sandbox isolation, system packages, Rust toolchain, Antigravity CLI `agy`), multi-instance manager `agys`, deterministic slot hierarchy (`agy1`..`agy200`), governance rules, and multi-account quota monitoring. |
| [`architecture_and_migration_guide.md`](file:///home/pluto/projects/mind/docs/architecture_and_migration_guide.md) | Architectural specifications, platform comparison (Windows ConPTY vs Linux POSIX PTY), FastMCP integration, Vim modal navigation, lazy spawning, 5-tier clipboard engine, and migration blueprint. |
| [`auth_refactor_architecture.md`](file:///home/pluto/projects/mind/docs/auth_refactor_architecture.md) | Architecture documentation and interface specifications for authentication and credential management, including `AuthValidator`, `TokenManager`, and cross-process mutex synchronization. |
