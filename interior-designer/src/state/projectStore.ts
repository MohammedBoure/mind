/**
 * Central State Management & Persistence Engine
 * Supports 100-step Undo/Redo history stack, auto-save to localStorage,
 * real-time room topology recalculation, and collision conflict tracking.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Point2D,
  Wall,
  Opening,
  Room,
  FurnitureItem,
  SelectionState,
  EditorMode,
  ViewLayout,
  AlternativeDesign,
  ProjectSettings,
} from '../types/plan.js';
import { createDefaultProject } from './defaultProject.js';
import { detectRooms } from '../core/roomDetection.js';
import {
  checkDoorSwingClearance,
  checkFurnitureCollision,
  DoorSwingConflict,
} from '../core/collision.js';
import { CATALOG_MAP } from '../catalog/items.js';

const STORAGE_KEY = 'mindspace_project_v1';
const MAX_UNDO_STACK = 100;

export function useProjectStore() {
  // Load initial project from localStorage or default
  const [projectData, setProjectData] = useState(() => {
    if (typeof window !== 'undefined') {
      try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
          const parsed = JSON.parse(saved);
          if (parsed && Array.isArray(parsed.alternatives) && parsed.alternatives.length > 0) {
            return parsed;
          }
        }
      } catch (err) {
        console.warn('Failed to parse saved project from localStorage:', err);
      }
    }
    return createDefaultProject();
  });

  const { activeAlternativeId, alternatives, settings } = projectData;

  // Active alternative helper
  const activeAlt: AlternativeDesign =
    alternatives.find((a: AlternativeDesign) => a.id === activeAlternativeId) ||
    alternatives[0];

  // UI Modes & States
  const [editorMode, setEditorMode] = useState<EditorMode>('select');
  const [viewLayout, setViewLayout] = useState<ViewLayout>('split');
  const [isWalkthrough, setIsWalkthrough] = useState(false);
  const [pendingCatalogItem, setPendingCatalogItem] = useState<string | null>(null);
  const [selection, setSelection] = useState<SelectionState>({ type: 'none', id: null });

  // Undo / Redo Stacks (stores AlternativeDesign snapshots)
  const undoStackRef = useRef<AlternativeDesign[]>([]);
  const redoStackRef = useRef<AlternativeDesign[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  // Push current state to undo history before mutation
  const pushHistorySnapshot = useCallback(() => {
    const clone: AlternativeDesign = JSON.parse(JSON.stringify(activeAlt));
    undoStackRef.current.push(clone);
    if (undoStackRef.current.length > MAX_UNDO_STACK) {
      undoStackRef.current.shift();
    }
    redoStackRef.current = []; // Clear redo stack on new action
    setCanUndo(true);
    setCanRedo(false);
  }, [activeAlt]);

  // Save to localStorage with debounce
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const handler = setTimeout(() => {
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(projectData));
        } catch (e) {
          console.error('Failed to auto-save project:', e);
        }
      }, 400);
      return () => clearTimeout(handler);
    }
  }, [projectData]);

  // Compute Spatial Intelligence & Collision Caches
  const doorConflicts = new Map<string, DoorSwingConflict>();
  const collidingFurnitureIds = new Set<string>();

  const furnitureList: FurnitureItem[] = Object.values(activeAlt.furniture || {});
  const openingsList: Opening[] = Object.values(activeAlt.openings || {});

  // 1. Check Door Swing Clearances
  for (const op of openingsList) {
    if (op.type === 'door') {
      const wall = activeAlt.walls[op.wallId];
      if (wall) {
        const conflict = checkDoorSwingClearance(
          op,
          wall,
          activeAlt.vertices,
          furnitureList
        );
        if (conflict) {
          doorConflicts.set(op.id, conflict);
          for (const fid of conflict.collidingFurnitureIds) {
            collidingFurnitureIds.add(fid);
          }
        }
      }
    }
  }

  // 2. Check Furniture vs Furniture Collisions (excluding non-blocking floor coverings)
  for (let i = 0; i < furnitureList.length; i++) {
    for (let j = i + 1; j < furnitureList.length; j++) {
      const itemA = furnitureList[i];
      const itemB = furnitureList[j];
      if (checkFurnitureCollision(itemA, itemB)) {
        collidingFurnitureIds.add(itemA.id);
        collidingFurnitureIds.add(itemB.id);
      }
    }
  }

  // Helper to commit updated active alternative
  const updateActiveAlternative = useCallback(
    (updater: (alt: AlternativeDesign) => AlternativeDesign) => {
      setProjectData((prev: any) => {
        const updatedAlts = prev.alternatives.map((a: AlternativeDesign) => {
          if (a.id === prev.activeAlternativeId) {
            const nextAlt = updater(a);
            // Automatically recalculate room topology when walls or vertices change
            nextAlt.rooms = detectRooms(nextAlt.vertices, nextAlt.walls, nextAlt.rooms);
            nextAlt.updatedAt = Date.now();
            return nextAlt;
          }
          return a;
        });
        return {
          ...prev,
          alternatives: updatedAlts,
        };
      });
    },
    []
  );

  // --- ACTIONS ---

  // Undo
  const undo = useCallback(() => {
    if (undoStackRef.current.length === 0) return;
    const previousSnapshot = undoStackRef.current.pop()!;
    redoStackRef.current.push(JSON.parse(JSON.stringify(activeAlt)));

    setProjectData((prev: any) => ({
      ...prev,
      alternatives: prev.alternatives.map((a: AlternativeDesign) =>
        a.id === prev.activeAlternativeId ? previousSnapshot : a
      ),
    }));

    setCanUndo(undoStackRef.current.length > 0);
    setCanRedo(true);
    setSelection({ type: 'none', id: null });
  }, [activeAlt]);

  // Redo
  const redo = useCallback(() => {
    if (redoStackRef.current.length === 0) return;
    const nextSnapshot = redoStackRef.current.pop()!;
    undoStackRef.current.push(JSON.parse(JSON.stringify(activeAlt)));

    setProjectData((prev: any) => ({
      ...prev,
      alternatives: prev.alternatives.map((a: AlternativeDesign) =>
        a.id === prev.activeAlternativeId ? nextSnapshot : a
      ),
    }));

    setCanUndo(true);
    setCanRedo(redoStackRef.current.length > 0);
    setSelection({ type: 'none', id: null });
  }, [activeAlt]);

  // Add Wall
  const addWall = useCallback(
    (start: Point2D, end: Point2D) => {
      pushHistorySnapshot();
      updateActiveAlternative((alt) => {
        const newVerts = { ...alt.vertices };
        newVerts[start.id] = start;
        newVerts[end.id] = end;

        const wallId = `wall_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
        const newWall: Wall = {
          id: wallId,
          startId: start.id,
          endId: end.id,
          thickness: settings.defaultWallThickness,
          height: settings.defaultWallHeight,
          finish: 'paint_white',
        };

        return {
          ...alt,
          vertices: newVerts,
          walls: { ...alt.walls, [wallId]: newWall },
        };
      });
    },
    [pushHistorySnapshot, updateActiveAlternative, settings]
  );

  // Update Vertex position
  const updateVertex = useCallback(
    (id: string, x: number, y: number) => {
      updateActiveAlternative((alt) => {
        if (!alt.vertices[id]) return alt;
        return {
          ...alt,
          vertices: {
            ...alt.vertices,
            [id]: { ...alt.vertices[id], x, y },
          },
        };
      });
    },
    [updateActiveAlternative]
  );

  // Update Wall properties
  const updateWall = useCallback(
    (id: string, updates: Partial<Wall>) => {
      updateActiveAlternative((alt) => {
        if (!alt.walls[id]) return alt;
        return {
          ...alt,
          walls: {
            ...alt.walls,
            [id]: { ...alt.walls[id], ...updates },
          },
        };
      });
    },
    [updateActiveAlternative]
  );

  // Add Opening (Door or Window)
  const addOpening = useCallback(
    (wallId: string, type: 'door' | 'window', offset: number) => {
      pushHistorySnapshot();
      updateActiveAlternative((alt) => {
        const opId = `op_${type}_${Date.now()}`;
        const isDoor = type === 'door';
        const newOp: Opening = {
          id: opId,
          wallId,
          type,
          offset: Math.max(0.1, Math.min(0.9, offset)),
          width: isDoor ? 0.9 : 1.4,
          height: isDoor ? 2.1 : 1.2,
          sillElevation: isDoor ? 0 : 0.9,
          swingAngle: isDoor ? 65 : 0,
          swingDirection: 'left',
          isOpen: isDoor,
          finish: isDoor ? 'wood_oak' : 'aluminum_black',
          costCents: isDoor ? 48000 : 36000,
        };
        return {
          ...alt,
          openings: { ...alt.openings, [opId]: newOp },
        };
      });
    },
    [pushHistorySnapshot, updateActiveAlternative]
  );

  // Update Opening offset or properties
  const updateOpening = useCallback(
    (id: string, updates: Partial<Opening>) => {
      updateActiveAlternative((alt) => {
        if (!alt.openings[id]) return alt;
        return {
          ...alt,
          openings: {
            ...alt.openings,
            [id]: { ...alt.openings[id], ...updates },
          },
        };
      });
    },
    [updateActiveAlternative]
  );

  // Add Furniture from catalog
  const addFurniture = useCallback(
    (catalogId: string, x: number, y: number) => {
      const catItem = CATALOG_MAP.get(catalogId);
      if (!catItem) return;

      pushHistorySnapshot();
      updateActiveAlternative((alt) => {
        const fid = `furn_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
        const newFurn: FurnitureItem = {
          id: fid,
          catalogId: catItem.id,
          name: catItem.name,
          x,
          y,
          z: catItem.category === 'lighting' ? 2.2 : 0,
          rotation: 0,
          width: catItem.defaultWidth,
          depth: catItem.defaultDepth,
          height: catItem.defaultHeight,
          isFloorCovering: catItem.isFloorCovering,
          finish: catItem.defaultFinish,
          costCents: catItem.defaultCostCents,
        };
        return {
          ...alt,
          furniture: { ...alt.furniture, [fid]: newFurn },
        };
      });
      setSelection({ type: 'furniture', id: null });
    },
    [pushHistorySnapshot, updateActiveAlternative]
  );

  // Update Furniture properties
  const updateFurniture = useCallback(
    (id: string, updates: Partial<FurnitureItem>) => {
      updateActiveAlternative((alt) => {
        if (!alt.furniture[id]) return alt;
        return {
          ...alt,
          furniture: {
            ...alt.furniture,
            [id]: { ...alt.furniture[id], ...updates },
          },
        };
      });
    },
    [updateActiveAlternative]
  );

  // Update Room properties
  const updateRoom = useCallback(
    (id: string, updates: Partial<Room>) => {
      updateActiveAlternative((alt) => {
        return {
          ...alt,
          rooms: alt.rooms.map((r) => (r.id === id ? { ...r, ...updates } : r)),
        };
      });
    },
    [updateActiveAlternative]
  );

  // Delete currently selected element
  const deleteSelected = useCallback(() => {
    if (!selection.id || selection.type === 'none') return;
    pushHistorySnapshot();

    updateActiveAlternative((alt) => {
      if (selection.type === 'furniture') {
        const newFurn = { ...alt.furniture };
        delete newFurn[selection.id!];
        return { ...alt, furniture: newFurn };
      }
      if (selection.type === 'opening') {
        const newOps = { ...alt.openings };
        delete newOps[selection.id!];
        return { ...alt, openings: newOps };
      }
      if (selection.type === 'wall') {
        const newWalls = { ...alt.walls };
        delete newWalls[selection.id!];
        // Remove openings on this wall
        const newOps = { ...alt.openings };
        for (const [opId, op] of Object.entries(newOps)) {
          if (op.wallId === selection.id) {
            delete newOps[opId];
          }
        }
        return { ...alt, walls: newWalls, openings: newOps };
      }
      if (selection.type === 'vertex') {
        const newVerts = { ...alt.vertices };
        delete newVerts[selection.id!];
        // Remove walls connected to this vertex
        const newWalls = { ...alt.walls };
        const removedWallIds = new Set<string>();
        for (const [wId, w] of Object.entries(newWalls)) {
          if (w.startId === selection.id || w.endId === selection.id) {
            removedWallIds.add(wId);
            delete newWalls[wId];
          }
        }
        // Remove associated openings
        const newOps = { ...alt.openings };
        for (const [opId, op] of Object.entries(newOps)) {
          if (removedWallIds.has(op.wallId)) {
            delete newOps[opId];
          }
        }
        return { ...alt, vertices: newVerts, walls: newWalls, openings: newOps };
      }
      return alt;
    });

    setSelection({ type: 'none', id: null });
  }, [selection, pushHistorySnapshot, updateActiveAlternative]);

  // Alternatives management
  const switchAlternative = useCallback((id: string) => {
    setProjectData((prev: any) => ({
      ...prev,
      activeAlternativeId: id,
    }));
    setSelection({ type: 'none', id: null });
    undoStackRef.current = [];
    redoStackRef.current = [];
    setCanUndo(false);
    setCanRedo(false);
  }, []);

  const branchAlternative = useCallback(
    (newName: string, newDesc = '') => {
      const newAlt: AlternativeDesign = {
        id: `alt_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
        name: newName,
        description: newDesc,
        vertices: JSON.parse(JSON.stringify(activeAlt.vertices)),
        walls: JSON.parse(JSON.stringify(activeAlt.walls)),
        openings: JSON.parse(JSON.stringify(activeAlt.openings)),
        furniture: JSON.parse(JSON.stringify(activeAlt.furniture)),
        rooms: JSON.parse(JSON.stringify(activeAlt.rooms)),
        wallFinishCostPerM2: activeAlt.wallFinishCostPerM2,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      };

      setProjectData((prev: any) => ({
        ...prev,
        activeAlternativeId: newAlt.id,
        alternatives: [...prev.alternatives, newAlt],
      }));
    },
    [activeAlt]
  );

  const deleteAlternative = useCallback(
    (id: string) => {
      setProjectData((prev: any) => {
        if (prev.alternatives.length <= 1) return prev;
        const filtered = prev.alternatives.filter((a: AlternativeDesign) => a.id !== id);
        return {
          ...prev,
          activeAlternativeId: filtered[0].id,
          alternatives: filtered,
        };
      });
    },
    []
  );

  // Settings
  const toggleCutaway = useCallback(() => {
    setProjectData((prev: any) => ({
      ...prev,
      settings: {
        ...prev.settings,
        cutawayMode: !prev.settings.cutawayMode,
      },
    }));
  }, []);

  const resetProject = useCallback(() => {
    const def = createDefaultProject();
    setProjectData(def);
    setSelection({ type: 'none', id: null });
    undoStackRef.current = [];
    redoStackRef.current = [];
    setCanUndo(false);
    setCanRedo(false);
  }, []);

  const loadProjectData = useCallback((newData: any) => {
    setProjectData(newData);
    setSelection({ type: 'none', id: null });
    undoStackRef.current = [];
    redoStackRef.current = [];
    setCanUndo(false);
    setCanRedo(false);
  }, []);

  return {
    activeAlt,
    activeAlternativeId,
    alternatives,
    settings,
    editorMode,
    viewLayout,
    isWalkthrough,
    pendingCatalogItem,
    selection,
    doorConflicts,
    collidingFurnitureIds,
    canUndo,
    canRedo,
    setEditorMode,
    setViewLayout,
    setIsWalkthrough,
    setPendingCatalogItem,
    setSelection,
    addWall,
    updateWall,
    updateVertex,
    addOpening,
    updateOpening,
    addFurniture,
    updateFurniture,
    updateRoom,
    deleteSelected,
    undo,
    redo,
    switchAlternative,
    branchAlternative,
    deleteAlternative,
    toggleCutaway,
    resetProject,
    loadProjectData,
  };
}
