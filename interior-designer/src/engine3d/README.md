# 3D Graphics Engine (`interior-designer/src/engine3d`)

## Architectural Role & Scope
This directory contains the Three.js real-time 3D rendering engine for the architectural interior studio. It generates photorealistic procedural 3D elements without external downloads, coordinates the Orbit dollhouse view with dynamic Presentation Cutaway plinths (0.25m), operates the First-Person Walkthrough controller with realistic traversal physics, and enables bi-directional selection through 3D raycasting.

## Itemized File Breakdown
- `materials.ts`: Procedural PBR material factory synthesizing standard and physical materials (oak parquet, walnut, subway tile, terrazzo, polished concrete, metals, fabrics, and clear architectural transmission glass) backed by in-memory procedural canvas textures.
- `proceduralMeshes.ts`: Parametric 3D mesh constructors synthesizing all 18 catalog elements via Three.js primitives (dining tables, chairs, barstools, straight and corner counters, fluted booths, acoustic screens, pendants with pointlights, rugs, foliage, desks, task chairs, and showcases).
- `cutaway.ts`: Presentation cutaway manager that analyzes camera azimuth relative to perimeter walls and dynamically lowers viewer-facing walls to low plinths (0.25m) in orbit mode, immediately restoring full height upon entering walkthrough mode.
- `walkthrough.ts`: First-person traversal controller featuring PointerLock mouse look, WASD movement, eye level ~1.65m, collision sphere ~0.18m, doorway traversal checks (open past 55°), and an automatic camera recovery algorithm that teleports trapped viewpoints safely to room centers.
- `sceneBuilder.ts`: Scene graph manager coordinating walls with watertight carved voids, procedural floors, openings with hinged swing leaves, furniture items, and selection wireframes.
- `Viewport3D.tsx`: Interactive React component rendering the Three.js viewport, managing orbit/walkthrough modes, raycasting selection, and high-resolution PNG snapshot exports.
- `README.md`: This comprehensive English documentation file.

## Exposed Interfaces & Utilities
- `Viewport3D`: Forward-ref React 3D viewport component exposing `captureSnapshot()`.
- `computeEffectiveWallHeight`: Presentation cutaway algorithm.
- `createProceduralFurnitureMesh`: 3D procedural generator for catalog elements.
- `getProceduralMaterial`: Procedural PBR materials cache.
- `updateScene3D`: Synchronizes the 3D scene with design state.

## Local Dependencies & Environment Variables
- `three` library and core algorithms from `../core/geometry.js`, `../core/wallCarving.js`, `../core/collision.js`.
- Zero network dependencies, zero CDNs, zero external 3D asset downloads.

## Caveats & Implementation Notes
- All meshes are generated procedurally with shadow casting and receiving.
- In Walkthrough mode, the presentation cutaway is deactivated to provide realistic, immersive room enclosures.
