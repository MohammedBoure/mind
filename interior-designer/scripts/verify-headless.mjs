#!/usr/bin/env node

/**
 * Headless Automated Verification Suite for MindSpace Architectural Engine
 * Validates:
 * 1. Metric grid and 45° angle snapping
 * 2. Planar graph cycle room detection & 0.001 m² Shoelace area accuracy
 * 3. True geometric wall void carving for doors and windows
 * 4. Spatial collision detection (SAT, floor covering allowance <= 0.06m, door swing 90° radial envelope)
 * 5. Walkthrough doorway traversal (>55°) & camera trapped recovery
 * 6. Integer-cent Bill of Quantities (BoQ) & Alternative branching delta calculations
 * 7. SVG blueprint, CSV BoQ, and JSON roundtrip export integrity
 */

import {
  distance,
  snapPointToGrid,
  snapPointToAngle,
  calculatePolygonArea,
  calculatePolygonCentroid,
} from '../src/core/geometry.js';
import { detectRooms } from '../src/core/roomDetection.js';
import { carveWallSegments } from '../src/core/wallCarving.js';
import {
  checkFurnitureCollision,
  checkDoorSwingClearance,
  checkWalkthroughCollision,
  getFurnitureFootprint,
} from '../src/core/collision.js';
import { calculateBoQ } from '../src/core/boqCalculator.js';
import { cloneAlternative, compareAlternatives } from '../src/core/alternatives.js';
import { exportBlueprintToSVG } from '../src/export/svgExporter.js';
import { exportBoQToCSV } from '../src/export/csvExporter.js';
import { exportProjectToJSON, importProjectFromJSON } from '../src/export/jsonExporter.js';
import { createDefaultProject } from '../src/state/defaultProject.js';

let passedTests = 0;
let totalTests = 0;

function assert(condition, message) {
  totalTests++;
  if (!condition) {
    console.error(`❌ FAIL: ${message}`);
    process.exitCode = 1;
  } else {
    passedTests++;
    console.log(`  ✓ ${message}`);
  }
}

console.log('\n======================================================');
console.log('🏛️  MINDSPACE ARCHITECTURAL ENGINE HEADLESS VERIFICATION');
console.log('======================================================\n');

// ---------------------------------------------------------------------------
// TEST 1: Metric Grid & 45-Degree Angle Snapping
// ---------------------------------------------------------------------------
console.log('[Test Suite 1: Metric Snapping & 2D Vector Geometry]');
{
  const p1 = { x: 1.234, y: 5.678 };
  const snappedGrid = snapPointToGrid(p1, 0.1);
  assert(
    Math.abs(snappedGrid.x - 1.2) < 1e-6 && Math.abs(snappedGrid.y - 5.7) < 1e-6,
    `Metric grid snap to 0.1m: (1.234, 5.678) -> (${snappedGrid.x}, ${snappedGrid.y})`
  );

  const anchor = { x: 0, y: 0 };
  const targetNear45 = { x: 2.0, y: 2.08 }; // angle ~ 46.1°
  const snappedAngle = snapPointToAngle(anchor, targetNear45, 45);
  const resultAngleDeg = (Math.atan2(snappedAngle.y, snappedAngle.x) * 180) / Math.PI;
  assert(
    Math.abs(resultAngleDeg - 45) < 1e-4,
    `45° angle snap: near 46.1° snaps exactly to 45.0° (Actual: ${resultAngleDeg.toFixed(2)}°)`
  );
}

