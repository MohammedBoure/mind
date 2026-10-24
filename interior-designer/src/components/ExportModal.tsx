import React, { useRef } from 'react';
import { AlternativeDesign, ProjectSettings } from '../types/plan.js';
import { exportBlueprintToSVG } from '../export/svgExporter.js';
import { exportBoQToCSV } from '../export/csvExporter.js';
import { exportProjectToJSON, importProjectFromJSON } from '../export/jsonExporter.js';
import { X, FileCode, FileSpreadsheet, FileJson, Camera, Upload } from 'lucide-react';

interface ExportModalProps {
  isOpen: boolean;
  activeAlternative: AlternativeDesign;
  alternatives: AlternativeDesign[];
  settings: ProjectSettings;
  onClose: () => void;
  onCaptureSnapshot: () => string;
  onImportProject: (data: any) => void;
}

export const ExportModal: React.FC<ExportModalProps> = ({
  isOpen,
  activeAlternative,
  alternatives,
  settings,
  onClose,
  onCaptureSnapshot,
  onImportProject,
}) => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  if (!isOpen) return null;

  const triggerDownload = (filename: string, content: string, mime: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  // 1. Scaled Vector SVG Blueprint Export (1:10 metric scale)
  const handleExportSVG = () => {
    const svgStr = exportBlueprintToSVG(activeAlternative, 100, '1:10');
    triggerDownload(
      `Blueprint_${activeAlternative.name.replace(/\s+/g, '_')}_1-10.svg`,
      svgStr,
      'image/svg+xml;charset=utf-8'
    );
  };

  // 2. Clean BoQ CSV Export
  const handleExportCSV = () => {
    const csvStr = exportBoQToCSV(activeAlternative);
    triggerDownload(
      `BoQ_${activeAlternative.name.replace(/\s+/g, '_')}.csv`,
      csvStr,
      'text/csv;charset=utf-8'
    );
  };

  // 3. Full Project JSON Backup
  const handleExportJSON = () => {
    const jsonStr = exportProjectToJSON(activeAlternative.id, alternatives, settings);
    triggerDownload(
      `MindSpace_Project_${new Date().toISOString().split('T')[0]}.json`,
      jsonStr,
      'application/json;charset=utf-8'
    );
  };

  // 4. 3D WebGL Canvas PNG Snapshot
  const handleExportPNG = () => {
    const dataUrl = onCaptureSnapshot();
    if (!dataUrl) return;
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = `Snapshot_3D_${activeAlternative.name.replace(/\s+/g, '_')}.png`;
    a.click();
  };

  // 5. JSON Project File Import
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      const result = importProjectFromJSON(content);
      if (result.success && result.data) {
        onImportProject(result.data);
        onClose();
      } else {
        alert(result.error || 'Failed to import project JSON.');
      }
    };
    reader.readAsText(file);
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 select-none animate-in fade-in duration-150">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-bold text-white">Export & Backup Studio Assets</h2>
            <p className="text-xs text-slate-400">Zero-loss portability, blueprints, schedules & snapshots</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Export Cards */}
        <div className="p-5 grid grid-cols-2 gap-3.5">
          {/* SVG Blueprint */}
          <button
            onClick={handleExportSVG}
            className="p-4 rounded-xl bg-slate-950/80 hover:bg-slate-800 border border-slate-800 hover:border-sky-500/50 text-left transition group shadow-sm flex flex-col justify-between"
          >
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center">
                <FileCode className="w-4 h-4" />
              </div>
              <span className="text-xs font-bold text-white group-hover:text-sky-300">
                Vector SVG Blueprint
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              Scaled 1:10 metric blueprint with dimension lines, room tags, and door swing arcs.
            </p>
          </button>

          {/* CSV BoQ */}
          <button
            onClick={handleExportCSV}
            className="p-4 rounded-xl bg-slate-950/80 hover:bg-slate-800 border border-slate-800 hover:border-emerald-500/50 text-left transition group shadow-sm flex flex-col justify-between"
          >
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
                <FileSpreadsheet className="w-4 h-4" />
              </div>
              <span className="text-xs font-bold text-white group-hover:text-emerald-300">
                Itemized BoQ CSV
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              Full pricing breakdown, area schedules, quantities, and category subtotals in integer cents.
            </p>
          </button>

          {/* JSON Backup */}
          <button
            onClick={handleExportJSON}
            className="p-4 rounded-xl bg-slate-950/80 hover:bg-slate-800 border border-slate-800 hover:border-indigo-500/50 text-left transition group shadow-sm flex flex-col justify-between"
          >
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
                <FileJson className="w-4 h-4" />
              </div>
              <span className="text-xs font-bold text-white group-hover:text-indigo-300">
                Project JSON Backup
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              Cross-browser JSON backup holding all design branches, walls, openings, and furniture.
            </p>
          </button>

          {/* 3D PNG Snapshot */}
          <button
            onClick={handleExportPNG}
            className="p-4 rounded-xl bg-slate-950/80 hover:bg-slate-800 border border-slate-800 hover:border-amber-500/50 text-left transition group shadow-sm flex flex-col justify-between"
          >
            <div className="flex items-center space-x-2.5">
              <div className="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center">
                <Camera className="w-4 h-4" />
              </div>
              <span className="text-xs font-bold text-white group-hover:text-amber-300">
                3D Canvas Snapshot
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">
              Direct high-resolution PNG snapshot captured straight from active WebGL 3D canvas.
            </p>
          </button>
        </div>

        {/* Project Import Section */}
        <div className="p-4 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2 text-xs text-slate-400">
            <Upload className="w-4 h-4 text-sky-400" />
            <span>Restore Project from JSON Backup:</span>
          </div>

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".json,application/json"
            className="hidden"
          />

          <button
            onClick={() => fileInputRef.current?.click()}
            className="bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-700 transition"
          >
            Upload JSON File
          </button>
        </div>
      </div>
    </div>
  );
};
