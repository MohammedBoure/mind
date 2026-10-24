import React, { useState } from 'react';
import { AlternativeDesign } from '../types/plan.js';
import { compareAlternatives } from '../core/alternatives.js';
import { X, GitBranch, Plus, Check } from 'lucide-react';

interface AlternativesModalProps {
  isOpen: boolean;
  activeAlternative: AlternativeDesign;
  alternatives: AlternativeDesign[];
  onSelectAlternative: (id: string) => void;
  onBranchAlternative: (name: string, description: string) => void;
  onClose: () => void;
}

export const AlternativesModal: React.FC<AlternativesModalProps> = ({
  isOpen,
  activeAlternative,
  alternatives,
  onSelectAlternative,
  onBranchAlternative,
  onClose,
}) => {
  const [baseId, setBaseId] = useState(activeAlternative.id);
  const [targetId, setTargetId] = useState(
    alternatives.find((a) => a.id !== activeAlternative.id)?.id || activeAlternative.id
  );

  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const [newBranchName, setNewBranchName] = useState('');
  const [newBranchDesc, setNewBranchDesc] = useState('');

  if (!isOpen) return null;

  const baseAlt = alternatives.find((a) => a.id === baseId) || activeAlternative;
  const targetAlt = alternatives.find((a) => a.id === targetId) || alternatives[0];

  const delta = compareAlternatives(baseAlt, targetAlt);

  const handleCreateBranch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBranchName.trim()) return;
    onBranchAlternative(newBranchName.trim(), newBranchDesc.trim());
    setIsCreatingNew(false);
    setNewBranchName('');
    setNewBranchDesc('');
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 select-none animate-in fade-in duration-150">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center border border-indigo-500/30">
              <GitBranch className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">Design Alternatives & Delta Comparison</h2>
              <p className="text-xs text-slate-400">Evaluate parallel layouts, finish specs, and budgets</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Alternative Selectors */}
        <div className="p-4 bg-slate-950/60 border-b border-slate-800 flex items-center justify-between gap-4">
          <div className="flex items-center space-x-3 flex-1">
            <div className="flex-1">
              <label className="text-[11px] text-slate-400 block mb-1">Base Alternative (A):</label>
              <select
                value={baseId}
                onChange={(e) => setBaseId(e.target.value)}
                className="w-full bg-slate-900 text-xs text-slate-200 px-3 py-1.5 rounded-lg border border-slate-700 outline-none cursor-pointer"
              >
                {alternatives.map((alt) => (
                  <option key={alt.id} value={alt.id}>
                    {alt.name} {alt.id === activeAlternative.id ? '(Active)' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex-1">
              <label className="text-[11px] text-slate-400 block mb-1">Target Comparison (B):</label>
              <select
                value={targetId}
                onChange={(e) => setTargetId(e.target.value)}
                className="w-full bg-slate-900 text-xs text-slate-200 px-3 py-1.5 rounded-lg border border-slate-700 outline-none cursor-pointer"
              >
                {alternatives.map((alt) => (
                  <option key={alt.id} value={alt.id}>
                    {alt.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="pt-4">
            <button
              onClick={() => setIsCreatingNew(!isCreatingNew)}
              className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold px-3 py-2 rounded-lg flex items-center space-x-1.5 shadow-sm transition"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Branch Variant</span>
            </button>
          </div>
        </div>

        {/* Create Branch Mini-Form */}
        {isCreatingNew && (
          <form onSubmit={handleCreateBranch} className="p-4 bg-indigo-950/20 border-b border-indigo-500/30 space-y-3">
            <h3 className="text-xs font-bold text-indigo-300">Clone Current Design into New Alternative</h3>
            <div className="grid grid-cols-2 gap-3">
              <input
                type="text"
                placeholder="Alternative Name (e.g. Alternative C - Minimalist)"
                value={newBranchName}
                onChange={(e) => setNewBranchName(e.target.value)}
                className="bg-slate-950 text-xs text-slate-200 px-3 py-1.5 rounded-lg border border-slate-700 outline-none focus:border-indigo-500"
              />
              <input
                type="text"
                placeholder="Description / Budget Notes"
                value={newBranchDesc}
                onChange={(e) => setNewBranchDesc(e.target.value)}
                className="bg-slate-950 text-xs text-slate-200 px-3 py-1.5 rounded-lg border border-slate-700 outline-none focus:border-indigo-500"
              />
            </div>
            <div className="flex justify-end space-x-2">
              <button
                type="button"
                onClick={() => setIsCreatingNew(false)}
                className="px-3 py-1 rounded text-xs text-slate-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold px-3 py-1 rounded shadow-sm"
              >
                Create Branch
              </button>
            </div>
          </form>
        )}

        {/* Delta Comparison Table */}
        <div className="flex-1 overflow-y-auto p-4">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-semibold">
                <th className="pb-2">Metric / Schedule Item</th>
                <th className="pb-2">Base: {baseAlt.name}</th>
                <th className="pb-2">Target: {targetAlt.name}</th>
                <th className="pb-2 text-right">Variance Delta</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {delta.comparisonRows.map((row, idx) => {
                const isPositive = row.deltaValue.startsWith('+');
                const isNegative = row.deltaValue.startsWith('-');
                return (
                  <tr key={idx} className="hover:bg-slate-800/30 transition">
                    <td className="py-2.5 font-medium text-slate-200">{row.item}</td>
                    <td className="py-2.5 font-mono text-slate-300">{row.baseValue}</td>
                    <td className="py-2.5 font-mono text-slate-300">{row.targetValue}</td>
                    <td className="py-2.5 font-mono font-semibold text-right">
                      <span
                        className={
                          row.isCost
                            ? isPositive
                              ? 'text-amber-400'
                              : isNegative
                              ? 'text-emerald-400'
                              : 'text-slate-300'
                            : 'text-sky-400'
                        }
                      >
                        {row.deltaValue}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Footer Actions */}
        <div className="p-4 bg-slate-950/60 border-t border-slate-800 flex justify-between items-center">
          <span className="text-xs text-slate-400">
            Active Variant: <strong className="text-sky-400">{activeAlternative.name}</strong>
          </span>
          {targetAlt.id !== activeAlternative.id && (
            <button
              onClick={() => {
                onSelectAlternative(targetAlt.id);
                onClose();
              }}
              className="bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold px-4 py-2 rounded-lg flex items-center space-x-1.5 shadow-sm transition"
            >
              <Check className="w-3.5 h-3.5" />
              <span>Switch to {targetAlt.name}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
