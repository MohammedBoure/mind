import React from 'react';
import { EditorMode } from '../types/plan.js';
import {
  MousePointer,
  SquareDashedBottomCode,
  DoorOpen,
  AppWindow,
  Armchair,
  Trash2,
} from 'lucide-react';

interface Toolbar2DProps {
  editorMode: EditorMode;
  isCatalogOpen: boolean;
  hasSelection: boolean;
  onSetEditorMode: (mode: EditorMode) => void;
  onToggleCatalog: () => void;
  onDeleteSelected: () => void;
}

export const Toolbar2D: React.FC<Toolbar2DProps> = ({
  editorMode,
  isCatalogOpen,
  hasSelection,
  onSetEditorMode,
  onToggleCatalog,
  onDeleteSelected,
}) => {
  return (
    <div className="absolute top-4 left-4 z-10 flex flex-col bg-slate-900/90 backdrop-blur border border-slate-800 rounded-xl p-1.5 shadow-xl space-y-1 select-none">
      <button
        onClick={() => onSetEditorMode('select')}
        className={`p-2.5 rounded-lg flex items-center justify-center transition ${
          editorMode === 'select'
            ? 'bg-sky-600 text-white shadow-md'
            : 'text-slate-400 hover:text-white hover:bg-slate-800'
        }`}
        title="Select & Move (V)"
      >
        <MousePointer className="w-4 h-4" />
      </button>

      <button
        onClick={() => onSetEditorMode('draw_wall')}
        className={`p-2.5 rounded-lg flex items-center justify-center transition ${
          editorMode === 'draw_wall'
            ? 'bg-sky-600 text-white shadow-md'
            : 'text-slate-400 hover:text-white hover:bg-slate-800'
        }`}
        title="Draw Walls Point-to-Point (W)"
      >
        <SquareDashedBottomCode className="w-4 h-4" />
      </button>

      <button
        onClick={() => onSetEditorMode('place_door')}
        className={`p-2.5 rounded-lg flex items-center justify-center transition ${
          editorMode === 'place_door'
            ? 'bg-sky-600 text-white shadow-md'
            : 'text-slate-400 hover:text-white hover:bg-slate-800'
        }`}
        title="Insert Door onto Wall (D)"
      >
        <DoorOpen className="w-4 h-4" />
      </button>

      <button
        onClick={() => onSetEditorMode('place_window')}
        className={`p-2.5 rounded-lg flex items-center justify-center transition ${
          editorMode === 'place_window'
            ? 'bg-sky-600 text-white shadow-md'
            : 'text-slate-400 hover:text-white hover:bg-slate-800'
        }`}
        title="Insert Window onto Wall"
      >
        <AppWindow className="w-4 h-4" />
      </button>

      <div className="h-px w-full bg-slate-800 my-1" />

      <button
        onClick={onToggleCatalog}
        className={`p-2.5 rounded-lg flex items-center justify-center transition ${
          isCatalogOpen
            ? 'bg-indigo-600 text-white shadow-md'
            : 'text-slate-400 hover:text-white hover:bg-slate-800'
        }`}
        title="Open Parametric Furniture Catalog"
      >
        <Armchair className="w-4 h-4" />
      </button>

      {hasSelection && (
        <button
          onClick={onDeleteSelected}
          className="p-2.5 rounded-lg flex items-center justify-center text-rose-400 hover:text-white hover:bg-rose-600/40 transition"
          title="Delete Selected (Del)"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      )}
    </div>
  );
};
