import React, { useRef, useEffect, useState, useCallback } from 'react';
import {
  Point2D,
  Wall,
  Opening,
  Room,
  FurnitureItem,
  SelectionState,
  EditorMode,
} from '../types/plan.js';
import {
  ViewportTransform,
  renderBlueprint2D,
  screenToWorld,
  worldToScreen,
} from './renderer2d.js';
import {
  distance,
  snapToGrid,
  snapPointToGrid,
  snapPointToAngle,
  closestPointOnSegment,
} from '../core/geometry.js';
import { DoorSwingConflict } from '../core/collision.js';

interface BlueprintCanvasProps {
  vertices: Record<string, Point2D>;
  walls: Record<string, Wall>;
  openings: Record<string, Opening>;
  furniture: Record<string, FurnitureItem>;
  rooms: Room[];
  selection: SelectionState;
  editorMode: EditorMode;
  pendingCatalogItem: string | null;
  doorConflicts: Map<string, DoorSwingConflict>;
  collidingFurnitureIds: Set<string>;
  onSelect: (selection: SelectionState) => void;
  onAddWall: (start: Point2D, end: Point2D) => void;
  onUpdateVertex: (id: string, x: number, y: number) => void;
  onAddOpening: (wallId: string, type: 'door' | 'window', offset: number) => void;
  onUpdateOpeningOffset: (id: string, offset: number) => void;
  onAddFurniture: (catalogId: string, x: number, y: number) => void;
  onUpdateFurniture: (id: string, updates: Partial<FurnitureItem>) => void;
  onDeleteSelected: () => void;
}

