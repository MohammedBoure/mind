/**
 * True Geometric Wall Carving Engine
 * Generates watertight 3D box segments that cut genuine geometric voids into walls
 * for doors and windows with adjustable widths, heights, and sill elevations.
 */

import { Point2D, Wall, Opening } from '../types/plan.js';
import { distance } from './geometry.js';

export interface LocalWallBox {
  uStart: number; // start along wall length (meters)
  uEnd: number;   // end along wall length (meters)
  zBottom: number; // elevation from floor (meters)
  zTop: number;    // top elevation (meters)
  thickness: number; // wall thickness (meters)
}

export interface Wall3DMeshSegment {
  // World coordinates center
  centerX: number;
  centerY: number; // Floor plane Y in 2D or world Z
  centerZ: number; // Vertical height center in Three.js (Three.js Y)
  // Dimensions
  length: number;
  width: number;  // thickness
  height: number;
  // Rotation
  angleY: number; // rotation in horizontal plane (radians)
}

/**
 * Computes the 3D solid box segments for a wall by carving out all door and window voids.
 */
export function carveWallSegments(
  wall: Wall,
  pStart: Point2D,
  pEnd: Point2D,
  wallOpenings: Opening[],
  effectiveHeight?: number
): Wall3DMeshSegment[] {
  const wallLen = distance(pStart, pEnd);
  if (wallLen < 0.05) return [];

  const wallHeight = effectiveHeight ?? wall.height;
  const thickness = wall.thickness;
  const wallAngle = Math.atan2(pEnd.y - pStart.y, pEnd.x - pStart.x);
  const dirX = Math.cos(wallAngle);
  const dirY = Math.sin(wallAngle);

  // Normalize and sort openings along the wall
  interface ProcessedOpening {
    id: string;
    uStart: number;
    uEnd: number;
    sill: number;
    top: number;
  }

  const validOpenings: ProcessedOpening[] = [];

  for (const op of wallOpenings) {
    const uCenter = op.offset * wallLen;
    const halfW = op.width / 2;
    const uStart = Math.max(0, uCenter - halfW);
    const uEnd = Math.min(wallLen, uCenter + halfW);

    if (uEnd > uStart + 0.05) {
      validOpenings.push({
        id: op.id,
        uStart,
        uEnd,
        sill: Math.min(op.sillElevation, wallHeight),
        top: Math.min(op.sillElevation + op.height, wallHeight),
      });
    }
  }

  // Sort by uStart
  validOpenings.sort((a, b) => a.uStart - b.uStart);

  const boxes: LocalWallBox[] = [];

  let currentU = 0;

  for (const op of validOpenings) {
    // 1. Full height jamb before this opening
    if (op.uStart > currentU + 0.005) {
      boxes.push({
        uStart: currentU,
        uEnd: op.uStart,
        zBottom: 0,
        zTop: wallHeight,
        thickness,
      });
    }

    // 2. Bottom sill section under opening (e.g., windows where sill > 0)
    if (op.sill > 0.01) {
      boxes.push({
        uStart: op.uStart,
        uEnd: op.uEnd,
        zBottom: 0,
        zTop: Math.min(op.sill, wallHeight),
        thickness,
      });
    }

    // 3. Top lintel section above opening
    if (op.top < wallHeight - 0.01) {
      boxes.push({
        uStart: op.uStart,
        uEnd: op.uEnd,
        zBottom: op.top,
        zTop: wallHeight,
        thickness,
      });
    }

    currentU = Math.max(currentU, op.uEnd);
  }

  // 4. Remaining full height jamb after last opening
  if (currentU < wallLen - 0.005) {
    boxes.push({
      uStart: currentU,
      uEnd: wallLen,
      zBottom: 0,
      zTop: wallHeight,
      thickness,
    });
  }

  // Convert local 1D intervals [uStart, uEnd] x [zBottom, zTop] into world 3D box segments
  // In Three.js: X is horizontal, Y is vertical up, Z is horizontal depth
  return boxes.map((box) => {
    const segLen = box.uEnd - box.uStart;
    const segHeight = box.zTop - box.zBottom;
    const uMid = (box.uStart + box.uEnd) / 2;
    const zMid = (box.zBottom + box.zTop) / 2;

    const worldX = pStart.x + uMid * dirX;
    const worldY = pStart.y + uMid * dirY; // map to Three.js Z

    return {
      centerX: worldX,
      centerY: worldY, // world horizontal Y
      centerZ: zMid,   // world vertical Z
      length: segLen,
      width: box.thickness,
      height: segHeight,
      angleY: wallAngle,
    };
  });
}
