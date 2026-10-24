/**
 * High-Performance 2D Architectural Blueprint Canvas Renderer
 * Renders metric grid, walls with true thickness, openings with swing arcs,
 * room boundary fills, dimension lines, and furniture footprints.
 */

import {
  Point2D,
  Wall,
  Opening,
  Room,
  FurnitureItem,
  SelectionState,
} from '../types/plan.js';
import { distance, midpoint } from '../core/geometry.js';
import { getFurnitureFootprint, DoorSwingConflict } from '../core/collision.js';

export interface ViewportTransform {
  zoom: number;       // pixels per meter (e.g. 50 px/m)
  panX: number;       // translation in pixels
  panY: number;       // translation in pixels
}

export function worldToScreen(
  x: number,
  y: number,
  transform: ViewportTransform,
  canvasWidth: number,
  canvasHeight: number
): { sx: number; sy: number } {
  const cx = canvasWidth / 2 + transform.panX;
  const cy = canvasHeight / 2 + transform.panY;
  return {
    sx: cx + x * transform.zoom,
    sy: cy - y * transform.zoom, // invert Y for standard Cartesian architectural blueprint
  };
}

export function screenToWorld(
  sx: number,
  sy: number,
  transform: ViewportTransform,
  canvasWidth: number,
  canvasHeight: number
): { x: number; y: number } {
  const cx = canvasWidth / 2 + transform.panX;
  const cy = canvasHeight / 2 + transform.panY;
  return {
    x: (sx - cx) / transform.zoom,
    y: -(sy - cy) / transform.zoom,
  };
}

export function renderBlueprint2D(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  transform: ViewportTransform,
  vertices: Record<string, Point2D>,
  walls: Record<string, Wall>,
  openings: Record<string, Opening>,
  furniture: Record<string, FurnitureItem>,
  rooms: Room[],
  selection: SelectionState,
  doorConflicts: Map<string, DoorSwingConflict>,
  collidingFurnitureIds: Set<string>,
  drawingTempWall?: { start: Point2D; end: Point2D } | null
) {
  ctx.save();
  ctx.clearRect(0, 0, width, height);

  // 1. Background
  ctx.fillStyle = '#0b1120'; // Slate 950 deep blueprint blue-gray
  ctx.fillRect(0, 0, width, height);

  // 2. Metric Grid
  renderGrid(ctx, width, height, transform);

  // 3. Room Floor Surfaces & Labels
  renderRooms(ctx, width, height, transform, rooms, selection);

  // 4. Walls
  renderWalls(ctx, width, height, transform, vertices, walls, openings, selection);

  // 5. Openings (Doors with Swing Arcs & Windows)
  renderOpenings(ctx, width, height, transform, vertices, walls, openings, selection, doorConflicts);

  // 6. Furniture Footprints
  renderFurniture(ctx, width, height, transform, furniture, selection, collidingFurnitureIds);

  // 7. Temporary Drawing Wall Preview
  if (drawingTempWall) {
    renderTempWall(ctx, width, height, transform, drawingTempWall);
  }

  // 8. Vertices Handles (Joints)
  renderVertices(ctx, width, height, transform, vertices, selection);

  ctx.restore();
}