export const BlueprintCanvas: React.FC<BlueprintCanvasProps> = ({
  vertices,
  walls,
  openings,
  furniture,
  rooms,
  selection,
  editorMode,
  pendingCatalogItem,
  doorConflicts,
  collidingFurnitureIds,
  onSelect,
  onAddWall,
  onUpdateVertex,
  onAddOpening,
  onUpdateOpeningOffset,
  onAddFurniture,
  onUpdateFurniture,
  onDeleteSelected,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Viewport Transform (Zoom & Pan)
  const [transform, setTransform] = useState<ViewportTransform>({
    zoom: 50, // 50 pixels per meter
    panX: 0,
    panY: 0,
  });

  // Interaction States
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const [dragVertexId, setDragVertexId] = useState<string | null>(null);
  const [dragFurnitureId, setDragFurnitureId] = useState<string | null>(null);
  const [dragFurnitureOffset, setDragFurnitureOffset] = useState<{ x: number; y: number }>({
    x: 0,
    y: 0,
  });

  const [drawingStartPoint, setDrawingStartPoint] = useState<Point2D | null>(null);
  const [tempMouseWorld, setTempMouseWorld] = useState<Point2D | null>(null);

  // Measure dynamic container dimensions
  const [dimensions, setDimensions] = useState<{ width: number; height: number }>({
    width: 800,
    height: 600,
  });

  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };
    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, []);

  // Snap search helper: find magnetic vertex or wall midpoint within snap threshold
  const findSnapTarget = useCallback(
    (worldPos: { x: number; y: number }, snapRadiusMeters = 0.25) => {
      let nearestVertex: Point2D | null = null;
      let minVDist = snapRadiusMeters;

      for (const v of Object.values(vertices)) {
        const d = distance(worldPos, v);
        if (d < minVDist) {
          minVDist = d;
          nearestVertex = v;
        }
      }

      if (nearestVertex) {
        return { point: { x: nearestVertex.x, y: nearestVertex.y }, vertexId: nearestVertex.id };
      }

      // Check wall midpoints
      for (const wall of Object.values(walls)) {
        const p1 = vertices[wall.startId];
        const p2 = vertices[wall.endId];
        if (!p1 || !p2) continue;
        const mid = { x: (p1.x + p2.x) / 2, y: (p1.y + p2.y) / 2 };
        const d = distance(worldPos, mid);
        if (d < snapRadiusMeters) {
          return { point: mid, vertexId: null };
        }
      }

      // Fallback: grid snap
      return { point: snapPointToGrid(worldPos, 0.1), vertexId: null };
    },
    [vertices, walls]
  );

  // Redraw Canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Handle High-DPI
    const dpr = window.devicePixelRatio || 1;
    canvas.width = dimensions.width * dpr;
    canvas.height = dimensions.height * dpr;
    ctx.scale(dpr, dpr);

    let drawingTempWall: { start: Point2D; end: Point2D } | null = null;
    if (editorMode === 'draw_wall' && drawingStartPoint && tempMouseWorld) {
      drawingTempWall = {
        start: drawingStartPoint,
        end: tempMouseWorld,
      };
    }

    renderBlueprint2D(
      ctx,
      dimensions.width,
      dimensions.height,
      transform,
      vertices,
      walls,
      openings,
      furniture,
      rooms,
      selection,
      doorConflicts,
      collidingFurnitureIds,
      drawingTempWall
    );
  }, [
    dimensions,
    transform,
    vertices,
    walls,
    openings,
    furniture,
    rooms,
    selection,
    doorConflicts,
    collidingFurnitureIds,
    editorMode,
    drawingStartPoint,
    tempMouseWorld,
  ]);

  // Pointer & Mouse Handlers
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    // Pan with Middle Click or Alt/Space + Left Click
    if (e.button === 1 || (e.button === 0 && e.altKey)) {
      setIsPanning(true);
      setPanStart({ x: sx - transform.panX, y: sy - transform.panY });
      return;
    }

    if (e.button !== 0) return; // Only process left click

    const rawWorld = screenToWorld(sx, sy, transform, dimensions.width, dimensions.height);
    const snapResult = findSnapTarget(rawWorld);

    // 1. Tool: Draw Wall
    if (editorMode === 'draw_wall') {
      if (!drawingStartPoint) {
        // Start wall
        setDrawingStartPoint({
          id: snapResult.vertexId || `v_${Date.now()}`,
          x: snapResult.point.x,
          y: snapResult.point.y,
        });
      } else {
        // Complete wall
        const endPt: Point2D = {
          id: snapResult.vertexId || `v_${Date.now()}`,
          x: snapResult.point.x,
          y: snapResult.point.y,
        };
        if (distance(drawingStartPoint, endPt) > 0.1) {
          onAddWall(drawingStartPoint, endPt);
          // Chain to next wall
          setDrawingStartPoint(endPt);
        }
      }
      return;
    }

    // 2. Tool: Place Door / Window
    if (editorMode === 'place_door' || editorMode === 'place_window') {
      const type = editorMode === 'place_door' ? 'door' : 'window';
      // Find nearest wall
      let nearestWall: Wall | null = null;
      let minWallDist = 0.5; // within 0.5m of wall
      let bestOffset = 0.5;

      for (const w of Object.values(walls)) {
        const p1 = vertices[w.startId];
        const p2 = vertices[w.endId];
        if (!p1 || !p2) continue;
        const { point, t } = closestPointOnSegment(p1, p2, rawWorld);
        const d = distance(point, rawWorld);
        if (d < minWallDist) {
          minWallDist = d;
          nearestWall = w;
          bestOffset = t;
        }
      }

      if (nearestWall) {
        onAddOpening(nearestWall.id, type, bestOffset);
      }
      return;
    }

    // 3. Tool: Place Furniture
    if (editorMode === 'place_furniture' && pendingCatalogItem) {
      const snapped = snapPointToGrid(rawWorld, 0.1);
      onAddFurniture(pendingCatalogItem, snapped.x, snapped.y);
      return;
    }

    // 4. Select Mode: Hit Testing
    // A. Check Vertices
    for (const v of Object.values(vertices)) {
      if (distance(rawWorld, v) < 0.2) {
        onSelect({ type: 'vertex', id: v.id });
        setDragVertexId(v.id);
        return;
      }
    }

    // B. Check Furniture
    for (const f of Object.values(furniture)) {
      const halfW = f.width / 2;
      const halfD = f.depth / 2;
      if (
        Math.abs(rawWorld.x - f.x) <= halfW + 0.1 &&
        Math.abs(rawWorld.y - f.y) <= halfD + 0.1
      ) {
        onSelect({ type: 'furniture', id: f.id });
        setDragFurnitureId(f.id);
        setDragFurnitureOffset({ x: rawWorld.x - f.x, y: rawWorld.y - f.y });
        return;
      }
    }

    // C. Check Openings
    for (const op of Object.values(openings)) {
      const wall = walls[op.wallId];
      if (!wall) continue;
      const p1 = vertices[wall.startId];
      const p2 = vertices[wall.endId];
      if (!p1 || !p2) continue;
      const wallLen = distance(p1, p2);
      const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);
      const opCenter = {
        x: p1.x + op.offset * wallLen * Math.cos(angle),
        y: p1.y + op.offset * wallLen * Math.sin(angle),
      };
      if (distance(rawWorld, opCenter) < op.width / 2 + 0.15) {
        onSelect({ type: 'opening', id: op.id });
        return;
      }
    }

    // D. Check Walls
    for (const wall of Object.values(walls)) {
      const p1 = vertices[wall.startId];
      const p2 = vertices[wall.endId];
      if (!p1 || !p2) continue;
      const { point } = closestPointOnSegment(p1, p2, rawWorld);
      if (distance(point, rawWorld) < wall.thickness / 2 + 0.15) {
        onSelect({ type: 'wall', id: wall.id });
        return;
      }
    }

    // E. Check Rooms
    for (const room of rooms) {
      // Fast rough bounding box check
      let inside = false;
      const poly = room.polygon;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const xi = poly[i].x;
        const yi = poly[i].y;
        const xj = poly[j].x;
        const yj = poly[j].y;
        const intersect =
          yi > rawWorld.y !== yj > rawWorld.y &&
          rawWorld.x < ((xj - xi) * (rawWorld.y - yi)) / (yj - yi + 1e-12) + xi;
        if (intersect) inside = !inside;
      }
      if (inside) {
        onSelect({ type: 'room', id: room.id });
        return;
      }
    }

    // Deselect if clicked empty area
    onSelect({ type: 'none', id: null });
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    if (isPanning) {
      setTransform((prev) => ({
        ...prev,
        panX: sx - panStart.x,
        panY: sy - panStart.y,
      }));
      return;
    }

    const rawWorld = screenToWorld(sx, sy, transform, dimensions.width, dimensions.height);

    // Dragging Vertex
    if (dragVertexId) {
      const snapped = snapPointToGrid(rawWorld, 0.1);
      onUpdateVertex(dragVertexId, snapped.x, snapped.y);
      return;
    }

    // Dragging Furniture
    if (dragFurnitureId) {
      const targetX = snapToGrid(rawWorld.x - dragFurnitureOffset.x, 0.1);
      const targetY = snapToGrid(rawWorld.y - dragFurnitureOffset.y, 0.1);
      onUpdateFurniture(dragFurnitureId, { x: targetX, y: targetY });
      return;
    }

    // Drawing Wall Preview with 45-degree angle snap
    if (editorMode === 'draw_wall' && drawingStartPoint) {
      const angleSnapped = snapPointToAngle(drawingStartPoint, rawWorld, 45);
      const snapResult = findSnapTarget(angleSnapped);
      setTempMouseWorld({
        id: 'temp_mouse',
        x: snapResult.point.x,
        y: snapResult.point.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsPanning(false);
    setDragVertexId(null);
    setDragFurnitureId(null);
  };

  // Zoom with Wheel
  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;

    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    const newZoom = Math.min(300, Math.max(10, transform.zoom * zoomFactor));

    // Keep point under cursor invariant
    const worldBefore = screenToWorld(sx, sy, transform, dimensions.width, dimensions.height);
    const newPanX = sx - dimensions.width / 2 - worldBefore.x * newZoom;
    const newPanY = sy - dimensions.height / 2 + worldBefore.y * newZoom;

    setTransform({
      zoom: newZoom,
      panX: newPanX,
      panY: newPanY,
    });
  };

  // Keyboard Shortcuts: Escape, Delete, 'r' for rotate
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setDrawingStartPoint(null);
        setTempMouseWorld(null);
        onSelect({ type: 'none', id: null });
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selection.type !== 'none') {
          onDeleteSelected();
        }
      } else if (e.key === 'r' || e.key === 'R') {
        if (selection.type === 'furniture' && selection.id) {
          const item = furniture[selection.id];
          if (item) {
            const nextRot = (item.rotation + Math.PI / 4) % (2 * Math.PI);
            onUpdateFurniture(selection.id, { rotation: nextRot });
          }
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selection, furniture, onDeleteSelected, onSelect, onUpdateFurniture]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full overflow-hidden bg-slate-950 select-none cursor-crosshair"
    >
      <canvas
        ref={canvasRef}
        style={{ width: dimensions.width, height: dimensions.height }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onWheel={handleWheel}
        className="block touch-none"
      />

      {/* Floating Blueprint Scale & Metric HUD */}
      <div className="absolute bottom-3 left-3 bg-slate-900/80 backdrop-blur border border-slate-800 text-xs text-slate-300 px-3 py-1.5 rounded-lg flex items-center space-x-3 pointer-events-none shadow-md">
        <span className="font-mono text-sky-400 font-semibold">1:50 Blueprint</span>
        <span className="text-slate-500">|</span>
        <span>Grid: 0.1m snap</span>
        <span className="text-slate-500">|</span>
        <span>Zoom: {Math.round((transform.zoom / 50) * 100)}%</span>
      </div>

      {/* Helper Notification for Drawing Mode */}
      {editorMode === 'draw_wall' && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-sky-950/90 border border-sky-500/50 text-sky-200 text-xs px-3.5 py-1.5 rounded-full shadow-lg pointer-events-none flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse"></span>
          <span>Click to place wall corners (Snaps to 0.1m and 45°). Press Esc to finish.</span>
        </div>
      )}
    </div>
  );
};
