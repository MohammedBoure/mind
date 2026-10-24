# Core Computational & Algorithmic Engines (`interior-designer/src/core`)

## Architectural Role & Scope
This directory contains the central architectural computation engines for the MindSpace 2D/3D design application. It executes metric 2D coordinate geometry, planar cycle graph extraction for automatic room identification, boolean void carving for door and window cutouts in 3D walls, spatial collision detection with floor-covering clearance rules, 90-degree radial door swing envelope warnings, integer-cent Bill of Quantities (BoQ) computations, and alternative design delta comparisons.

## Itemized File Breakdown
- `geometry.ts`: High-precision metric geometric operations including Euclidean distance, grid snapping (0.1m), angle snapping (45°), line segment projection, ray-casting point-in-polygon tests, Shoelace polygon area calculations (accurate to 0.001 m²), and polygon ear-clipping triangulation.
- `roomDetection.ts`: Planar graph face-cycle extraction engine utilizing directed half-edges with angular sorting to automatically recognize closed rooms upon wall drawing/vertex movements, preserving user labels and floor finishes.
- `wallCarving.ts`: Watertight 3D cuboid segmentation engine that cuts genuine geometric voids into wall thickness for adjustable doors and windows without external CSG dependencies.
- `collision.ts`: 2D/3D Oriented Bounding Box (OBB) collision detector utilizing the Separating Axis Theorem (SAT). Implements clearance rules for thin decorative floor coverings (≤ 0.06m non-blocking), 90-degree radial door swing envelope warnings, and walkthrough player collision.
- `boqCalculator.ts`: Real-time Bill of Quantities engine computing net wall finish areas (accounting for openings subtractions), floor finish areas, opening schedules, and catalog item costs using integer cents.
- `alternatives.ts`: Design branching and side-by-side delta analysis system for comparing parallel layout and finish alternatives (Alternative A vs B vs C).
- `README.md`: This comprehensive English documentation file.

## Exposed Interfaces & Utilities
- `distance`, `snapToGrid`, `snapPointToAngle`, `calculatePolygonArea`, `triangulatePolygon` (from `geometry.ts`)
- `detectRooms(vertices, walls, existingRooms)` (from `roomDetection.ts`)
- `carveWallSegments(wall, pStart, pEnd, openings, effectiveHeight)` (from `wallCarving.ts`)
- `checkFurnitureCollision`, `checkDoorSwingClearance`, `checkWalkthroughCollision` (from `collision.ts`)
- `calculateBoQ(design)`, `formatCurrency(cents)` (from `boqCalculator.ts`)
- `cloneAlternative(base, name)`, `compareAlternatives(base, target)` (from `alternatives.ts`)

## Local Dependencies & Environment Variables
- Imports from `../types/plan.js` and `../types/boq.js`.
- Zero backend dependencies; zero external CDN dependencies.

## Caveats & Implementation Notes
- All mathematical coordinates operate in the metric system (meters).
- Financial math strictly uses integer cents (`number` without floating-point fraction).
- Wall carving creates clean axis-aligned box segments that eliminate vertex z-fighting and avoid heavy CSG mesh errors.