function renderGrid(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  transform: ViewportTransform
) {
  const zoom = transform.zoom;
  // Choose grid step based on zoom level: 0.1m, 0.5m, 1m, or 2m
  let step = 1.0; // 1 meter default
  if (zoom > 100) step = 0.5;
  if (zoom > 250) step = 0.1;
  if (zoom < 30) step = 2.0;

  const topLeft = screenToWorld(0, 0, transform, width, height);
  const bottomRight = screenToWorld(width, height, transform, width, height);

  const startX = Math.floor(topLeft.x / step) * step;
  const endX = Math.ceil(bottomRight.x / step) * step;
  const startY = Math.floor(bottomRight.y / step) * step;
  const endY = Math.ceil(topLeft.y / step) * step;

  // Minor lines
  ctx.lineWidth = 1;
  ctx.strokeStyle = '#1e293b'; // Slate 800

  ctx.beginPath();
  for (let x = startX; x <= endX; x += step) {
    const { sx } = worldToScreen(x, 0, transform, width, height);
    ctx.moveTo(sx, 0);
    ctx.lineTo(sx, height);
  }
  for (let y = startY; y <= endY; y += step) {
    const { sy } = worldToScreen(0, y, transform, width, height);
    ctx.moveTo(0, sy);
    ctx.lineTo(width, sy);
  }
  ctx.stroke();

  // Major 5-meter lines
  const majorStep = step * 5;
  const mStartX = Math.floor(topLeft.x / majorStep) * majorStep;
  const mEndX = Math.ceil(bottomRight.x / majorStep) * majorStep;
  const mStartY = Math.floor(bottomRight.y / majorStep) * majorStep;
  const mEndY = Math.ceil(topLeft.y / majorStep) * majorStep;

  ctx.strokeStyle = '#334155'; // Slate 700
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  for (let x = mStartX; x <= mEndX; x += majorStep) {
    const { sx } = worldToScreen(x, 0, transform, width, height);
    ctx.moveTo(sx, 0);
    ctx.lineTo(sx, height);
  }
  for (let y = mStartY; y <= mEndY; y += majorStep) {
    const { sy } = worldToScreen(0, y, transform, width, height);
    ctx.moveTo(0, sy);
    ctx.lineTo(width, sy);
  }
  ctx.stroke();

  // Axis Cross at World (0,0)
  const origin = worldToScreen(0, 0, transform, width, height);
  ctx.strokeStyle = '#38bdf8'; // Sky 400
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(origin.sx - 15, origin.sy);
  ctx.lineTo(origin.sx + 15, origin.sy);
  ctx.moveTo(origin.sx, origin.sy - 15);
  ctx.lineTo(origin.sx, origin.sy + 15);
  ctx.stroke();
}

function renderRooms(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  transform: ViewportTransform,
  rooms: Room[],
  selection: SelectionState
) {
  for (const room of rooms) {
    if (room.polygon.length < 3) continue;

    ctx.beginPath();
    const first = worldToScreen(room.polygon[0].x, room.polygon[0].y, transform, width, height);
    ctx.moveTo(first.sx, first.sy);

    for (let i = 1; i < room.polygon.length; i++) {
      const pt = worldToScreen(room.polygon[i].x, room.polygon[i].y, transform, width, height);
      ctx.lineTo(pt.sx, pt.sy);
    }
    ctx.closePath();

    const isSelected = selection.type === 'room' && selection.id === room.id;
    ctx.fillStyle = isSelected ? 'rgba(56, 189, 248, 0.16)' : 'rgba(30, 41, 59, 0.45)';
    ctx.fill();

    // Room Label & Area Badge
    let avgX = 0;
    let avgY = 0;
    for (const p of room.polygon) {
      avgX += p.x;
      avgY += p.y;
    }
    avgX /= room.polygon.length;
    avgY /= room.polygon.length;

    const centerScreen = worldToScreen(avgX, avgY, transform, width, height);

    ctx.save();
    ctx.font = '600 13px system-ui, -apple-system, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    // Label tag
    const title = room.name;
    const areaText = `${room.area.toFixed(3)} m²`;

    ctx.fillStyle = '#f8fafc';
    ctx.fillText(title, centerScreen.sx, centerScreen.sy - 8);

    ctx.font = '400 11px system-ui, -apple-system, sans-serif';
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(areaText, centerScreen.sx, centerScreen.sy + 10);
    ctx.restore();
  }
}

