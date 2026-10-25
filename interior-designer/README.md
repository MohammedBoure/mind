# MindSpace — 2D/3D Interior & Commercial Space Studio (`interior-designer`)

## 1. Overarching Architectural Role & Scope
MindSpace is a production-grade, local-first web application designed for high-precision 2D architectural blueprint design and real-time interactive 3D commercial space visualization. It is architected under strict constraints:
- **100% Web-Based & Zero Backend**: No backend services, no server database, and no login required.
- **100% Offline After Initialization**: Zero external CDN calls and zero external 3D model asset downloads. All 18 parametric interior elements and PBR materials (oak parquet, terrazzo, subway tiles, concrete, brass, glass) are mathematically synthesized in-memory.
- **Bi-Directional Synchronized Viewports**: Top-down 2D vector blueprint canvas paired with a navigable WebGL 3D environment with unified selection and presentation cutaway modes.
- **Zero-Loss Persistence**: 100-step undo/redo stack with continuous debounced browser `localStorage` synchronization.

## 2. Directory & File Breakdown
- `package.json`: NPM package definition, scripts (`dev`, `build`, `preview`, `test`), and dependencies (`react`, `react-dom`, `three`, `lucide-react`, `tailwindcss`, `vite`, `tsx`).
- `tsconfig.json`, `tsconfig.node.json`: TypeScript compiler configurations for ES2022 and React JSX.
- `vite.config.ts`: Vite bundling and HMR configuration with `@tailwindcss/vite` and `@vitejs/plugin-react`.
- `index.html`: Web entrypoint document with viewport meta, dark canvas body styling, and favicon link.
- `public/`:
  - `favicon.svg`: Vector icon for the architectural studio.
  - `README.md`: English documentation for static assets.
- `scripts/`:
  - `verify-headless.mjs`: Automated headless verification script testing all 7 core mathematical, topological, and export subsystems.
  - `README.md`: English documentation for verification suites.
- `src/`:
  - `main.tsx`: React mounting entrypoint.
  - `App.tsx`: Central workspace layout integrating navbar, split viewports, inspector, and modals.
  - `index.css`: Tailwind CSS imports and custom dark scrollbars.
  - `types/`:
    - `plan.ts`: Core geometric interfaces (`Point2D`, `Wall`, `Opening`, `Room`, `FurnitureItem`, `AlternativeDesign`, `SelectionState`).
    - `boq.ts`: Integer-cent financial schedule types (`BoQItem`, `BoQSummary`, `AlternativeDelta`).
    - `catalog.ts`: Taxonomy and parametric catalog schemas.
    - `README.md`: English documentation for data contracts.
  - `core/`:
    - `geometry.ts`: Metric snapping (0.1m, 45°), polygon Shoelace area (0.001 m²), and triangulation.
    - `roomDetection.ts`: Planar cycle half-edge graph traversal for automatic enclosed room detection.
    - `wallCarving.ts`: Watertight 3D cuboid segmentation cutting genuine void openings into wall thickness.
    - `collision.ts`: 2D/3D SAT footprint collision, floor covering allowance (≤0.06m), and 90° radial door swing envelopes.
    - `boqCalculator.ts`: Real-time Bill of Quantities schedule with integer-cent accuracy.
    - `alternatives.ts`: Design variant branching, cloning, and side-by-side delta schedules.
    - `README.md`: English documentation for algorithmic engines.
  - `catalog/`:
    - `items.ts`: 18 Parametric commercial items (dining tables, chairs, counters, booths, screens, rugs, planters).
    - `textures.ts`: 100% procedural HTML5 canvas texture generators (wood, terrazzo, tile, concrete, fabric).
    - `README.md`: English documentation for procedural assets.
  - `engine2d/`:
    - `renderer2d.ts`: Pure Canvas 2D rendering pipeline (grid, walls, openings, swing arcs, dimension lines, furniture footprints).
    - `BlueprintCanvas.tsx`: High-DPI interactive canvas component with pan, zoom, snapping, and dragging.
    - `README.md`: English documentation for 2D blueprint engine.
  - `engine3d/`:
    - `materials.ts`: Procedural PBR materials factory backed by canvas textures.
    - `proceduralMeshes.ts`: Parametric 3D mesh constructors for all 18 catalog elements.
    - `cutaway.ts`: Dynamic presentation cutaway lowering camera-facing perimeter walls to low plinths (0.25m).
    - `walkthrough.ts`: First-person traversal controller (WASD + mouse look, 1.65m eye level, doorway clearance > 55°, trapped camera recovery).
    - `sceneBuilder.ts`: Scene graph manager coordinating walls with true carved voids, floors, and furniture.
    - `Viewport3D.tsx`: Three.js viewport hosting orbit and walkthrough navigation, raycasting selection, and snapshot export.
    - `README.md`: English documentation for 3D graphics engine.
  - `components/`:
    - `TopNavbar.tsx`: Variant selector, view toggles, walkthrough button, cutaway toggle, undo/redo, live BoQ pill.
    - `Toolbar2D.tsx`: Mode switching (Select, Wall, Door, Window, Catalog, Delete).
    - `CatalogDrawer.tsx`: Filterable 18-item catalog drawer.
    - `PropertyInspector.tsx`: Real-time parametric sidebar for walls, doors, windows, furniture, and rooms.
    - `BoQModal.tsx`: Comprehensive Bill of Quantities schedule with integer-cent CSV export.
    - `AlternativesModal.tsx`: Side-by-side design branch comparison and variance analysis dialog.
    - `ExportModal.tsx`: Export hub (1:50 SVG blueprint, BoQ CSV, JSON backup, and 3D PNG snapshot).
    - `README.md`: English documentation for UI components.
  - `state/`:
    - `defaultProject.ts`: Preloaded commercial cafe/bistro showcase model.
    - `projectStore.ts`: Central React state store, 100-step undo/redo, and localStorage auto-save.
    - `README.md`: English documentation for state persistence.
  - `export/`:
    - `svgExporter.ts`: Scaled 1:10 vector SVG blueprint generator.
    - `csvExporter.ts`: Itemized BoQ CSV generator.
    - `jsonExporter.ts`: JSON project serialization and schema-validated restore.
    - `README.md`: English documentation for export generators.

## 3. Quick Start & Setup Instructions

### Standard Installation
Navigate to the `interior-designer` directory and install standard dependencies:

```bash
cd interior-designer
npm install
```

### Launch in Any Modern Web Browser
Run the local Vite development server with a single command:

```bash
npm run dev
```

Open `http://localhost:3000` in Google Chrome, Mozilla Firefox, Microsoft Edge, or Apple Safari.

### Run Automated Headless Verification Suite
Run the comprehensive test suite verifying snapping, room detection, wall carving, collision, and exports:

```bash
npm test
```

### Production Build
Generate an optimized static production bundle in `dist/`:

```bash
npm run build
```

## 4. Key Architectural Features & Caveats
- **Metric System**: All distances, dimensions, and coordinates are strictly in meters ($m$).
- **Integer Cents**: All financial amounts are stored as integer cents to prevent floating-point rounding errors.
- **Floor Covering Clearance**: Items with `isFloorCovering = true` or height $\le 0.06$m (such as area rugs) are classified as non-blocking floor finishes, allowing tables and chairs to be placed directly over them.
- **Doorway Traversal**: In walkthrough mode, doors act as physical barriers unless swung open past $55^\circ$.
- **Camera Recovery**: If a geometric mutation traps the first-person walkthrough camera inside a solid wall, the engine automatically teleports the viewpoint back to the center of the largest cleared room.
