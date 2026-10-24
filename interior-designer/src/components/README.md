# User Interface Components (`interior-designer/src/components`)

## Architectural Role & Scope
This directory contains modular React UI components that comprise the MindSpace design studio layout. It provides the top navigation bar, 2D architectural sketch toolbar, 18-item parametric furniture drawer, real-time property inspector, Bill of Quantities schedule dialog, multi-alternative delta comparison modal, and asset export/restore dialogues.

## Itemized File Breakdown
- `TopNavbar.tsx`: Header bar with design variant dropdown, split/2D/3D layout toggles, first-person walkthrough button, presentation cutaway toggle, 100-step undo/redo buttons, live integer-cent BoQ budget badge, and export action.
- `Toolbar2D.tsx`: Floating action bar for switching 2D editor modes (Select, Draw Wall, Insert Door, Insert Window, Open Catalog, and Delete Selected).
- `CatalogDrawer.tsx`: Filterable drawer displaying all 18 parametric items grouped by taxonomy (Dining, Seating, Counters, Partitions, Lighting, Rugs, Office, and Decor) with dimensions and integer-cent pricing.
- `PropertyInspector.tsx`: Contextual real-time sidebar providing parametric inputs for selected walls (thickness, height, finishes), openings (dimensions, sill elevation, swing angles, hinge side, collision warnings), furniture (rotation gizmo, dimensions, pricing, rug non-blocking clearance indicators), and rooms (name, area readout in m², floor finish materials).
- `BoQModal.tsx`: Comprehensive Bill of Quantities modal presenting KPI summaries (Flooring area, net wall finish area, door/window counts, furniture count, grand total budget), categorized item tables, and CSV export.
- `AlternativesModal.tsx`: Side-by-side design branch comparison modal calculating variance deltas between Alternative A and Alternative B, with tools to create new layout branches.
- `ExportModal.tsx`: Asset export dialog generating scaled 1:10 vector SVG blueprints, BoQ CSV schedules, cross-browser JSON backup files, 3D WebGL PNG canvas snapshots, and file upload restoration.
- `README.md`: This comprehensive English documentation file.

## Exposed Interfaces & Utilities
- All files export React Functional Components.

## Local Dependencies & Environment Variables
- React 19, Lucide React icons, and core engines (`boqCalculator.js`, `alternatives.js`, `svgExporter.js`, `csvExporter.js`, `jsonExporter.js`).
- Zero backend dependencies; zero external CDN dependencies.

## Caveats & Implementation Notes
- All monetary inputs and displays communicate with the integer-cent state store, formatting numbers dynamically without floating-point inaccuracies.
- Closing or opening modals does not interrupt background WebGL rendering or 2D canvas states.