function renderWalls(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  transform: ViewportTransform,
  vertices: Record<string, Point2D>,
  walls: Record<string, Wall>,
  openings: Record<string, Opening>,
  selection: SelectionState
) {
  for (const wall of Object.values(walls)) {
    const p1 = vertices[wall.startId];
    const p2 = vertices[wall.endId];
    if (!p1 || !p2) continue;

    const s1 = worldToScreen(p1.x, p1.y, transform, width, height);
    const s2 = worldToScreen(p2.x, p2.y, transform, width, height);

    const isSelected = selection.type === 'wall' && selection.id === wall.id;
    const wallThickPx = Math.max(4, wall.thickness * transform.zoom);

    // Wall stroke
    ctx.save();
    ctx.lineWidth = wallThickPx;
    ctx.lineCap = 'square';
    ctx.strokeStyle = isSelected ? '#38bdf8' : '#e2e8f0'; // Sky 400 when selected, off-white architectural wall
    ctx.beginPath();
    ctx.moveTo(s1.sx, s1.sy);
    ctx.lineTo(s2.sx, s2.sy);
    ctx.stroke();

    // Wall interior dark core for blueprint depth
    ctx.lineWidth = Math.max(1, wallThickPx - 4);
    ctx.strokeStyle = isSelected ? '#0284c7' : '#1e293b';
    ctx.stroke();

    // Dimension label on wall
    const wallLen = distance(p1, p2);
    if (wallLen > 0.4 && transform.zoom > 35) {
      const mid = midpoint(p1, p2);
      const midScreen = worldToScreen(mid.x, mid.y, transform, width, height);
      const angle = Math.atan2(s2.sy - s1.sy, s2.sx - s1.sx);
      // Keep text upright
      let textAngle = angle;
      if (textAngle > Math.PI / 2 || textAngle < -Math.PI / 2) {
        textAngle += Math.PI;
      }

      ctx.save();
      ctx.translate(midScreen.sx, midScreen.sy);
      ctx.rotate(textAngle);
      ctx.font = '500 11px system-ui, -apple-system, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillStyle = isSelected ? '#38bdf8' : '#cbd5e1';
      ctx.fillText(`${wallLen.toFixed(2)}m`, 0, -wallThickPx / 2 - 3);
      ctx.restore();
    }

    ctx.restore();
  }
}

