/**
 * 2D Geometric Utilities for Architectural Blueprint Engine
 * Metric unit: meters (m). All calculations are high precision.
 */

export interface Point {
  x: number;
  y: number;
}

/**
 * Euclidean distance between two points in meters.
 */
export function distance(p1: Point, p2: Point): number {
  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  return Math.hypot(dx, dy);
}

/**
 * Midpoint between two points.
 */
export function midpoint(p1: Point, p2: Point): Point {
  return {
    x: (p1.x + p2.x) / 2,
    y: (p1.y + p2.y) / 2,
  };
}

/**
 * Snap a point coordinate to nearest metric grid interval (e.g., 0.1m).
 */
export function snapToGrid(val: number, gridSize = 0.1): number {
  return Math.round(val / gridSize) * gridSize;
}

export function snapPointToGrid(p: Point, gridSize = 0.1): Point {
  return {
    x: snapToGrid(p.x, gridSize),
    y: snapToGrid(p.y, gridSize),
  };
}

/**
 * Snap an angle (in radians) to nearest increment in degrees (default 45°).
 */
export function snapAngle(angleRad: number, incrementDeg = 45): number {
  const deg = (angleRad * 180) / Math.PI;
  const snappedDeg = Math.round(deg / incrementDeg) * incrementDeg;
  return (snappedDeg * Math.PI) / 180;
}

/**
 * Apply 45-degree angle snapping from an anchor point to target point.
 */
export function snapPointToAngle(anchor: Point, target: Point, incrementDeg = 45): Point {
  const dist = distance(anchor, target);
  if (dist < 0.001) return target;
  const rawAngle = Math.atan2(target.y - anchor.y, target.x - anchor.x);
  const snappedAngle = snapAngle(rawAngle, incrementDeg);
  return {
    x: anchor.x + dist * Math.cos(snappedAngle),
    y: anchor.y + dist * Math.sin(snappedAngle),
  };
}

/**
 * Nearest point on a finite line segment (p1 -> p2) to query point q.
 */
export function closestPointOnSegment(p1: Point, p2: Point, q: Point): { point: Point; t: number } {
  const dx = p2.x - p1.x;
  const dy = p2.y - p1.y;
  const lengthSq = dx * dx + dy * dy;
  if (lengthSq < 1e-9) {
    return { point: { x: p1.x, y: p1.y }, t: 0 };
  }
  const t = Math.max(0, Math.min(1, ((q.x - p1.x) * dx + (q.y - p1.y) * dy) / lengthSq));
  return {
    point: {
      x: p1.x + t * dx,
      y: p1.y + t * dy,
    },
    t,
  };
}

/**
 * Distance from point q to finite line segment (p1 -> p2).
 */
export function distanceToSegment(p1: Point, p2: Point, q: Point): number {
  const { point } = closestPointOnSegment(p1, p2, q);
  return distance(point, q);
}

/**
 * Check if two line segments (p1-p2 and p3-p4) intersect.
 */
export function segmentsIntersect(p1: Point, p2: Point, p3: Point, p4: Point): boolean {
  function ccw(a: Point, b: Point, c: Point): boolean {
    return (c.y - a.y) * (b.x - a.x) > (b.y - a.y) * (c.x - a.x);
  }
  return (
    ccw(p1, p3, p4) !== ccw(p2, p3, p4) &&
    ccw(p1, p2, p3) !== ccw(p1, p2, p4)
  );
}

/**
 * Ray casting algorithm to test whether a 2D point is inside a polygon.
 */
