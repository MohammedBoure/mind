# Verification Scripts Directory (`interior-designer/scripts`)

## Architectural Role & Scope
This directory contains automated headless verification tools and test suites that validate the mathematical, topological, spatial, and export integrity of the MindSpace design studio.

## Itemized File Breakdown
- `verify-headless.mjs`: Automated verification script executing 7 comprehensive test suites covering metric grid/angle snapping, planar graph room detection with 0.001 m² Shoelace area accuracy, true geometric 3D wall void carving, SAT collision detection with floor covering exemptions (≤ 0.06m), 90-degree radial door swing envelopes, walkthrough doorway traversal (>55°) and trapped camera recovery, integer-cent Bill of Quantities math, and SVG/CSV/JSON export integrity.
- `README.md`: This comprehensive English documentation file.

## Execution
Run this verification script directly using Node.js:

```bash
node scripts/verify-headless.mjs
```

Or via package.json script:

```bash
npm test
```

## Dependencies & Environment Variables
- Standard Node.js v18+ runtime with ECMAScript module (`.mjs`) support.
- Zero external runtime test runners required; runs completely offline.

## Caveats & Implementation Notes
- Exits with return code 0 on complete test pass and code 1 on any assertion failure.
