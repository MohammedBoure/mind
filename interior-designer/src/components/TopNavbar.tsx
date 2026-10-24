import React from 'react';
import {
  ViewLayout,
  AlternativeDesign,
} from '../types/plan.js';
import {
  Undo2,
  Redo2,
  Columns2,
  Square,
  Box,
  Eye,
  Layers,
  FileSpreadsheet,
  GitCompare,
  Download,
  RotateCcw,
} from 'lucide-react';
import { formatCurrency } from '../core/boqCalculator.js';

interface TopNavbarProps {
  activeAlternative: AlternativeDesign;
  alternatives: AlternativeDesign[];
  viewLayout: ViewLayout;
  isWalkthrough: boolean;
  cutawayMode: boolean;
  canUndo: boolean;
  canRedo: boolean;
  totalBudgetCents: number;
  onSelectAlternative: (id: string) => void;
  onSetViewLayout: (layout: ViewLayout) => void;
  onToggleWalkthrough: () => void;
  onToggleCutaway: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onOpenBoQ: () => void;
  onOpenAlternatives: () => void;
  onOpenExport: () => void;
  onResetProject: () => void;
}

export const TopNavbar: React.FC<TopNavbarProps> = ({
  activeAlternative,
  alternatives,
  viewLayout,
  isWalkthrough,
  cutawayMode,
  canUndo,
  canRedo,
  totalBudgetCents,
  onSelectAlternative,
  onSetViewLayout,
  onToggleWalkthrough,
  onToggleCutaway,
  onUndo,
  onRedo,
  onOpenBoQ,
  onOpenAlternatives,
  onOpenExport,
  onResetProject,
}) => {
  return (
    <header className="h-14 bg-slate-900 border-b border-slate-800 px-4 flex items-center justify-between select-none z-20">
      {/* Brand & Design Variant Selector */}
      <div className="flex items-center space-x-4">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-sky-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-sky-500/20">
            <Box className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white tracking-wide flex items-center gap-1.5">
              <span>MindSpace</span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-400 border border-sky-500/30">
                Studio
              </span>
            </h1>
          </div>
        </div>

        <div className="h-5 w-px bg-slate-800" />

        {/* Alternative Branch Selector */}
        <div className="flex items-center space-x-2">
          <span className="text-xs text-slate-400">Variant:</span>
          <select
            value={activeAlternative.id}
            onChange={(e) => onSelectAlternative(e.target.value)}
            className="bg-slate-800 hover:bg-slate-750 text-xs text-sky-300 font-medium px-2.5 py-1.5 rounded-md border border-slate-700 outline-none focus:border-sky-500 cursor-pointer transition"
          >
            {alternatives.map((alt) => (
              <option key={alt.id} value={alt.id}>
                {alt.name}
              </option>
            ))}
          </select>

          <button
            onClick={onOpenAlternatives}
            title="Side-by-side alternative comparison & branch creator"
            className="p-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition"
          >
            <GitCompare className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Center: Viewport Mode & Walkthrough Controls */}
      <div className="flex items-center space-x-2 bg-slate-950/60 p-1 rounded-lg border border-slate-800">
        <button
          onClick={() => onSetViewLayout('split')}
          className={`px-2.5 py-1 rounded text-xs font-medium flex items-center space-x-1.5 transition ${
            viewLayout === 'split'
              ? 'bg-sky-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          title="Split View: 2D Blueprint & 3D Interactive"
        >
          <Columns2 className="w-3.5 h-3.5" />
          <span>Split</span>
        </button>

        <button
          onClick={() => onSetViewLayout('2d_only')}
          className={`px-2.5 py-1 rounded text-xs font-medium flex items-center space-x-1.5 transition ${
            viewLayout === '2d_only'
              ? 'bg-sky-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          title="2D Plan View Only"
        >
          <Square className="w-3.5 h-3.5" />
          <span>2D Plan</span>
        </button>

        <button
          onClick={() => onSetViewLayout('3d_only')}
          className={`px-2.5 py-1 rounded text-xs font-medium flex items-center space-x-1.5 transition ${
            viewLayout === '3d_only'
              ? 'bg-sky-600 text-white shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          title="3D Viewport Only"
        >
          <Box className="w-3.5 h-3.5" />
          <span>3D View</span>
        </button>

        <div className="h-4 w-px bg-slate-800 mx-1" />

        {/* Walkthrough Mode Toggle */}
        <button
          onClick={onToggleWalkthrough}
          className={`px-2.5 py-1 rounded text-xs font-medium flex items-center space-x-1.5 transition ${
            isWalkthrough
              ? 'bg-emerald-600 text-white shadow-md animate-pulse'
              : 'bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-emerald-500/30'
          }`}
          title="First-Person Walkthrough (WASD & Mouse Look)"
        >
          <Eye className="w-3.5 h-3.5" />
          <span>{isWalkthrough ? 'Walking (1.65m)' : 'Walkthrough'}</span>
        </button>

        {/* Cutaway Presentation Toggle */}
        <button
          onClick={onToggleCutaway}
          disabled={isWalkthrough}
          className={`px-2.5 py-1 rounded text-xs font-medium flex items-center space-x-1.5 transition ${
            isWalkthrough
              ? 'opacity-40 cursor-not-allowed text-slate-500'
              : cutawayMode
              ? 'bg-indigo-600/30 text-indigo-300 border border-indigo-500/50'
              : 'text-slate-400 hover:text-slate-200'
          }`}
          title="Dynamic Presentation Cutaway (Low Plinths on Camera Side)"
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Cutaway: {cutawayMode ? 'ON' : 'OFF'}</span>
        </button>
      </div>

      {/* Right Controls: Undo/Redo, Live BoQ Badge, Export */}
      <div className="flex items-center space-x-3">
        {/* Undo / Redo */}
        <div className="flex items-center space-x-1">
          <button
            onClick={onUndo}
            disabled={!canUndo}
            title="Undo (Ctrl+Z)"
            className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent transition"
          >
            <Undo2 className="w-4 h-4" />
          </button>
          <button
            onClick={onRedo}
            disabled={!canRedo}
            title="Redo (Ctrl+Y)"
            className="p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent transition"
          >
            <Redo2 className="w-4 h-4" />
          </button>
        </div>

        {/* Live BoQ Budget Pill */}
        <button
          onClick={onOpenBoQ}
          className="bg-slate-800 hover:bg-slate-750 text-xs px-3 py-1.5 rounded-lg border border-slate-700 flex items-center space-x-2 transition cursor-pointer shadow-sm"
          title="Open Bill of Quantities & Estimation"
        >
          <FileSpreadsheet className="w-3.5 h-3.5 text-sky-400" />
          <span className="text-slate-400">BoQ:</span>
          <span className="font-mono font-semibold text-emerald-400">
            {formatCurrency(totalBudgetCents)}
          </span>
        </button>

        {/* Export & Reset Buttons */}
        <button
          onClick={onOpenExport}
          className="bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold px-3 py-1.5 rounded-lg flex items-center space-x-1.5 shadow-md shadow-sky-600/20 transition"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Export</span>
        </button>

        <button
          onClick={onResetProject}
          title="Reset to default architectural cafe showcase"
          className="p-1.5 rounded-md text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition"
        >
          <RotateCcw className="w-3.5 h-3.5" />
        </button>
      </div>
    </header>
  );
};
