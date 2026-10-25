/**
 * Default Architectural Showcase Project
 * Preloads a commercial cafe/bistro with multiple closed rooms,
 * doors, windows, and procedural furniture to showcase all features immediately.
 */

import { AlternativeDesign, ProjectSettings, Point2D, Wall, Opening, FurnitureItem } from '../types/plan.js';
import { detectRooms } from '../core/roomDetection.js';

export function createDefaultProject(): {
  activeAlternativeId: string;
  alternatives: AlternativeDesign[];
  settings: ProjectSettings;
} {
  // Vertices for Cafe Blueprint:
  // Perimeter: (0,0) to (10,0) to (10,7) to (0,7)
  // Interior Wall dividing Main Dining from Service/Kitchen: x=6 from y=0 to y=7
  // Interior Wall dividing Kitchen from Restroom: y=4 from x=6 to x=10
  const vertices: Record<string, Point2D> = {
    v1: { id: 'v1', x: 0, y: 0 },
    v2: { id: 'v2', x: 6, y: 0 },
    v3: { id: 'v3', x: 10, y: 0 },
    v4: { id: 'v4', x: 10, y: 4 },
    v5: { id: 'v5', x: 10, y: 7 },
    v6: { id: 'v6', x: 6, y: 7 },
    v7: { id: 'v7', x: 0, y: 7 },
    v8: { id: 'v8', x: 6, y: 4 }, // interior intersection
  };

  const walls: Record<string, Wall> = {
    w1: { id: 'w1', startId: 'v1', endId: 'v2', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    w2: { id: 'w2', startId: 'v2', endId: 'v3', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    w3: { id: 'w3', startId: 'v3', endId: 'v4', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    w4: { id: 'w4', startId: 'v4', endId: 'v5', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    w5: { id: 'w5', startId: 'v5', endId: 'v6', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    w6: { id: 'w6', startId: 'v6', endId: 'v7', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    w7: { id: 'w7', startId: 'v7', endId: 'v1', thickness: 0.2, height: 2.8, finish: 'paint_white' },
    // Interior dividing walls
    w8: { id: 'w8', startId: 'v2', endId: 'v8', thickness: 0.15, height: 2.8, finish: 'wood_panel' },
    w9: { id: 'w9', startId: 'v8', endId: 'v6', thickness: 0.15, height: 2.8, finish: 'wood_panel' },
    w10: { id: 'w10', startId: 'v8', endId: 'v4', thickness: 0.15, height: 2.8, finish: 'paint_white' },
  };

  // Openings (Doors & Windows)
  const openings: Record<string, Opening> = {
    // Main Entrance Door on West wall (w7)
    op_door_main: {
      id: 'op_door_main',
      wallId: 'w7',
      type: 'door',
      offset: 0.35,
      width: 1.0,
      height: 2.2,
      sillElevation: 0,
      swingAngle: 65, // swung open > 55° for traversal!
      swingDirection: 'left',
      isOpen: true,
      finish: 'aluminum_black',
      costCents: 65000,
    },
    // Front Street Windows on South wall (w1)
    op_win_south1: {
      id: 'op_win_south1',
      wallId: 'w1',
      type: 'window',
      offset: 0.35,
      width: 1.8,
      height: 1.4,
      sillElevation: 0.8,
      swingAngle: 0,
      swingDirection: 'left',
      isOpen: false,
      finish: 'aluminum_black',
      costCents: 45000,
    },
    op_win_south2: {
      id: 'op_win_south2',
      wallId: 'w1',
      type: 'window',
      offset: 0.75,
      width: 1.8,
      height: 1.4,
      sillElevation: 0.8,
      swingAngle: 0,
      swingDirection: 'left',
      isOpen: false,
      finish: 'aluminum_black',
      costCents: 45000,
    },
    // Interior Service Door (w9)
    op_door_kitchen: {
      id: 'op_door_kitchen',
      wallId: 'w9',
      type: 'door',
      offset: 0.5,
      width: 0.9,
      height: 2.1,
      sillElevation: 0,
      swingAngle: 90,
      swingDirection: 'right',
      isOpen: true,
      finish: 'wood_oak',
      costCents: 42000,
    },
    // Restroom Door (w10)
    op_door_restroom: {
      id: 'op_door_restroom',
      wallId: 'w10',
      type: 'door',
      offset: 0.5,
      width: 0.85,
      height: 2.1,
      sillElevation: 0,
      swingAngle: 0,
      swingDirection: 'left',
      isOpen: false,
      finish: 'wood_oak',
      costCents: 38000,
    },
  };

  // Detect initial rooms
  const initialRooms = detectRooms(vertices, walls);
  // Give descriptive names & finishes to detected rooms
  for (const r of initialRooms) {
    if (r.area > 30) {
      r.name = 'Main Dining Hall';
      r.floorFinish = 'oak_parquet';
      r.floorCostCentsPerM2 = 5500; // $55.00/m²
    } else if (r.area > 13) {
      r.name = 'Barista & Prep Kitchen';
      r.floorFinish = 'terrazzo';
      r.floorCostCentsPerM2 = 6800; // $68.00/m²
    } else {
      r.name = 'Staff Restroom / Utility';
      r.floorFinish = 'tile_subway';
      r.floorCostCentsPerM2 = 4200; // $42.00/m²
    }
  }

  // Furniture items placed across the space
  const furniture: Record<string, FurnitureItem> = {
    f_counter: {
      id: 'f_counter',
      catalogId: 'furn_counter_straight',
      name: 'Barista Service Counter',
      x: 5.2,
      y: 2.0,
      z: 0,
      rotation: Math.PI / 2,
      width: 2.2,
      depth: 0.75,
      height: 0.95,
      isFloorCovering: false,
      finish: 'terrazzo',
      costCents: 115000,
    },
    f_espresso: {
      id: 'f_espresso',
      catalogId: 'furn_coffee_station',
      name: 'Commercial Espresso Machine',
      x: 7.2,
      y: 2.0,
      z: 0,
      rotation: Math.PI / 2,
      width: 0.9,
      depth: 0.6,
      height: 0.95,
      isFloorCovering: false,
      finish: 'metal_stainless',
      costCents: 78000,
    },
    // Dining table with Rug underneath (Rug is non-blocking!)
    f_rug_dining: {
      id: 'f_rug_dining',
      catalogId: 'furn_rug_rectangular',
      name: 'Dining Area Wool Rug',
      x: 2.8,
      y: 4.8,
      z: 0,
      rotation: 0,
      width: 2.4,
      depth: 1.6,
      height: 0.015,
      isFloorCovering: true, // Non-blocking!
      finish: 'fabric_beige',
      costCents: 26000,
    },
    f_table_dining: {
      id: 'f_table_dining',
      catalogId: 'furn_dining_rect',
      name: 'Dining Table',
      x: 2.8,
      y: 4.8,
      z: 0,
      rotation: 0,
      width: 1.6,
      depth: 0.9,
      height: 0.75,
      isFloorCovering: false,
      finish: 'wood_oak',
      costCents: 42000,
    },
    f_chair_d1: {
      id: 'f_chair_d1',
      catalogId: 'furn_chair_bistro',
      name: 'Bistro Chair North',
      x: 2.8,
      y: 5.4,
      z: 0,
      rotation: Math.PI,
      width: 0.48,
      depth: 0.5,
      height: 0.82,
      isFloorCovering: false,
      finish: 'wood_walnut',
      costCents: 12500,
    },
    f_chair_d2: {
      id: 'f_chair_d2',
      catalogId: 'furn_chair_bistro',
      name: 'Bistro Chair South',
      x: 2.8,
      y: 4.2,
      z: 0,
      rotation: 0,
      width: 0.48,
      depth: 0.5,
      height: 0.82,
      isFloorCovering: false,
      finish: 'wood_walnut',
      costCents: 12500,
    },
    // Bistro Round Tables near window
    f_bistro_table: {
      id: 'f_bistro_table',
      catalogId: 'furn_table_bistro_round',
      name: 'Window Bistro Table',
      x: 2.0,
      y: 1.5,
      z: 0,
      rotation: 0,
      width: 0.8,
      depth: 0.8,
      height: 0.75,
      isFloorCovering: false,
      finish: 'marble_carrara',
      costCents: 24000,
    },
    f_booth: {
      id: 'f_booth',
      catalogId: 'furn_lounge_booth',
      name: 'Fluted Dining Booth',
      x: 1.2,
      y: 6.2,
      z: 0,
      rotation: 0,
      width: 1.8,
      depth: 0.75,
      height: 1.05,
      isFloorCovering: false,
      finish: 'fabric_terracotta',
      costCents: 85000,
    },
    f_pendant_light: {
      id: 'f_pendant_light',
      catalogId: 'furn_pendant_light',
      name: 'Brass Pendant Light',
      x: 2.8,
      y: 4.8,
      z: 2.2, // ceiling suspended
      rotation: 0,
      width: 0.45,
      depth: 0.45,
      height: 0.35,
      isFloorCovering: false,
      finish: 'metal_brass',
      costCents: 18000,
    },
    f_planter: {
      id: 'f_planter',
      catalogId: 'furn_planter_foliage',
      name: 'Architectural Foliage Planter',
      x: 0.6,
      y: 0.6,
      z: 0,
      rotation: 0,
      width: 0.5,
      depth: 0.5,
      height: 1.4,
      isFloorCovering: false,
      finish: 'ceramic_white',
      costCents: 19500,
    },
  };

  const altA: AlternativeDesign = {
    id: 'alt_warm_bistro',
    name: 'Alternative A — Warm Oak Bistro',
    description: 'Natural oak parquet, brass fixtures, and relaxed cafe seating layout.',
    vertices,
    walls,
    openings,
    furniture,
    rooms: initialRooms,
    wallFinishCostPerM2: 2500,
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };

  // Alternative B: Terrazzo Luxury Lounge with modern dividers and booths
  const altBVertices = JSON.parse(JSON.stringify(vertices));
  const altBWalls = JSON.parse(JSON.stringify(walls));
  const altBOpenings = JSON.parse(JSON.stringify(openings));
  const altBFurniture: Record<string, FurnitureItem> = JSON.parse(JSON.stringify(furniture));

  // Modify finishes & items in Alternative B to demonstrate variance
  altBFurniture['f_divider'] = {
    id: 'f_divider',
    catalogId: 'furn_acoustic_divider',
    name: 'Acoustic Screen Partition',
    x: 4.2,
    y: 5.5,
    z: 0,
    rotation: Math.PI / 2,
    width: 1.2,
    depth: 0.25,
    height: 1.6,
    isFloorCovering: false,
    finish: 'fabric_gray',
    costCents: 31000,
  };

  const altBRooms = JSON.parse(JSON.stringify(initialRooms));
  for (const r of altBRooms) {
    if (r.name.includes('Dining')) {
      r.floorFinish = 'terrazzo';
      r.floorCostCentsPerM2 = 7200; // Premium terrazzo
    }
  }

  const altB: AlternativeDesign = {
    id: 'alt_terrazzo_lounge',
    name: 'Alternative B — Terrazzo Luxury Lounge',
    description: 'Polished terrazzo flooring, acoustic dividers, and premium commercial finish spec.',
    vertices: altBVertices,
    walls: altBWalls,
    openings: altBOpenings,
    furniture: altBFurniture,
    rooms: altBRooms,
    wallFinishCostPerM2: 3200, // Premium washable finish
    createdAt: Date.now() + 1000,
    updatedAt: Date.now() + 1000,
  };

  const settings: ProjectSettings = {
    unit: 'm',
    gridSnap: 0.1,
    angleSnapDeg: 45,
    cutawayMode: true,
    cutawayHeight: 0.25,
    defaultWallHeight: 2.8,
    defaultWallThickness: 0.2,
    defaultWallFinishCostPerM2: 2500,
  };

  return {
    activeAlternativeId: altA.id,
    alternatives: [altA, altB],
    settings,
  };
}