function renderOpenings(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  transform: ViewportTransform,
  vertices: Record<string, Point2D>,
  walls: Record<string, Wall>,
  openings: Record<string, Opening>,
  selection: SelectionState,
  doorConflicts: Map<string, DoorSwingConflict>
) {
  for (const op of Object.values(openings)) {
    const wall = walls[op.wallId];
    if (!wall) continue;
    const p1 = vertices[wall.startId];
    const p2 = vertices[wall.endId];
    if (!p1 || !p2) continue;

    const wallLen = distance(p1, p2);
    if (wallLen < 0.1) continue;

    const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);
    const uCenter = op.offset * wallLen;
    const halfW = op.width / 2;

    const uStart = Math.max(0, uCenter - halfW);
    const uEnd = Math.min(wallLen, uCenter + halfW);

    const startPt = {
      x: p1.x + uStart * Math.cos(angle),
      y: p1.y + uStart * Math.sin(angle),
    };
    const endPt = {
      x: p1.x + uEnd * Math.cos(angle),
      y: p1.y + uEnd * Math.sin(angle),
    };

    const sStart = worldToScreen(startPt.x, startPt.y, transform, width, height);
    const sEnd = worldToScreen(endPt.x, endPt.y, transform, width, height);

    const isSelected = selection.type === 'opening' && selection.id === op.id;
    const isConflict = doorConflicts.has(op.id);
    const wallThickPx = Math.max(4, wall.thickness * transform.zoom);

    // 1. Cut the void into the wall (clear host wall thickness)
    ctx.save();
    ctx.lineWidth = wallThickPx + 2;
    ctx.strokeStyle = '#0b1120'; // background void
    ctx.beginPath();
    ctx.moveTo(sStart.sx, sStart.sy);
    ctx.lineTo(sEnd.sx, sEnd.sy);
    ctx.stroke();

    if (op.type === 'door') {
      // Door opening: Frame jamb lines
      ctx.lineWidth = 2;
      ctx.strokeStyle = isSelected ? '#38bdf8' : '#e2e8f0';

      // Door leaf & 90° Swing Arc
      const isLeft = op.swingDirection === 'left';
      const hinge = isLeft ? sStart : sEnd;
      const leafRadius = op.width * transform.zoom;

      // Base wall angle in screen space (screen Y is flipped)
      const screenWallAngle = Math.atan2(sEnd.sy - sStart.sy, sEnd.sx - sStart.sx);
      const swingSign = isLeft ? 1 : -1;
      const startAngle = isLeft ? screenWallAngle : screenWallAngle + Math.PI;
      const endAngle = startAngle - (Math.PI / 2) * swingSign;

      // 90° Swing Arc
      ctx.save();
      ctx.beginPath();
      ctx.arc(hinge.sx, hinge.sy, leafRadius, startAngle, endAngle, !isLeft);
      ctx.strokeStyle = isConflict ? '#ef4444' : isSelected ? '#38bdf8' : '#94a3b8';
      ctx.lineWidth = isConflict ? 2.5 : 1.5;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.restore();

      // Open Door Leaf Line
      const leafAngle = startAngle - ((op.swingAngle * Math.PI) / 180) * swingSign;
      const leafEnd = {
        sx: hinge.sx + leafRadius * Math.cos(leafAngle),
        sy: hinge.sy + leafRadius * Math.sin(leafAngle),
      };

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(hinge.sx, hinge.sy);
      ctx.lineTo(leafEnd.sx, leafEnd.sy);
      ctx.strokeStyle = isConflict ? '#ef4444' : isSelected ? '#38bdf8' : '#f8fafc';
      ctx.lineWidth = 3;
      ctx.stroke();
      ctx.restore();

      // Conflict Alert Badge
      if (isConflict) {
        ctx.save();
        ctx.fillStyle = '#ef4444';
        ctx.beginPath();
        ctx.arc(hinge.sx, hinge.sy, 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    } else {
      // Window: Architectural parallel glass panes + sill
      ctx.save();
      ctx.lineWidth = 2;
      ctx.strokeStyle = isSelected ? '#38bdf8' : '#38bdf8';

      // Sill lines
      ctx.beginPath();
      ctx.moveTo(sStart.sx, sStart.sy);
      ctx.lineTo(sEnd.sx, sEnd.sy);
      ctx.stroke();

      // Double glazed center lines
      const normX = -Math.sin(angle);
      const normY = Math.cos(angle);
      const offsetPx = wallThickPx * 0.25;

      ctx.lineWidth = 1.2;
      ctx.strokeStyle = isSelected ? '#38bdf8' : '#7dd3fc';
      ctx.beginPath();
      ctx.moveTo(sStart.sx + normX * offsetPx, sStart.sy - normY * offsetPx);
      ctx.lineTo(sEnd.sx + normX * offsetPx, sEnd.sy - normY * offsetPx);
      ctx.moveTo(sStart.sx - normX * offsetPx, sStart.sy + normY * offsetPx);
      ctx.lineTo(sEnd.sx - normX * offsetPx, sEnd.sy + normY * offsetPx);
      ctx.stroke();
      ctx.restore();
    }

    ctx.restore();
  }
}

function renderFurniture(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  transform: ViewportTransform,
  furniture: Record<string, FurnitureItem>,
  selection: SelectionState,
  collidingFurnitureIds: Set<string>
) {
  for (const item of Object.values(furniture)) {
    const isSelected = selection.type === 'furniture' && selection.id === item.id;
    const isColliding = collidingFurnitureIds.has(item.id);

    const footprint = getFurnitureFootprint(item);
    const screenCorners = footprint.corners.map((c) =>
      worldToScreen(c.x, c.y, transform, width, height)
    );

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(screenCorners[0].sx, screenCorners[0].sy);
    for (let i = 1; i < screenCorners.length; i++) {
      ctx.lineTo(screenCorners[i].sx, screenCorners[i].sy);
    }
    ctx.closePath();

    // Fill style based on item category
    if (item.isFloorCovering) {
      // Rug: soft dashed outline, patterned fill
      ctx.fillStyle = isSelected
        ? 'rgba(56, 189, 248, 0.25)'
        : 'rgba(148, 163, 184, 0.18)';
      ctx.fill();
      ctx.strokeStyle = isSelected ? '#38bdf8' : '#64748b';
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 3]);
      ctx.stroke();
    } else {
      ctx.fillStyle = isColliding
        ? 'rgba(239, 68, 68, 0.35)' // red warning fill when colliding
        : isSelected
        ? 'rgba(56, 189, 248, 0.25)'
        : 'rgba(51, 65, 85, 0.85)';
      ctx.fill();

      ctx.strokeStyle = isColliding
        ? '#ef4444'
        : isSelected
        ? '#38bdf8'
        : '#94a3b8';
      ctx.lineWidth = isSelected || isColliding ? 2.5 : 1.5;
      ctx.stroke();
    }

    // Directional orientation notch / label
    const centerScreen = worldToScreen(item.x, item.y, transform, width, height);

    if (transform.zoom > 35) {
      ctx.save();
      ctx.translate(centerScreen.sx, centerScreen.sy);
      ctx.rotate(-item.rotation);
      ctx.font = '500 10px system-ui, -apple-system, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = isColliding ? '#fca5a5' : isSelected ? '#bae6fd' : '#e2e8f0';
      ctx.fillText(item.name, 0, 0);

      // Orientation pointer
      ctx.fillStyle = isSelected ? '#38bdf8' : '#94a3b8';
      ctx.beginPath();
      ctx.moveTo(0, -(item.depth * transform.zoom) / 2);
      ctx.lineTo(-4, -(item.depth * transform.zoom) / 2 + 6);
      ctx.lineTo(4, -(item.depth * transform.zoom) / 2 + 6);
      ctx.closePath();
      ctx.fill();
      ctx.restore();
    }

    ctx.restore();
  }
}

