# Data Portability & Export Generators (`interior-designer/src/export`)

## Architectural Role & Scope
This directory implements zero-data-loss export and import modules for the MindSpace studio. It generates scaled vector blueprints, itemized CSV financial schedules for construction estimation, schema-validated JSON project backup files, and camera snapshots.

## Itemized File Breakdown
- `svgExporter.ts`: Synthesizes 1:10 architectural-standard vector SVG blueprints (100 px/meter, with configurable scale factors) containing metric coordinate grids, room boundary fills with square-meter tags, walls with core and thickness strokes, dimension markers, door swing arcs, window double-lines, furniture footprints, and title blocks.
- `csvExporter.ts`: Synthesizes Bill of Quantities (BoQ) spreadsheets formatted with item descriptions, specifications, metric quantities, units, and integer-cent prices converted to decimal dollars, complete with category subtotals and grand totals.
- `jsonExporter.ts`: Serializes and deserializes the full multi-alternative project tree with schema sanitization for cross-browser backup and restore.
- `README.md`: This comprehensive English documentation file.

## Exposed Interfaces & Utilities
- `exportBlueprintToSVG(design, scale)`: Returns SVG XML markup string.
- `exportBoQToCSV(design)`: Returns CSV text string.
- `exportProjectToJSON(activeAltId, alternatives, settings)`: Serializes project state.
- `importProjectFromJSON(jsonString)`: Validates and sanitizes imported JSON project state.

## Local Dependencies & Environment Variables
- Core types from `../types/plan.js` and financial calculations from `../core/boqCalculator.js`.
- Zero backend dependencies; zero external CDN dependencies.

## Caveats & Implementation Notes
- All SVG dimensions scale linearly with metric coordinates.
- CSV output formats numbers cleanly with quotes to avoid delimiter splitting issues in spreadsheet software (Excel, LibreOffice, Google Sheets).
