/**
 * Core geometric and structural data types for the 2D/3D interior design engine.
 * Metric system: All coordinates and distances are specified in METERS (m).
 * Angles: Degrees or Radians as explicitly noted.
 */

export interface Point2D {
  id: string;
  x: number; // in meters
  y: number; // in meters
}

export interface Wall {
  id: string;
  startId: string; // Point2D id
  endId: string;   // Point2D id
  thickness: number; // default ~0.2m (20cm)
  height: number;    // default ~2.8m
  finish: string;    // 'paint_white' | 'paint_warm_gray' | 'concrete' | 'brick' | 'wood_panel'
}

export type OpeningType = 'door' | 'window';

export type SwingDirection = 'left' | 'right';

export interface Opening {
  id: string;
  wallId: string;
  type: OpeningType;
  /**
   * Normalized offset along the host wall [0.0 - 1.0], or absolute distance in meters from startId.
   * Here we use normalized offset (0.0 to 1.0) along the host wall centerline.
   */
  offset: number;
  width: number;        // width along wall, e.g. 0.9m
  height: number;       // opening height, e.g. 2.1m for door, 1.2m for window
  sillElevation: number; // height above floor, e.g. 0.0m for door, 0.9m for window
  swingAngle: number;   // current open angle in degrees [0 to 90+]
  swingDirection: SwingDirection;
  isOpen: boolean;      // whether door is swung open
  finish: string;       // 'wood_oak' | 'wood_walnut' | 'aluminum_black' | 'steel'
  costCents: number;    // integer cents
}

export interface Room {
  id: string;
  name: string;
  wallIds: string[];
  vertexIds: string[];
  polygon: Array<{ x: number; y: number }>;
  area: number; // in square meters (m²), accurate to 0.001 m²
  perimeter: number; // in meters
  floorFinish: string; // 'oak_parquet' | 'terrazzo' | 'concrete' | 'marble' | 'carpet_tile'
  ceilingHeight: number;
  floorCostCentsPerM2: number; // integer cents per m²
}

export interface FurnitureItem {
  id: string;
  catalogId: string;
  name: string;
  x: number; // X coordinate on floor (meters)
  y: number; // Y coordinate on floor (meters)
  z: number; // Elevation above floor (meters), usually 0
  rotation: number; // Rotation in radians (around vertical Z/Y axis)
  width: number; // Dimensions in meters
  depth: number;
  height: number;
  isFloorCovering: boolean; // items <= 0.06m (rugs, tiles) non-blocking
  finish: string;
  costCents: number; // integer cents
  customProps?: Record<string, unknown>;
}

export interface ProjectSettings {
  unit: 'm';
  gridSnap: number; // 0.1m snap
  angleSnapDeg: number; // 45°
  cutawayMode: boolean; // presentation cutaway mode
  cutawayHeight: number; // low plinth height, e.g. 0.25m
  defaultWallHeight: number; // 2.8m
  defaultWallThickness: number; // 0.2m
  defaultWallFinishCostPerM2: number; // 2500 cents ($25.00/m²)
}

export interface AlternativeDesign {
  id: string;
  name: string;
  description: string;
  vertices: Record<string, Point2D>;
  walls: Record<string, Wall>;
  openings: Record<string, Opening>;
  furniture: Record<string, FurnitureItem>;
  rooms: Room[];
  wallFinishCostPerM2: number;
  createdAt: number;
  updatedAt: number;
}

export type SelectionType = 'none' | 'vertex' | 'wall' | 'opening' | 'furniture' | 'room';

export interface SelectionState {
  type: SelectionType;
  id: string | null;
}

export type EditorMode =
  | 'select'
  | 'draw_wall'
  | 'place_door'
  | 'place_window'
  | 'place_furniture'
  | 'walkthrough';

export type ViewLayout = 'split' | '2d_only' | '3d_only';
