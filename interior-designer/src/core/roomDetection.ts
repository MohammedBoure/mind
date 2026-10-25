/**
 * Room Topology & Automatic Cycle Detection Engine
 * Uses planar graph face extraction (directed half-edges with angular sorting)
 * to automatically detect all closed rooms as walls are drawn or moved.
 */

import { Point2D, Wall, Room } from '../types/plan.js';
import {
  calculatePolygonArea,
  calculatePolygonPerimeter,
  calculateSignedPolygonArea,
} from './geometry.js';

interface DirectedEdge {
  from: string;
  to: string;
  wallId: string;
  angle: number;
}

/**
 * Detect all enclosed rooms from the graph of vertices and walls.
 * Existing rooms with matching vertex sets retain their ID, label, and floor finishes.
 */
export function detectRooms(
  vertices: Record<string, Point2D>,
  walls: Record<string, Wall>,
  existingRooms: Room[] = []
): Room[] {
  const wallList = Object.values(walls).filter(
    (w) => vertices[w.startId] && vertices[w.endId] && w.startId !== w.endId
  );

  if (wallList.length < 3) {
    return [];
  }

  // 1. Build adjacency list of directed half-edges
  const adj: Map<string, DirectedEdge[]> = new Map();

  for (const w of wallList) {
    const p1 = vertices[w.startId];
    const p2 = vertices[w.endId];

    const angle1 = Math.atan2(p2.y - p1.y, p2.x - p1.x);
    const angle2 = Math.atan2(p1.y - p2.y, p1.x - p2.x);

    if (!adj.has(w.startId)) adj.set(w.startId, []);
    if (!adj.has(w.endId)) adj.set(w.endId, []);

    adj.get(w.startId)!.push({
      from: w.startId,
      to: w.endId,
      wallId: w.id,
      angle: angle1,
    });

    adj.get(w.endId)!.push({
      from: w.endId,
      to: w.startId,
      wallId: w.id,
      angle: angle2,
    });
  }

  // 2. Sort outgoing edges around each vertex counter-clockwise by angle
  for (const edges of adj.values()) {
    edges.sort((a, b) => a.angle - b.angle);
  }

  // 3. Find faces using planar graph half-edge traversal
  const visitedEdges = new Set<string>();
  const detectedFaces: Array<{
    vertexIds: string[];
    wallIds: string[];
    polygon: Array<{ x: number; y: number }>;
  }> = [];

  for (const [fromId, edges] of adj.entries()) {
    for (const edge of edges) {
      const edgeKey = `${edge.from}->${edge.to}`;
      if (visitedEdges.has(edgeKey)) continue;

      const faceVertexIds: string[] = [];
      const faceWallIds: string[] = [];
      const facePolygon: Array<{ x: number; y: number }> = [];

      let currEdge = edge;
      let loopDetected = false;
      let steps = 0;
      const maxSteps = wallList.length * 2 + 10;

      while (steps < maxSteps) {
        steps++;
        const currKey = `${currEdge.from}->${currEdge.to}`;
        if (visitedEdges.has(currKey)) {
          // If we looped back to our starting edge
          if (currEdge.from === edge.from && currEdge.to === edge.to) {
            loopDetected = true;
          }
          break;
        }

        visitedEdges.add(currKey);
        faceVertexIds.push(currEdge.from);
        faceWallIds.push(currEdge.wallId);
        facePolygon.push({
          x: vertices[currEdge.from].x,
          y: vertices[currEdge.from].y,
        });

        // Find next edge from currEdge.to:
        // In CCW planar face traversal, when arriving via (from -> to),
        // we take the reverse edge (to -> from) in adj(to) and pick the predecessor in CCW order
        const toEdges = adj.get(currEdge.to);
        if (!toEdges || toEdges.length === 0) break;

        // Find reverse edge index
        const revIdx = toEdges.findIndex((e) => e.to === currEdge.from);
        if (revIdx === -1) break;

        // Take predecessor CCW (which turns most right / keeps face on left)
        const nextIdx = (revIdx - 1 + toEdges.length) % toEdges.length;
        currEdge = toEdges[nextIdx];

        if (currEdge.from === edge.from && currEdge.to === edge.to) {
          loopDetected = true;
          break;
        }
      }

      if (loopDetected && faceVertexIds.length >= 3) {
        detectedFaces.push({
          vertexIds: faceVertexIds,
          wallIds: Array.from(new Set(faceWallIds)),
          polygon: facePolygon,
        });
      }
    }
  }

  // 4. Filter faces: Keep only positive CCW faces with area > 0.05 m² (eliminates outer infinite face and degenerate slips)
  const validRooms: Room[] = [];
  const existingRoomMap = new Map<string, Room>();

  for (const r of existingRooms) {
    const key = [...r.vertexIds].sort().join(':');
    existingRoomMap.set(key, r);
  }

  let roomCounter = 1;

  for (const face of detectedFaces) {
    const signedArea = calculateSignedPolygonArea(face.polygon);
    // Positive signed area indicates CCW orientation (internal bounded room)
    if (signedArea > 0.05) {
      const area = Math.round(Math.abs(signedArea) * 1000) / 1000;
      const perimeter = Math.round(calculatePolygonPerimeter(face.polygon) * 100) / 100;

      const key = [...face.vertexIds].sort().join(':');
      const existing = existingRoomMap.get(key);

      const roomId = existing ? existing.id : `room_${Date.now()}_${roomCounter}`;
      const name = existing ? existing.name : `Room ${roomCounter}`;
      const floorFinish = existing ? existing.floorFinish : 'oak_parquet';
      const ceilingHeight = existing ? existing.ceilingHeight : 2.8;
      const floorCostCentsPerM2 = existing ? existing.floorCostCentsPerM2 : 4500; // $45.00/m² default

      validRooms.push({
        id: roomId,
        name,
        wallIds: face.wallIds,
        vertexIds: face.vertexIds,
        polygon: face.polygon,
        area,
        perimeter,
        floorFinish,
        ceilingHeight,
        floorCostCentsPerM2,
      });

      roomCounter++;
    }
  }

  return validRooms;
}
