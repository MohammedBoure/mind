# 2D Blueprint Vector Engine (`interior-designer/src/engine2d`)

## Architectural Role & Scope
This directory implements the high-performance 2D architectural blueprint drawing canvas and rendering pipeline. It translates metric space coordinates into crisp vector graphics on high-DPI screens, handling mouse/touch pan, smooth zoom centered at the cursor, point-to-point wall sketching with 0.1m and 45-degree angle snapping, vertex manipulation, host wall opening placement, furniture dragging/rotation, and visual alerts for door swing clearances.

## Itemized File Breakdown
- `renderer2d.ts`: Pure Canvas 2D rendering pipeline executing layers for metric grid, room polygon fills with square-meter tags, walls with true thickness and dimension strings, openings with true void cuts, 90-degree radial door swing arcs, and furniture bounding footprints with collision indicators.
- `BlueprintCanvas.tsx`: Interactive React component hosting the canvas element, managing pointer events, magnetic snapping, hit testing, drag-to-move vertex topology updates, keyboard shortcuts (`Esc`, `Delete`, `R` for rotation), and synchronized bi-directional selection with the 3D viewport.
- `README.md`: This comprehensive English documentation file.

## Exposed Interfaces & Utilities
- `renderBlueprint2D`: Core canvas rendering entrypoint.
- `worldToScreen`, `screenToWorld`: Cartesian world meters $\leftrightarrow$ viewport screen pixels transformation utilities.
- `BlueprintCanvas`: Fully interactive React canvas component.

## Local Dependencies & Environment Variables
- React 19, Lucide React icons, and core geometry math from `../core/geometry.js` and `../core/collision.js`.
- Zero backend dependencies; zero external CDN dependencies.

## Caveats & Implementation Notes
- World coordinates are in meters $(x, y)$. In the 2D blueprint, the standard Cartesian convention is preserved with positive $Y$ pointing upwards, which is translated to inverted screen coordinates during canvas rendering.
- When dragging a vertex, all attached walls move synchronously, triggering real-time room cycle recalculation without tearing topology.