export function isPointInPolygon(point: Point, polygon: Point[]): boolean {
  let inside = false;
  const n = polygon.length;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = polygon[i].x;
    const yi = polygon[i].y;
    const xj = polygon[j].x;
    const yj = polygon[j].y;

    const intersect =
      yi > point.y !== yj > point.y &&
      point.x < ((xj - xi) * (point.y - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

/**
 * Calculate polygon area using Shoelace formula (signed area).
 * Positive if counter-clockwise, negative if clockwise.
 */
export function calculateSignedPolygonArea(polygon: Point[]): number {
  let area = 0;
  const n = polygon.length;
  if (n < 3) return 0;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    area += polygon[i].x * polygon[j].y;
    area -= polygon[j].x * polygon[i].y;
  }
  return area / 2;
}

/**
 * Absolute polygon area in square meters (accurate to 0.001 m²).
 */
export function calculatePolygonArea(polygon: Point[]): number {
  return Math.abs(calculateSignedPolygonArea(polygon));
}

/**
 * Calculate polygon perimeter in meters.
 */
export function calculatePolygonPerimeter(polygon: Point[]): number {
  let p = 0;
  const n = polygon.length;
  if (n < 2) return 0;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    p += distance(polygon[i], polygon[j]);
  }
  return p;
}

/**
 * Calculate polygon centroid.
 */
export function calculatePolygonCentroid(polygon: Point[]): Point {
  let cx = 0;
  let cy = 0;
  let signedArea = 0;
  const n = polygon.length;
  if (n === 0) return { x: 0, y: 0 };
  if (n === 1) return { x: polygon[0].x, y: polygon[0].y };
  if (n === 2) return midpoint(polygon[0], polygon[1]);

  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const a = polygon[i].x * polygon[j].y - polygon[j].x * polygon[i].y;
    signedArea += a;
    cx += (polygon[i].x + polygon[j].x) * a;
    cy += (polygon[i].y + polygon[j].y) * a;
  }
  signedArea *= 0.5;
  if (Math.abs(signedArea) < 1e-6) {
    let sx = 0;
    let sy = 0;
    for (const pt of polygon) {
      sx += pt.x;
      sy += pt.y;
    }
    return { x: sx / n, y: sy / n };
  }
  return {
    x: cx / (6 * signedArea),
    y: cy / (6 * signedArea),
  };
}

/**
 * Ear-clipping triangulation for simple polygons (useful for Three.js floor meshes).
 * Returns array of triangle index triples [i0, i1, i2].
 */
export function triangulatePolygon(polygon: Point[]): number[][] {
  const n = polygon.length;
  if (n < 3) return [];
  if (n === 3) return [[0, 1, 2]];

  // Ensure CCW orientation
  let vertices = polygon.map((p, i) => ({ ...p, origIndex: i }));
  if (calculateSignedPolygonArea(vertices) < 0) {
    vertices = vertices.reverse();
  }

  const triangles: number[][] = [];
  const indices = vertices.map((_, i) => i);

  function isEar(i0: number, i1: number, i2: number): boolean {
    const a = vertices[i0];
    const b = vertices[i1];
    const c = vertices[i2];
    // Must be convex
    const cross = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
    if (cross <= 0) return false;

    // No other vertex inside triangle (a, b, c)
    for (let i = 0; i < indices.length; i++) {
      const idx = indices[i];
      if (idx === i0 || idx === i1 || idx === i2) continue;
      const pt = vertices[idx];
      if (isPointInPolygon(pt, [a, b, c])) return false;
    }
    return true;
  }

  let count = indices.length;
  let iterations = 0;
  const maxIterations = count * 3;

  while (count > 3 && iterations < maxIterations) {
    iterations++;
    let earFound = false;
    for (let i = 0; i < count; i++) {
      const prev = indices[(i - 1 + count) % count];
      const curr = indices[i];
      const next = indices[(i + 1) % count];

      if (isEar(prev, curr, next)) {
        triangles.push([
          vertices[prev].origIndex,
          vertices[curr].origIndex,
          vertices[next].origIndex,
        ]);
        indices.splice(i, 1);
        count--;
        earFound = true;
        break;
      }
    }
    if (!earFound) {
      // Degenerate polygon fallback
      break;
    }
  }

  if (count === 3) {
    triangles.push([
      vertices[indices[0]].origIndex,
      vertices[indices[1]].origIndex,
      vertices[indices[2]].origIndex,
    ]);
  }

  return triangles;
}
