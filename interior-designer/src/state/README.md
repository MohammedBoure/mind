# State Management & Architectural Persistence (`interior-designer/src/state`)

## Architectural Role & Scope
This directory governs state orchestration, local persistence, undo/redo history tracking (up to 100 snapshots), real-time topological recalculation, and the preloaded commercial cafe showcase project. It ensures zero data loss via debounced local storage persistence and enables seamless parallel design branching (Alternative A vs Alternative B).

## Itemized File Breakdown
- `defaultProject.ts`: Factory constructing a preloaded commercial cafe/bistro architectural model containing enclosed rooms (Main Dining Hall, Barista Prep Kitchen, Utility Restroom), walls, host doors, double-glazed windows, and placed catalog items (counters, dining sets, fluted booths, non-blocking rugs, and planters).
- `projectStore.ts`: Central React hook managing active alternatives, multi-alternative design branches, 100-operation undo/redo stacks, automatic room detection dispatch, active selections, editor modes, and dynamic collision conflict mapping.
- `README.md`: This comprehensive English documentation file.

## Exposed Interfaces & Utilities
- `createDefaultProject()`: Instantiates default multi-alternative project.
- `useProjectStore()`: React hook exposing design state, spatial caches, and dispatch mutators.

## Local Dependencies & Environment Variables
- Core types from `../types/plan.js`, room detection from `../core/roomDetection.js`, and collision tests from `../core/collision.js`.
- Zero backend dependencies; zero external CDN dependencies.

## Caveats & Implementation Notes
- Any modification to wall vertices automatically triggers `detectRooms`, maintaining closed cycle continuity and area calculations.
- Mutations push deep snapshot clones onto the internal undo stack, allowing immediate rollback across all planar geometry operations.
