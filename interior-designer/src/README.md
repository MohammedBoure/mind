# Source Root Directory (`interior-designer/src`)

## Architectural Role & Scope
This directory is the root TypeScript source tree for the MindSpace 2D/3D interior and commercial space design web application. It integrates the root React application, high-level UI layout orchestration, global stylesheet styles, and coordinates sub-engines across 2D blueprint rendering, 3D WebGL graphics, spatial intelligence, parametric catalogs, and export generators.

## Itemized File Breakdown
- `main.tsx`: Application bootstrapping entrypoint that mounts React into the root DOM node with `React.StrictMode`.
- `App.tsx`: Top-level application layout component coordinating the navigation header, split 2D/3D workspace canvas, contextual property inspector, and floating modals (BoQ, Alternatives, Export).
- `index.css`: Global design system stylesheet defining Tailwind CSS utilities, dark theme color variables, and custom scrollbars.
- `types/`: Domain TypeScript types (geometry, structure, catalog, BoQ schedules).
- `core/`: Algorithmic engines (metric geometry, planar room cycle detection, watertight wall carving, SAT collision, BoQ financial math, alternative deltas).
- `catalog/`: 18-element parametric furniture catalog and procedural canvas texture generators.
- `engine2d/`: High-DPI HTML5 canvas 2D blueprint interactive drawing engine.
- `engine3d/`: Three.js real-time 3D interactive viewport with presentation cutaway plinths and first-person walkthrough.
- `components/`: Modular UI widgets (TopNavbar, Toolbar2D, CatalogDrawer, PropertyInspector, BoQModal, AlternativesModal, ExportModal).
- `state/`: Global design store, undo/redo stacks, auto-save persistence, and the default commercial cafe showcase model.
- `export/`: Vector SVG blueprint, BoQ CSV, and schema-validated JSON backup exporters.
- `README.md`: This comprehensive English documentation file.

## Exposed Interfaces & Utilities
- `App`: Main React component.

## Local Dependencies & Environment Variables
- React 19, ReactDOM, Three.js, Lucide React, Tailwind CSS.
- Completely offline with zero backend servers and zero external CDN connections.

## Caveats & Implementation Notes
- Designed for zero-lag 60fps rendering in modern web browsers (Chrome, Edge, Firefox, Safari).
- Operates entirely locally with instant auto-save to browser `localStorage`.
