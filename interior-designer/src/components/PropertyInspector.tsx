import React from 'react';
import {
  SelectionState,
  Wall,
  Opening,
  Room,
  FurnitureItem,
} from '../types/plan.js';
import { DoorSwingConflict } from '../core/collision.js';
import { formatCurrency } from '../core/boqCalculator.js';
import {
  Sliders,
  AlertTriangle,
  Trash2,
  Maximize2,
  Compass,
  DollarSign,
  Palette,
} from 'lucide-react';

interface PropertyInspectorProps {
  selection: SelectionState;
  walls: Record<string, Wall>;
  openings: Record<string, Opening>;
  furniture: Record<string, FurnitureItem>;
  rooms: Room[];
  doorConflicts: Map<string, DoorSwingConflict>;
  collidingFurnitureIds: Set<string>;
  onUpdateWall: (id: string, updates: Partial<Wall>) => void;
  onUpdateOpening: (id: string, updates: Partial<Opening>) => void;
  onUpdateFurniture: (id: string, updates: Partial<FurnitureItem>) => void;
  onUpdateRoom: (id: string, updates: Partial<Room>) => void;
  onDeleteSelected: () => void;
  onClose: () => void;
}

export const PropertyInspector: React.FC<PropertyInspectorProps> = ({
  selection,
  walls,
  openings,
  furniture,
  rooms,
  doorConflicts,
  collidingFurnitureIds,
  onUpdateWall,
  onUpdateOpening,
  onUpdateFurniture,
  onUpdateRoom,
  onDeleteSelected,
}) => {
  // 1. Wall Inspector
  if (selection.type === 'wall' && selection.id) {
    const wall = walls[selection.id];
    if (!wall) return null;

    return (
      <aside className="w-80 bg-slate-900 border-l border-slate-800 p-4 flex flex-col space-y-4 select-none overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <Sliders className="w-4 h-4 text-sky-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Wall Properties
            </h2>
          </div>
          <button
            onClick={onDeleteSelected}
            className="p-1 rounded text-rose-400 hover:text-white hover:bg-rose-600/30 transition"
            title="Delete Wall"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3 text-xs">
          <div>
            <label className="text-slate-400 block mb-1">Thickness (m)</label>
            <input
              type="number"
              step="0.05"
              min="0.1"
              max="0.6"
              value={wall.thickness}
              onChange={(e) => onUpdateWall(wall.id, { thickness: parseFloat(e.target.value) || 0.2 })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none focus:border-sky-500 font-mono"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1">Wall Height (m)</label>
            <input
              type="number"
              step="0.1"
              min="1.5"
              max="5.0"
              value={wall.height}
              onChange={(e) => onUpdateWall(wall.id, { height: parseFloat(e.target.value) || 2.8 })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none focus:border-sky-500 font-mono"
            />
          </div>

          <div>
            <label className="text-slate-400 block mb-1">Finish / Material</label>
            <select
              value={wall.finish}
              onChange={(e) => onUpdateWall(wall.id, { finish: e.target.value })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none focus:border-sky-500 cursor-pointer"
            >
              <option value="paint_white">Architectural Paint (Off-White)</option>
              <option value="wood_panel">Natural Timber Paneling</option>
              <option value="concrete">Polished Concrete</option>
              <option value="brick">Exposed Architectural Brick</option>
            </select>
          </div>
        </div>
      </aside>
    );
  }

  // 2. Opening (Door / Window) Inspector
  if (selection.type === 'opening' && selection.id) {
    const op = openings[selection.id];
    if (!op) return null;
    const isDoor = op.type === 'door';
    const hasConflict = doorConflicts.has(op.id);

    return (
      <aside className="w-80 bg-slate-900 border-l border-slate-800 p-4 flex flex-col space-y-4 select-none overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <Sliders className="w-4 h-4 text-sky-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              {isDoor ? 'Door Specifications' : 'Window Specifications'}
            </h2>
          </div>
          <button
            onClick={onDeleteSelected}
            className="p-1 rounded text-rose-400 hover:text-white hover:bg-rose-600/30 transition"
            title="Delete Opening"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        {/* Door Swing Clearance Warning Banner */}
        {hasConflict && (
          <div className="p-3 rounded-lg bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs flex items-start space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block">Door Swing Envelope Obstructed!</span>
              <span className="text-[11px] text-rose-300/80">
                Furniture items intersect the 90° radial door swing path. Relocate items for life-safety clearance.
              </span>
            </div>
          </div>
        )}

        <div className="space-y-3 text-xs">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-slate-400 block mb-1">Width (m)</label>
              <input
                type="number"
                step="0.05"
                min="0.6"
                max="3.0"
                value={op.width}
                onChange={(e) => onUpdateOpening(op.id, { width: parseFloat(e.target.value) || 0.9 })}
                className="w-full bg-slate-950 px-2.5 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none font-mono"
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-1">Height (m)</label>
              <input
                type="number"
                step="0.05"
                min="0.8"
                max="3.0"
                value={op.height}
                onChange={(e) => onUpdateOpening(op.id, { height: parseFloat(e.target.value) || 2.1 })}
                className="w-full bg-slate-950 px-2.5 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none font-mono"
              />
            </div>
          </div>

          <div>
            <label className="text-slate-400 block mb-1">Sill Elevation (m)</label>
            <input
              type="number"
              step="0.05"
              min="0.0"
              max="2.0"
              value={op.sillElevation}
              onChange={(e) => onUpdateOpening(op.id, { sillElevation: parseFloat(e.target.value) || 0 })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none font-mono"
            />
          </div>

          {isDoor && (
            <>
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-slate-400">Swing Angle</label>
                  <span className="font-mono text-sky-400">{op.swingAngle}°</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="110"
                  step="5"
                  value={op.swingAngle}
                  onChange={(e) => {
                    const angle = parseInt(e.target.value, 10);
                    onUpdateOpening(op.id, { swingAngle: angle, isOpen: angle > 0 });
                  }}
                  className="w-full accent-sky-500 cursor-pointer"
                />
                <span className="text-[10px] text-slate-500 block mt-1">
                  * Must be open &gt; 55° for first-person walkthrough traversal.
                </span>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Hinge Side</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => onUpdateOpening(op.id, { swingDirection: 'left' })}
                    className={`py-1.5 rounded-md text-xs font-medium transition ${
                      op.swingDirection === 'left'
                        ? 'bg-sky-600 text-white'
                        : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-white'
                    }`}
                  >
                    Left Hinge
                  </button>
                  <button
                    onClick={() => onUpdateOpening(op.id, { swingDirection: 'right' })}
                    className={`py-1.5 rounded-md text-xs font-medium transition ${
                      op.swingDirection === 'right'
                        ? 'bg-sky-600 text-white'
                        : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-white'
                    }`}
                  >
                    Right Hinge
                  </button>
                </div>
              </div>
            </>
          )}

          <div>
            <label className="text-slate-400 block mb-1">Unit Cost ($)</label>
            <input
              type="number"
              step="10"
              value={op.costCents / 100}
              onChange={(e) => onUpdateOpening(op.id, { costCents: Math.round((parseFloat(e.target.value) || 0) * 100) })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none font-mono"
            />
          </div>
        </div>
      </aside>
    );
  }

  // 3. Furniture Inspector
  if (selection.type === 'furniture' && selection.id) {
    const item = furniture[selection.id];
    if (!item) return null;
    const isColliding = collidingFurnitureIds.has(item.id);

    return (
      <aside className="w-80 bg-slate-900 border-l border-slate-800 p-4 flex flex-col space-y-4 select-none overflow-y-auto">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <Sliders className="w-4 h-4 text-sky-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Furniture Item
            </h2>
          </div>
          <button
            onClick={onDeleteSelected}
            className="p-1 rounded text-rose-400 hover:text-white hover:bg-rose-600/30 transition"
            title="Delete Item"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        {/* Collision Warning Banner */}
        {isColliding && (
          <div className="p-3 rounded-lg bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs flex items-start space-x-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block">Bounding Footprint Collision!</span>
              <span className="text-[11px] text-rose-300/80">
                This item overlaps another solid object or door swing path.
              </span>
            </div>
          </div>
        )}

        <div className="space-y-3 text-xs">
          <div>
            <label className="text-slate-400 block mb-1">Item Name</label>
            <input
              type="text"
              value={item.name}
              onChange={(e) => onUpdateFurniture(item.id, { name: e.target.value })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none font-medium"
            />
          </div>

          {/* Rotation Slider */}
          <div>
            <div className="flex justify-between items-center mb-1">
              <label className="text-slate-400 flex items-center gap-1">
                <Compass className="w-3.5 h-3.5" />
                <span>Rotation</span>
              </label>
              <span className="font-mono text-sky-400">
                {Math.round(((item.rotation * 180) / Math.PI) % 360)}°
              </span>
            </div>
            <input
              type="range"
              min="0"
              max={Math.PI * 2}
              step={Math.PI / 16}
              value={item.rotation}
              onChange={(e) => onUpdateFurniture(item.id, { rotation: parseFloat(e.target.value) })}
              className="w-full accent-sky-500 cursor-pointer"
            />
          </div>

          {/* Dimensions */}
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="text-slate-400 block mb-1">Width (m)</label>
              <input
                type="number"
                step="0.05"
                value={item.width}
                onChange={(e) => onUpdateFurniture(item.id, { width: parseFloat(e.target.value) || 0.5 })}
                className="w-full bg-slate-950 px-2 py-1.5 rounded-md border border-slate-800 text-slate-200 font-mono text-[11px]"
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-1">Depth (m)</label>
              <input
                type="number"
                step="0.05"
                value={item.depth}
                onChange={(e) => onUpdateFurniture(item.id, { depth: parseFloat(e.target.value) || 0.5 })}
                className="w-full bg-slate-950 px-2 py-1.5 rounded-md border border-slate-800 text-slate-200 font-mono text-[11px]"
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-1">Height (m)</label>
              <input
                type="number"
                step="0.05"
                value={item.height}
                onChange={(e) => onUpdateFurniture(item.id, { height: parseFloat(e.target.value) || 0.5 })}
                className="w-full bg-slate-950 px-2 py-1.5 rounded-md border border-slate-800 text-slate-200 font-mono text-[11px]"
              />
            </div>
          </div>

          <div>
            <label className="text-slate-400 block mb-1 flex items-center gap-1">
              <DollarSign className="w-3.5 h-3.5" />
              <span>Unit Cost ($)</span>
            </label>
            <input
              type="number"
              step="5"
              value={item.costCents / 100}
              onChange={(e) => onUpdateFurniture(item.id, { costCents: Math.round((parseFloat(e.target.value) || 0) * 100) })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none font-mono"
            />
          </div>

          {item.isFloorCovering && (
            <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-[11px]">
              ✓ Classified as thin floor covering (h ≤ 0.06m). Tables & chairs can sit over top.
            </div>
          )}
        </div>
      </aside>
    );
  }

  // 4. Room Inspector
  if (selection.type === 'room' && selection.id) {
    const room = rooms.find((r) => r.id === selection.id);
    if (!room) return null;

    return (
      <aside className="w-80 bg-slate-900 border-l border-slate-800 p-4 flex flex-col space-y-4 select-none overflow-y-auto">
        <div className="border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <Maximize2 className="w-4 h-4 text-sky-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Room Enclosure
            </h2>
          </div>
        </div>

        <div className="space-y-3 text-xs">
          <div>
            <label className="text-slate-400 block mb-1">Room Name</label>
            <input
              type="text"
              value={room.name}
              onChange={(e) => onUpdateRoom(room.id, { name: e.target.value })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none font-semibold"
            />
          </div>

          <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
            <div className="flex justify-between">
              <span className="text-slate-400">Enclosed Area:</span>
              <span className="font-mono font-bold text-sky-400">{room.area.toFixed(3)} m²</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Perimeter:</span>
              <span className="font-mono text-slate-300">{room.perimeter.toFixed(2)} m</span>
            </div>
          </div>

          <div>
            <label className="text-slate-400 block mb-1 flex items-center gap-1">
              <Palette className="w-3.5 h-3.5" />
              <span>Floor Finish</span>
            </label>
            <select
              value={room.floorFinish}
              onChange={(e) => onUpdateRoom(room.id, { floorFinish: e.target.value })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none cursor-pointer"
            >
              <option value="oak_parquet">Natural Oak Parquet</option>
              <option value="terrazzo">Honed Terrazzo Matrix</option>
              <option value="tile_subway">Subway Ceramic Tile</option>
              <option value="concrete">Polished Concrete</option>
              <option value="marble_carrara">Carrara Marble Slabs</option>
            </select>
          </div>

          <div>
            <label className="text-slate-400 block mb-1">Flooring Cost ($/m²)</label>
            <input
              type="number"
              step="5"
              value={room.floorCostCentsPerM2 / 100}
              onChange={(e) => onUpdateRoom(room.id, { floorCostCentsPerM2: Math.round((parseFloat(e.target.value) || 0) * 100) })}
              className="w-full bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 text-slate-200 outline-none font-mono"
            />
          </div>
        </div>
      </aside>
    );
  }

  // 5. Default Workspace Overview Inspector
  const totalRoomArea = rooms.reduce((acc, r) => acc + r.area, 0);

  return (
    <aside className="w-72 bg-slate-900 border-l border-slate-800 p-4 flex flex-col space-y-4 select-none">
      <div className="border-b border-slate-800 pb-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300">
          Workspace Overview
        </h2>
        <p className="text-[11px] text-slate-500 mt-0.5">Click any element in 2D or 3D to inspect</p>
      </div>

      <div className="space-y-3 text-xs">
        <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
          <div className="flex justify-between">
            <span className="text-slate-400">Total Enclosed Area:</span>
            <span className="font-mono font-bold text-sky-400">{totalRoomArea.toFixed(2)} m²</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Detected Rooms:</span>
            <span className="font-mono text-slate-200">{rooms.length}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Active Walls:</span>
            <span className="font-mono text-slate-200">{Object.keys(walls).length}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-400">Furniture Placed:</span>
            <span className="font-mono text-slate-200">{Object.keys(furniture).length}</span>
          </div>
        </div>

        <div className="p-3 rounded-lg bg-sky-950/30 border border-sky-800/30 text-[11px] text-sky-300 space-y-1.5">
          <span className="font-semibold block text-sky-200">Pro Tips:</span>
          <p>• Draw walls to close loops; room surface areas compute automatically.</p>
          <p>• In 3D orbit mode, facing walls drop to plinths (Cutaway) for interior visibility.</p>
          <p>• Press &quot;Walkthrough&quot; for first-person WASD exploration at 1.65m eye level.</p>
        </div>
      </div>
    </aside>
  );
};
