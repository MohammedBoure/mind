# Procedural Catalog & Textures (`interior-designer/src/catalog`)

## Architectural Role & Scope
This directory houses the built-in catalog of 18 parametric interior, commercial, and hospitality items, along with 100% procedural material and texture generators. It guarantees zero external asset dependencies: all 3D furniture meshes, wood grains, subway tiles, terrazzo chip matrices, and woven fabric textures are mathematically synthesized in-memory via Three.js primitives and HTML5 2D Canvas routines.

## Itemized File Breakdown
- `items.ts`: Definitions for 18 modern commercial and interior architectural items (dining tables, bistro seating, service counters, fluted booths, acoustic partitions, dome pendants, area rugs, planters, executive desks, task chairs, and showcases), complete with dimensional envelopes, non-blocking floor covering classification (`isFloorCovering`), finishes, and prices stored in integer cents.
- `textures.ts`: Procedural canvas texture generators for oak parquet, walnut timber, speckled mineral terrazzo, polished concrete, beveled subway tiles, and cross-hatch upholstery fabrics.
- `README.md`: This comprehensive English documentation file.

## Exposed Interfaces & Utilities
- `CATALOG_ITEMS`: Array of 18 parametric catalog definitions.
- `CATALOG_MAP`: Fast lookup map indexed by item ID.
- `generateWoodTexture(isWalnut)`: Synthesizes procedural wood grain planks with bevel grooves.
- `generateTerrazzoTexture()`: Synthesizes polished cream matrix with organic multi-colored mineral aggregate chips.
- `generateConcreteTexture()`: Synthesizes industrial polished concrete with mottled noise.
- `generateTileTexture()`: Synthesizes offset subway tile grid with dark recessed grout lines.
- `generateFabricTexture(color)`: Synthesizes woven fabric threads.

## Local Dependencies & Environment Variables
- Uses `three` for `CanvasTexture` wrapping.
- Zero network dependencies, zero CDN dependencies, zero external model downloads.

## Caveats & Implementation Notes
- All item costs are specified in integer cents to ensure zero floating-point rounding errors.
- Floor coverings (e.g. rugs with thickness $\le 0.06$m) have `isFloorCovering: true`, enabling permissible placement of chairs and tables on top without triggering collision blocks.
