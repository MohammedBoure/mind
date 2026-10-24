/**
 * Scaled Vector SVG Blueprint Generator
 * Produces architectural-standard vector blueprints (1:50 metric scale)
 * complete with dimension lines, room tags, door swing arcs, wall thickness, and title block.
 */

import { AlternativeDesign } from '../types/plan.js';
import { distance, midpoint } from '../core/geometry.js';
import { getFurnitureFootprint } from '../core/collision.js';

export function exportBlueprintToSVG(
  design: AlternativeDesign,
  scale = 100, // 100 pixels per meter (1:10 architectural blueprint scale)
  scaleLabel = '1:10'
): string {
  const { vertices, walls, openings, furniture, rooms } = design;

  // 1. Calculate Bounding Box of all vertices and furniture
  let minX = -5;
  let maxX = 15;
  let minY = -5;
  let maxY = 15;

  const vList = Object.values(vertices);
  if (vList.length > 0) {
    minX = Math.min(...vList.map((v) => v.x)) - 1.5;
    maxX = Math.max(...vList.map((v) => v.x)) + 1.5;
    minY = Math.min(...vList.map((v) => v.y)) - 1.5;
    maxY = Math.max(...vList.map((v) => v.y)) + 1.5;
  }

  for (const f of Object.values(furniture)) {
    minX = Math.min(minX, f.x - f.width);
    maxX = Math.max(maxX, f.x + f.width);
    minY = Math.min(minY, f.y - f.depth);
    maxY = Math.max(maxY, f.y + f.depth);
  }

  const margin = 1.0;
  minX -= margin;
  maxX += margin;
  minY -= margin;
  maxY += margin;

  const worldW = maxX - minX;
  const worldH = maxY - minY;

  const svgW = Math.round(worldW * scale);
  const svgH = Math.round(worldH * scale);

  function toSvgX(x: number): number {
    return (x - minX) * scale;
  }
  function toSvgY(y: number): number {
    return svgH - (y - minY) * scale; // invert Y
  }

  const svgParts: string[] = [];

  // SVG Header & Styles
  svgParts.push(`<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${svgW} ${svgH}" width="${svgW}" height="${svgH}">
  <style>
    .grid-line { stroke: #1e293b; stroke-width: 0.5; }
    .room-fill { fill: #0f172a; stroke: #334155; stroke-width: 0.5; }
    .room-text-title { font-family: system-ui, sans-serif; font-size: 13px; font-weight: 600; fill: #f8fafc; text-anchor: middle; }
    .room-text-sub { font-family: system-ui, sans-serif; font-size: 11px; fill: #94a3b8; text-anchor: middle; }
    .wall-thick { stroke: #e2e8f0; stroke-linecap: square; }
    .wall-core { stroke: #0f172a; stroke-linecap: square; }
    .dim-line { stroke: #38bdf8; stroke-width: 1; }
    .dim-text { font-family: system-ui, sans-serif; font-size: 10px; font-weight: 500; fill: #38bdf8; text-anchor: middle; }
    .door-arc { stroke: #94a3b8; stroke-width: 1.5; stroke-dasharray: 4,4; fill: none; }
    .door-leaf { stroke: #f8fafc; stroke-width: 2.5; stroke-linecap: round; }
    .win-frame { stroke: #38bdf8; stroke-width: 1.5; }
    .furn-box { fill: #334155; stroke: #94a3b8; stroke-width: 1.5; }
    .furn-rug { fill: rgba(148, 163, 184, 0.15); stroke: #64748b; stroke-width: 1; stroke-dasharray: 4,3; }
    .furn-text { font-family: system-ui, sans-serif; font-size: 9px; fill: #cbd5e1; text-anchor: middle; dominant-baseline: middle; }
  </style>
  <rect width="${svgW}" height="${svgH}" fill="#0b1120"/>
  `);

  // 2. Metric Grid
  svgParts.push('<g id="metric-grid">');
  for (let x = Math.ceil(minX); x <= Math.floor(maxX); x += 1) {
    const sx = toSvgX(x);
    svgParts.push(`<line x1="${sx}" y1="0" x2="${sx}" y2="${svgH}" class="grid-line"/>`);
  }
  for (let y = Math.ceil(minY); y <= Math.floor(maxY); y += 1) {
    const sy = toSvgY(y);
    svgParts.push(`<line x1="0" y1="${sy}" x2="${svgW}" y2="${sy}" class="grid-line"/>`);
  }
  svgParts.push('</g>');

  // 3. Room Floors & Labels
  svgParts.push('<g id="rooms">');
  for (const r of rooms) {
    if (r.polygon.length < 3) continue;
    const ptsStr = r.polygon
      .map((p) => `${toSvgX(p.x).toFixed(1)},${toSvgY(p.y).toFixed(1)}`)
      .join(' ');
    svgParts.push(`<polygon points="${ptsStr}" class="room-fill"/>`);

    let avgX = 0;
    let avgY = 0;
    for (const p of r.polygon) {
      avgX += p.x;
      avgY += p.y;
    }
    avgX /= r.polygon.length;
    avgY /= r.polygon.length;

    const lblX = toSvgX(avgX);
    const lblY = toSvgY(avgY);
    svgParts.push(
      `<text x="${lblX}" y="${lblY - 7}" class="room-text-title">${r.name}</text>`
    );
    svgParts.push(
      `<text x="${lblX}" y="${lblY + 11}" class="room-text-sub">${r.area.toFixed(3)} m²</text>`
    );
  }
  svgParts.push('</g>');

  // 4. Walls
  svgParts.push('<g id="walls">');
  for (const w of Object.values(walls)) {
    const p1 = vertices[w.startId];
    const p2 = vertices[w.endId];
    if (!p1 || !p2) continue;

    const x1 = toSvgX(p1.x);
    const y1 = toSvgY(p1.y);
    const x2 = toSvgX(p2.x);
    const y2 = toSvgY(p2.y);
    const thickPx = Math.max(4, w.thickness * scale);

    svgParts.push(
      `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="wall-thick" stroke-width="${thickPx}"/>`
    );
    svgParts.push(
      `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="wall-core" stroke-width="${Math.max(1, thickPx - 4)}"/>`
    );

    // Dimension label
    const wallLen = distance(p1, p2);
    if (wallLen > 0.6) {
      const mid = midpoint(p1, p2);
      const mx = toSvgX(mid.x);
      const my = toSvgY(mid.y);
      svgParts.push(
        `<text x="${mx}" y="${my - thickPx / 2 - 4}" class="dim-text">${wallLen.toFixed(2)}m</text>`
      );
    }
  }
  svgParts.push('</g>');

  // 5. Openings (Doors with Swing Arcs & Windows)
  svgParts.push('<g id="openings">');
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

    const startPt = { x: p1.x + uStart * Math.cos(angle), y: p1.y + uStart * Math.sin(angle) };
    const endPt = { x: p1.x + uEnd * Math.cos(angle), y: p1.y + uEnd * Math.sin(angle) };

    const sx1 = toSvgX(startPt.x);
    const sy1 = toSvgY(startPt.y);
    const sx2 = toSvgX(endPt.x);
    const sy2 = toSvgY(endPt.y);
    const wallThickPx = Math.max(4, wall.thickness * scale);

    // Clear wall void
    svgParts.push(
      `<line x1="${sx1}" y1="${sy1}" x2="${sx2}" y2="${sy2}" stroke="#0b1120" stroke-width="${wallThickPx + 2}"/>`
    );

    if (op.type === 'door') {
      const isLeft = op.swingDirection === 'left';
      const hx = isLeft ? sx1 : sx2;
      const hy = isLeft ? sy1 : sy2;
      const r = op.width * scale;

      const screenWallAngle = Math.atan2(sy2 - sy1, sx2 - sx1);
      const swingSign = isLeft ? 1 : -1;
      const startAngle = isLeft ? screenWallAngle : screenWallAngle + Math.PI;
      const endAngle = startAngle - (Math.PI / 2) * swingSign;

      const ax1 = hx + r * Math.cos(startAngle);
      const ay1 = hy + r * Math.sin(startAngle);
      const ax2 = hx + r * Math.cos(endAngle);
      const ay2 = hy + r * Math.sin(endAngle);

      // Arc path
      svgParts.push(
        `<path d="M ${ax1} ${ay1} A ${r} ${r} 0 0 ${isLeft ? 0 : 1} ${ax2} ${ay2}" class="door-arc"/>`
      );
      // Door Leaf
      svgParts.push(`<line x1="${hx}" y1="${hy}" x2="${ax2}" y2="${ay2}" class="door-leaf"/>`);
    } else {
      // Window lines
      svgParts.push(`<line x1="${sx1}" y1="${sy1}" x2="${sx2}" y2="${sy2}" class="win-frame"/>`);
    }
  }
  svgParts.push('</g>');

  // 6. Furniture
  svgParts.push('<g id="furniture">');
  for (const item of Object.values(furniture)) {
    const footprint = getFurnitureFootprint(item);
    const pts = footprint.corners
      .map((c) => `${toSvgX(c.x).toFixed(1)},${toSvgY(c.y).toFixed(1)}`)
      .join(' ');
    const cls = item.isFloorCovering ? 'furn-rug' : 'furn-box';
    svgParts.push(`<polygon points="${pts}" class="${cls}"/>`);

    const cx = toSvgX(item.x);
    const cy = toSvgY(item.y);
    svgParts.push(`<text x="${cx}" y="${cy}" class="furn-text">${item.name}</text>`);
  }
  svgParts.push('</g>');

  // 7. Architectural Title Block & Scale Bar
  svgParts.push(`
  <g id="title-block" transform="translate(15, ${svgH - 65})">
    <rect width="260" height="50" rx="6" fill="#0f172a" stroke="#334155" stroke-width="1"/>
    <text x="12" y="20" font-family="system-ui, sans-serif" font-size="12" font-weight="bold" fill="#38bdf8">${design.name}</text>
    <text x="12" y="38" font-family="system-ui, sans-serif" font-size="10" fill="#94a3b8">Metric Blueprint | Scale ${scaleLabel} | MindSpace</text>
  </g>
  </svg>`);

  return svgParts.join('\n');
}