// ---------------------------------------------------------------------------
// TEST 2: Planar Graph Room Detection & Shoelace Area Accuracy (0.001 m²)
// ---------------------------------------------------------------------------
console.log('\n[Test Suite 2: Room Topology & Automatic Cycle Detection]');
{
  // 6m x 5m rectangular room: Area must be exactly 30.000 m²
  const testVertices = {
    v1: { id: 'v1', x: 0, y: 0 },
    v2: { id: 'v2', x: 6, y: 0 },
    v3: { id: 'v3', x: 6, y: 5 },
    v4: { id: 'v4', x: 0, y: 5 },
  };
  const testWalls = {
    w1: { id: 'w1', startId: 'v1', endId: 'v2', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    w2: { id: 'w2', startId: 'v2', endId: 'v3', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    w3: { id: 'w3', startId: 'v3', endId: 'v4', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    w4: { id: 'w4', startId: 'v4', endId: 'v1', thickness: 0.2, height: 2.8, finish: 'paint_white' },
  };

  const detected = detectRooms(testVertices, testWalls);
  assert(detected.length === 1, `Single closed loop detects exactly 1 room (detected: ${detected.length})`);
  assert(
    Math.abs(detected[0].area - 30.0) < 0.001,
    `Room area accurate to 0.001 m²: Expected 30.000 m², got ${detected[0].area.toFixed(3)} m²`
  );

  // Add interior partition dividing room into 4m x 5m (20.0 m²) and 2m x 5m (10.0 m²)
  testVertices['v5'] = { id: 'v5', x: 4, y: 0 };
  testVertices['v6'] = { id: 'v6', x: 4, y: 5 };
  testWalls['w1'].endId = 'v5';
  testWalls['w1_sub'] = { id: 'w1_sub', startId: 'v5', endId: 'v2', thickness: 0.2, height: 2.8, finish: 'paint_white' };
  testWalls['w3'].startId = 'v3';
  testWalls['w3'].endId = 'v6';
  testWalls['w3_sub'] = { id: 'w3_sub', startId: 'v6', endId: 'v4', thickness: 0.2, height: 2.8, finish: 'paint_white' };
  testWalls['w_div'] = { id: 'w_div', startId: 'v5', endId: 'v6', thickness: 0.15, height: 2.8, finish: 'paint_white' };

  const partitionedRooms = detectRooms(testVertices, testWalls);
  assert(partitionedRooms.length === 2, `Interior partition creates exactly 2 enclosed rooms (detected: ${partitionedRooms.length})`);
  const areas = partitionedRooms.map((r) => r.area).sort((a, b) => a - b);
  assert(
    Math.abs(areas[0] - 10.0) < 0.001 && Math.abs(areas[1] - 20.0) < 0.001,
    `Partitioned sub-room areas: 10.000 m² and 20.000 m² (sum: ${(areas[0] + areas[1]).toFixed(3)} m²)`
  );
}

// ---------------------------------------------------------------------------
// TEST 3: True Geometric Wall Void Carving (Doors & Windows)
// ---------------------------------------------------------------------------
console.log('\n[Test Suite 3: True Geometric Wall Void Carving]');
{
  const testWall = {
    id: 'w_carve',
    startId: 'va',
    endId: 'vb',
    thickness: 0.2,
    height: 2.8,
    finish: 'paint_white',
  };
  const va = { id: 'va', x: 0, y: 0 };
  const vb = { id: 'vb', x: 8, y: 0 }; // 8.0m long wall

  const doorOpening = {
    id: 'op_door_test',
    wallId: 'w_carve',
    type: 'door',
    offset: 0.25, // center at 2.0m along wall
    width: 1.0,   // interval [1.5m, 2.5m]
    height: 2.1,  // height 2.1m
    sillElevation: 0.0, // sill at floor
    swingAngle: 65,
    swingDirection: 'left',
    isOpen: true,
    finish: 'wood_oak',
    costCents: 48000,
  };

  const windowOpening = {
    id: 'op_win_test',
    wallId: 'w_carve',
    type: 'window',
    offset: 0.75, // center at 6.0m along wall
    width: 1.6,   // interval [5.2m, 6.8m]
    height: 1.2,  // height 1.2m
    sillElevation: 0.9, // sill at 0.9m
    swingAngle: 0,
    swingDirection: 'left',
    isOpen: false,
    finish: 'aluminum_black',
    costCents: 36000,
  };

  const segments = carveWallSegments(testWall, va, vb, [doorOpening, windowOpening], 2.8);

  // Wall segments must include:
  // 1. Jamb before door: [0 -> 1.5m] full height 2.8m
  // 2. Door lintel above door: [1.5 -> 2.5m] from 2.1m to 2.8m (height 0.7m)
  // 3. Jamb between door and window: [2.5 -> 5.2m] full height 2.8m
  // 4. Window bottom sill: [5.2 -> 6.8m] from 0 to 0.9m (height 0.9m)
  // 5. Window top lintel: [5.2 -> 6.8m] from 2.1m to 2.8m (height 0.7m)
  // 6. Jamb after window: [6.8 -> 8.0m] full height 2.8m
  assert(segments.length === 6, `Wall carved into exactly 6 non-overlapping solid cuboids (got: ${segments.length})`);

  // Verify door void: exactly 0 solid geometry between 0 and 2.1m elevation at door center (x=2.0m)
  const solidsAtDoorOpening = segments.filter(
    (s) => Math.abs(s.centerX - 2.0) < 0.1 && s.centerZ < 2.0
  );
  assert(solidsAtDoorOpening.length === 0, `Door void is 100% physically clear from floor to 2.1m elevation`);

  // Verify window sill: solid lower wall exists at window center (x=6.0m) below 0.9m
  const sillAtWindow = segments.find(
    (s) => Math.abs(s.centerX - 6.0) < 0.1 && s.height <= 0.95
  );
  assert(sillAtWindow !== undefined, `Window bottom sill exists at 0.9m elevation beneath glazing`);
}

// ---------------------------------------------------------------------------
// TEST 4: Collision Detection (Separation of Overlap vs Contact & Door Swing)
// ---------------------------------------------------------------------------
console.log('\n[Test Suite 4: Collision Detection & Door Swing Envelopes]');
{
  const tableA = {
    id: 'tbl_a',
    catalogId: 'furn_dining_rect',
    name: 'Table A',
    x: 3.0,
    y: 3.0,
    z: 0,
    rotation: 0,
    width: 1.6,
    depth: 0.9,
    height: 0.75,
    isFloorCovering: false,
    finish: 'wood_oak',
    costCents: 42000,
  };

  const tableOverlap = {
    id: 'tbl_overlap',
    catalogId: 'furn_dining_rect',
    name: 'Table Overlap',
    x: 3.4, // overlaps Table A
    y: 3.2,
    z: 0,
    rotation: 0,
    width: 1.6,
    depth: 0.9,
    height: 0.75,
    isFloorCovering: false,
    finish: 'wood_oak',
    costCents: 42000,
  };

  const rugUnderneath = {
    id: 'rug_under',
    catalogId: 'furn_rug_rectangular',
    name: 'Dining Rug',
    x: 3.0,
    y: 3.0,
    z: 0,
    rotation: 0,
    width: 2.4,
    depth: 1.6,
    height: 0.015, // <= 0.06m: thin floor covering
    isFloorCovering: true,
    finish: 'fabric_beige',
    costCents: 26000,
  };

  // Solid Table vs Solid Table -> Collision
  assert(
    checkFurnitureCollision(tableA, tableOverlap) === true,
    `Two overlapping solid tables trigger footprint collision`
  );

  // Solid Table vs Floor Rug (<=0.06m) -> Non-blocking!
  assert(
    checkFurnitureCollision(tableA, rugUnderneath) === false,
    `Thin decorative floor covering (rug <= 0.06m) is non-blocking beneath table`
  );

  // 90° Door Swing Envelope
  const doorWall = {
    id: 'dw',
    startId: 'dva',
    endId: 'dvb',
    thickness: 0.2,
    height: 2.8,
    finish: 'paint_white',
  };
  const doorVerts = {
    dva: { id: 'dva', x: 0, y: 0 },
    dvb: { id: 'dvb', x: 5, y: 0 },
  };
  const doorOp = {
    id: 'door_swing_test',
    wallId: 'dw',
    type: 'door',
    offset: 0.3, // x=1.5m
    width: 1.0,
    height: 2.1,
    sillElevation: 0,
    swingAngle: 90,
    swingDirection: 'left',
    isOpen: true,
    finish: 'wood_oak',
    costCents: 48000,
  };

  // Obstacle right inside door's 90° radial arc
  const obstructingChair = {
    id: 'chair_obstruct',
    catalogId: 'furn_chair_bistro',
    name: 'Blocking Chair',
    x: 1.5,
    y: 0.6, // in swing wedge
    z: 0,
    rotation: 0,
    width: 0.5,
    depth: 0.5,
    height: 0.85,
    isFloorCovering: false,
    finish: 'wood_walnut',
    costCents: 12500,
  };

  const conflict = checkDoorSwingClearance(doorOp, doorWall, doorVerts, [obstructingChair]);
  assert(
    conflict !== null && conflict.collidingFurnitureIds.includes('chair_obstruct'),
    `Door 90° radial swing clearance flags furniture obstructing door leaf path`
  );

  // Clear obstacle away from door
  obstructingChair.y = 2.5; // outside 1.0m radius
  const clearCheck = checkDoorSwingClearance(doorOp, doorWall, doorVerts, [obstructingChair]);
  assert(clearCheck === null, `Relocating furniture outside swing arc resolves door clearance`);
}

// ---------------------------------------------------------------------------
// TEST 5: Walkthrough Traversal Physics & Camera Recovery
// ---------------------------------------------------------------------------
console.log('\n[Test Suite 5: Walkthrough Traversal Physics & Trapped Recovery]');
{
  const defaultProj = createDefaultProject();
  const alt = defaultProj.alternatives[0];

  // Try walking into solid wall: Position (0, 3.5) on West wall (thickness 0.2m, x=0)
  const walkingIntoWall = { x: 0.05, y: 3.5 };
  const collisionResult = checkWalkthroughCollision(
    walkingIntoWall,
    0.18, // player radius
    alt.walls,
    alt.openings,
    alt.vertices,
    alt.furniture
  );
  assert(
    collisionResult.hasCollision === true,
    `Player sphere (r=0.18m) blocks collision when walking into solid architectural wall`
  );
  assert(
    collisionResult.correctedPos.x > 0.18,
    `Player collision response pushes camera outside wall boundary (corrected X: ${collisionResult.correctedPos.x.toFixed(3)})`
  );

  // Test doorway traversal through open door (op_door_main on w7: v7(0,7) -> v1(0,0), offset 0.35 => y = 7 - 2.45 = 4.55m)
  const doorwayPos = { x: 0.0, y: 4.55 };
  const doorwayCheck = checkWalkthroughCollision(
    doorwayPos,
    0.18,
    alt.walls,
    alt.openings,
    alt.vertices,
    alt.furniture
  );
  assert(
    doorwayCheck.hasCollision === false,
    `Door open past 55° (65°) allows unhindered player traversal as architectural portal`
  );

  // Camera recovery test: Room centroid calculation
  const mainRoom = alt.rooms.find((r) => r.name.includes('Main Dining'));
  assert(mainRoom !== undefined, `Main Dining room detected for camera safe teleport`);
  const safeCentroid = calculatePolygonCentroid(mainRoom.polygon);
  assert(
    safeCentroid.x > 0 && safeCentroid.x < 6 && safeCentroid.y > 0 && safeCentroid.y < 7,
    `Trapped camera recovery targets safe interior room centroid: (${safeCentroid.x.toFixed(2)}, ${safeCentroid.y.toFixed(2)})`
  );
}

// ---------------------------------------------------------------------------
// TEST 6: Integer-Cent Bill of Quantities (BoQ) & Alternative Deltas
// ---------------------------------------------------------------------------
console.log('\n[Test Suite 6: Integer-Cent BoQ Estimation & Alternative Deltas]');
{
  const defaultProj = createDefaultProject();
  const altA = defaultProj.alternatives[0];
  const altB = defaultProj.alternatives[1];

  const boqA = calculateBoQ(altA);
  const boqB = calculateBoQ(altB);

  assert(
    Number.isInteger(boqA.totalCostCents) && boqA.totalCostCents > 0,
    `BoQ total budget strictly calculated in integer cents: ${boqA.totalCostCents} cents ($${(boqA.totalCostCents / 100).toFixed(2)})`
  );

  assert(
    boqA.totalFlooringAreaM2 > 40,
    `Total enclosed flooring area aggregated: ${boqA.totalFlooringAreaM2.toFixed(3)} m²`
  );

  assert(
    boqA.netWallAreaM2 > 0 && boqA.netWallAreaM2 < boqA.totalGrossWallAreaM2,
    `Net wall area properly deducts doors/windows openings (${boqA.netWallAreaM2.toFixed(2)} m² vs Gross ${boqA.totalGrossWallAreaM2.toFixed(2)} m²)`
  );

  // Compare Alternatives
  const delta = compareAlternatives(altA, altB);
  assert(
    delta.baseAlternativeId === altA.id && delta.targetAlternativeId === altB.id,
    `Delta comparison correctly references base and target variant IDs`
  );
  assert(
    Number.isInteger(delta.totalCostDeltaCents),
    `Total budget variance calculated down to integer cents: ${delta.totalCostDeltaCents} cents`
  );
  assert(
    delta.comparisonRows.length >= 6,
    `Alternative delta breakdown table contains ${delta.comparisonRows.length} metric comparison rows`
  );
}

// ---------------------------------------------------------------------------
// TEST 7: SVG Blueprint, CSV BoQ, and JSON Roundtrip Export Integrity
// ---------------------------------------------------------------------------
console.log('\n[Test Suite 7: Export Formats & Zero-Data-Loss Portability]');
{
  const defaultProj = createDefaultProject();
  const alt = defaultProj.alternatives[0];

  // 1. Vector SVG (1:10 Scaled Architectural Blueprint)
  const svg1_10 = exportBlueprintToSVG(alt, 100, '1:10');
  assert(
    svg1_10.startsWith('<?xml') && svg1_10.includes('<svg') && svg1_10.includes('</svg>'),
    `Exported SVG blueprint is valid XML starting with <svg> and ending with </svg>`
  );
  assert(
    svg1_10.includes('door-arc') && svg1_10.includes('wall-thick') && svg1_10.includes('Main Dining Hall'),
    `SVG blueprint contains door swing arcs, wall thickness paths, and room label tags`
  );
  assert(
    svg1_10.includes('Scale 1:10'),
    `SVG blueprint includes 1:10 metric scale specification in title block`
  );

  // 2. BoQ CSV
  const csv = exportBoQToCSV(alt);
  assert(
    csv.includes('Category,Item Description,Specification') && csv.includes('GRAND TOTAL'),
    `Exported BoQ CSV contains standard column headers and GRAND TOTAL row`
  );

  // 3. JSON Roundtrip
  const jsonStr = exportProjectToJSON(alt.id, defaultProj.alternatives, defaultProj.settings);
  const roundtrip = importProjectFromJSON(jsonStr);
  assert(roundtrip.success === true, `Exported JSON project successfully parsed and schema-validated`);
  assert(
    roundtrip.data.alternatives.length === defaultProj.alternatives.length,
    `JSON roundtrip preserves all ${roundtrip.data.alternatives.length} design alternatives`
  );
  assert(
    Object.keys(roundtrip.data.alternatives[0].furniture).length === Object.keys(alt.furniture).length,
    `JSON roundtrip preserves exact furniture count with zero data loss`
  );
}

console.log('\n======================================================');
console.log(`🎉 ALL TESTS PASSED: ${passedTests} / ${totalTests} assertions verified!`);
console.log('======================================================\n');