function renderTempWall(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  transform: ViewportTransform,
  tempWall: { start: Point2D; end: Point2D }
) {
  const s1 = worldToScreen(tempWall.start.x, tempWall.start.y, transform, width, height);
  const s2 = worldToScreen(tempWall.end.x, tempWall.end.y, transform, width, height);

  ctx.save();
  ctx.lineWidth = Math.max(3, 0.2 * transform.zoom);
  ctx.strokeStyle = '#38bdf8';
  ctx.setLineDash([6, 4]);
  ctx.beginPath();
  ctx.moveTo(s1.sx, s1.sy);
  ctx.lineTo(s2.sx, s2.sy);
  ctx.stroke();

  // Dimension label
  const len = distance(tempWall.start, tempWall.end);
  const mid = midpoint(tempWall.start, tempWall.end);
  const sMid = worldToScreen(mid.x, mid.y, transform, width, height);

  ctx.setLineDash([]);
  ctx.font = '600 12px system-ui, -apple-system, sans-serif';
  ctx.fillStyle = '#38bdf8';
  ctx.textAlign = 'center';
  ctx.fillText(`${len.toFixed(2)}m`, sMid.sx, sMid.sy - 12);
  ctx.restore();
}

function renderVertices(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  transform: ViewportTransform,
  vertices: Record<string, Point2D>,
  selection: SelectionState
) {
  for (const v of Object.values(vertices)) {
    const s = worldToScreen(v.x, v.y, transform, width, height);
    const isSelected = selection.type === 'vertex' && selection.id === v.id;

    ctx.save();
    ctx.beginPath();
    ctx.arc(s.sx, s.sy, isSelected ? 6 : 4, 0, Math.PI * 2);
    ctx.fillStyle = isSelected ? '#38bdf8' : '#ffffff';
    ctx.fill();
    ctx.strokeStyle = '#0f172a';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.restore();
  }
}
