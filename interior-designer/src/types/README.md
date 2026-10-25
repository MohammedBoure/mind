# Data Types Directory (`interior-designer/src/types`)

## Architectural Role & Scope
This directory defines the foundational TypeScript type definitions, domain schemas, and data interfaces for the MindSpace 2D/3D interior design engine. It establishes the contracts for planar geometry, architectural openings, room topology, parametric furniture items, design alternatives, and the integer-cents Bill of Quantities (BoQ) financial schedules.

## Itemized File Breakdown
- `plan.ts`: Core geometric interfaces including `Point2D` (in meters), `Wall`, `Opening` (doors and windows with sill height and swing angles), `Room` (closed polygon topology, area, perimeter, finishes), `FurnitureItem`, `AlternativeDesign`, and `SelectionState`.
- `boq.ts`: Cost schedules and financial models including `BoQItem`, `BoQSummary`, and `AlternativeDelta` representing variance analysis between design branches with integer cents precision.
- `catalog.ts`: Definitions for 16+ parametric interior and commercial elements, category taxonomy, procedural model types, and dimensional defaults.
- `README.md`: This comprehensive English documentation file.

## Exposed Interfaces & Schemas
- `Point2D`: Coordinates in meters $(x, y)$.
- `Wall`: Two-point wall connection with thickness, height, and finish.
- `Opening`: Host wall reference, normalized offset $[0, 1]$, width, height, sill elevation, swing angle, swing direction.
- `Room`: Auto-detected closed cycle with Shoelace area calculation ($m^2$), perimeter, and floor finish.
- `FurnitureItem`: Bounding footprint $(x, y, z)$, dimensions, rotation, `isFloorCovering` flag, and finish.
- `BoQSummary`: Integer-cent financial aggregations and itemized schedules.

## Local Dependencies & Environment Variables
- Pure TypeScript type declarations.
- No external npm runtime dependencies or environment variables required.

## Caveats & Implementation Notes
- All spatial coordinates, offsets, and dimensions are strictly in **meters**.
- All monetary amounts are strictly in **integer cents** (e.g., $100.00 is represented as `10000`) to completely eliminate floating-point financial drift.
