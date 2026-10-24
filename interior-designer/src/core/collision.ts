/**
 * Collision Detection & Spatial Intelligence Engine
 * - Separating Axis Theorem (SAT) for 2D/3D bounding footprints
 * - Overlap vs Contact distinction: Rugs / Floor coverings (<= 0.06m) are non-blocking beneath tables/chairs
 * - 90° Radial Door Swing Envelope clearance and warning system
 * - First-person walkthrough traversal collision against architectural boundaries
 */

import { FurnitureItem, Opening, Wall, Point2D } from '../types/plan.js';
import { distance, distanceToSegment } from './geometry.js';

export interface Point {
  x: number;
  y: number;
}

export interface BoundingBox2D {
  corners: Point[]; // 4 points in cyclic order
  axes: Point[];    // 2 unit normal axes
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

/**
 * Compute the 4 world corners of a furniture item's oriented footprint.
 */
export function getFurnitureFootprint(item: FurnitureItem): BoundingBox2D {
  const cos = Math.cos(item.rotation);
  const sin = Math.sin(item.rotation);

  const hw = item.width / 2;
  const hd = item.depth / 2;

  // Local corners: (+hw, +hd), (-hw, +hd), (-hw, -hd), (+hw, -hd)
  const localOffsets = [
    { x: hw, y: hd },
    { x: -hw, y: hd },
    { x: -hw, y: -hd },
    { x: hw, y: -hd },
  ];

  const corners: Point[] = localOffsets.map((pt) => ({
    x: item.x + (pt.x * cos - pt.y * sin),
    y: item.y + (pt.x * sin + pt.y * cos),
  }));

  // Edge axes for SAT
  const axes: Point[] = [
    { x: cos, y: sin },      // local X axis
    { x: -sin, y: cos },     // local Y axis
  ];

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  for (const c of corners) {
    if (c.x < minX) minX = c.x;
    if (c.x > maxX) maxX = c.x;
    if (c.y < minY) minY = c.y;
    if (c.y > maxY) maxY = c.y;
  }

  return { corners, axes, minX, maxX, minY, maxY };
}

/**
 * Separating Axis Theorem (SAT) test between two 2D oriented bounding boxes.
 */
export function testOBBOBB(boxA: BoundingBox2D, boxB: BoundingBox2D): boolean {
  // Quick AABB reject
  if (
    boxA.maxX < boxB.minX ||
    boxA.minX > boxB.maxX ||
    boxA.maxY < boxB.minY ||
    boxA.minY > boxB.maxY
  ) {
    return false;
  }

  const axes = [...boxA.axes, ...boxB.axes];

  for (const axis of axes) {
    // Project boxA
    let minA = Infinity;
    let maxA = -Infinity;
    for (const p of boxA.corners) {
      const proj = p.x * axis.x + p.y * axis.y;
      if (proj < minA) minA = proj;
      if (proj > maxA) maxA = proj;
    }

    // Project boxB
    let minB = Infinity;
    let maxB = -Infinity;
    for (const p of boxB.corners) {
      const proj = p.x * axis.x + p.y * axis.y;
      if (proj < minB) minB = proj;
      if (proj > maxB) maxB = proj;
    }

    // Check separation
    if (maxA < minB || maxB < minA) {
      return false;
    }
  }

  return true;
}

/**
 * Check collision between two furniture items.
 * Rule: Thin floor items (height <= 0.06m or isFloorCovering=true) are non-blocking
 * and allowed beneath tables, chairs, and other items.
 */
export function checkFurnitureCollision(
  itemA: FurnitureItem,
  itemB: FurnitureItem
): boolean {
  if (itemA.id === itemB.id) return false;

  // Floor coverings (e.g. rugs <= 0.06m) do not block other furniture
  if (itemA.isFloorCovering || itemB.isFloorCovering) {
    return false;
  }
  if (itemA.height <= 0.06 || itemB.height <= 0.06) {
    return false;
  }

  const boxA = getFurnitureFootprint(itemA);
  const boxB = getFurnitureFootprint(itemB);

  return testOBBOBB(boxA, boxB);
}

/**
 * Door swing envelope check.
 * Sweeps a 90° radial sector of radius equal to door width from the hinge point.
 * Returns true if any furniture item intersects the door's 90° swing arc.
 */
export interface DoorSwingConflict {
  doorId: string;
  collidingFurnitureIds: string[];
  hingePoint: Point;
  radius: number;
  startAngle: number;
  endAngle: number;
}

export function checkDoorSwingClearance(
  door: Opening,
  hostWall: Wall,
  vertices: Record<string, Point2D>,
  furnitureList: FurnitureItem[]
): DoorSwingConflict | null {
  const p1 = vertices[hostWall.startId];
  const p2 = vertices[hostWall.endId];
  if (!p1 || !p2) return null;

  const wallLen = distance(p1, p2);
  if (wallLen < 0.1) return null;

  const wallAngle = Math.atan2(p2.y - p1.y, p2.x - p1.x);

  // Door center along wall
  const uCenter = door.offset * wallLen;
  const halfW = door.width / 2;

  // Hinge point (either left or right edge of the door opening)
  const isLeftHinge = door.swingDirection === 'left';
  const uHinge = isLeftHinge ? uCenter - halfW : uCenter + halfW;

  const hingePoint: Point = {
    x: p1.x + uHinge * Math.cos(wallAngle),
    y: p1.y + uHinge * Math.sin(wallAngle),
  };

  const radius = door.width;

  // Base closed door angle in radians
  const closedAngle = isLeftHinge ? wallAngle : wallAngle + Math.PI;

  // 90° swing angle sweep
  // Door swings 90 degrees outward / inward
  const sweepAngle = Math.PI / 2;
  const startAngle = closedAngle;
  const endAngle = closedAngle + sweepAngle;

  const collidingIds: string[] = [];

  for (const item of furnitureList) {
    // Floor coverings (rugs) do not block door swing
    if (item.isFloorCovering || item.height <= 0.06) continue;

    const box = getFurnitureFootprint(item);

    // 1. Check if any corner is inside the radial sector
    let intersects = false;
    for (const c of box.corners) {
      const d = distance(hingePoint, c);
      if (d <= radius) {
        let angle = Math.atan2(c.y - hingePoint.y, c.x - hingePoint.x);
        // Normalize angle difference relative to startAngle
        let diff = (angle - startAngle) % (2 * Math.PI);
        if (diff < 0) diff += 2 * Math.PI;
        if (diff <= sweepAngle) {
          intersects = true;
          break;
        }
      }
    }

    // 2. Check if radial boundary segments intersect box
    if (!intersects) {
      const midAngle = startAngle + sweepAngle / 2;
      const testRays = [startAngle, midAngle, endAngle];
      for (const rayAngle of testRays) {
        const rayEnd: Point = {
          x: hingePoint.x + radius * Math.cos(rayAngle),
          y: hingePoint.y + radius * Math.sin(rayAngle),
        };
        for (let i = 0; i < 4; i++) {
          const c1 = box.corners[i];
          const c2 = box.corners[(i + 1) % 4];
          if (distanceToSegment(c1, c2, rayEnd) < 0.1 || distanceToSegment(hingePoint, rayEnd, c1) < 0.1) {
            intersects = true;
            break;
          }
        }
        if (intersects) break;
      }
    }

    if (intersects) {
      collidingIds.push(item.id);
    }
  }

  if (collidingIds.length > 0) {
    return {
      doorId: door.id,
      collidingFurnitureIds: collidingIds,
      hingePoint,
      radius,
      startAngle,
      endAngle,
    };
  }

  return null;
}

/**
 * Check walkthrough collision for player sphere (radius ~0.18m) against
 * walls, doors, windows, and solid furniture.
 */
export function checkWalkthroughCollision(
  pos: Point,
  radius: number,
  walls: Record<string, Wall>,
  openings: Record<string, Opening>,
  vertices: Record<string, Point2D>,
  furniture: Record<string, FurnitureItem>
): { hasCollision: boolean; correctedPos: Point } {
  let hasCollision = false;
  let cx = pos.x;
  let cy = pos.y;

  // 1. Test against walls and their openings
  for (const wall of Object.values(walls)) {
    const p1 = vertices[wall.startId];
    const p2 = vertices[wall.endId];
    if (!p1 || !p2) continue;

    const wallLen = distance(p1, p2);
    if (wallLen < 0.05) continue;

    const distToCenterline = distanceToSegment(p1, p2, { x: cx, y: cy });
    const wallHalfThick = wall.thickness / 2;
    const threshold = wallHalfThick + radius;

    if (distToCenterline < threshold) {
      // Find projected parameter t along wall
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      const t = Math.max(0, Math.min(1, ((cx - p1.x) * dx + (cy - p1.y) * dy) / (wallLen * wallLen)));
      const distFromStart = t * wallLen;

      // Check if player is passing through an OPEN door
      let isOpenDoorClearance = false;
      for (const op of Object.values(openings)) {
        if (op.wallId === wall.id && op.type === 'door') {
          const opCenter = op.offset * wallLen;
          const halfW = op.width / 2;
          if (distFromStart >= opCenter - halfW && distFromStart <= opCenter + halfW) {
            // Traversal rule: Door must be open past 55 degrees
            if (op.isOpen && op.swingAngle >= 55) {
              isOpenDoorClearance = true;
              break;
            }
          }
        }
      }

      if (!isOpenDoorClearance) {
        hasCollision = true;
        // Push out along wall normal
        const nx = -dy / wallLen;
        const ny = dx / wallLen;
        const side = (cx - p1.x) * nx + (cy - p1.y) * ny;
        const pushDir = side >= 0 ? 1 : -1;
        const overlap = threshold - distToCenterline;
        cx += nx * pushDir * overlap;
        cy += ny * pushDir * overlap;
      }
    }
  }

  // 2. Test against solid furniture (excluding floor coverings)
  for (const item of Object.values(furniture)) {
    if (item.isFloorCovering || item.height <= 0.06) continue;
    const box = getFurnitureFootprint(item);
    // Circular test against box
    for (let i = 0; i < 4; i++) {
      const c1 = box.corners[i];
      const c2 = box.corners[(i + 1) % 4];
      const d = distanceToSegment(c1, c2, { x: cx, y: cy });
      if (d < radius) {
        hasCollision = true;
        const pushDist = radius - d;
        // push away from item center
        const toItemX = cx - item.x;
        const toItemY = cy - item.y;
        const distCenter = Math.hypot(toItemX, toItemY) || 1;
        cx += (toItemX / distCenter) * pushDist;
        cy += (toItemY / distCenter) * pushDist;
      }
    }
  }

  return {
    hasCollision,
    correctedPos: { x: cx, y: cy },
  };
}
