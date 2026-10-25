import React from 'react';
import { AlternativeDesign } from '../types/plan.js';
import { calculateBoQ, formatCurrency } from '../core/boqCalculator.js';
import { exportBoQToCSV } from '../export/csvExporter.js';
import { X, Download, FileSpreadsheet } from 'lucide-react';

interface BoQModalProps {
  isOpen: boolean;
  activeAlternative: AlternativeDesign;
  onClose: () => void;
}

export const BoQModal: React.FC<BoQModalProps> = ({
  isOpen,
  activeAlternative,
  onClose,
}) => {
  if (!isOpen) return null;

  const boq = calculateBoQ(activeAlternative);

  const handleDownloadCSV = () => {
    const csvContent = exportBoQToCSV(activeAlternative);
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `BoQ_${activeAlternative.name.replace(/\s+/g, '_')}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4 select-none animate-in fade-in duration-150">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-4xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center border border-sky-500/30">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">Bill of Quantities (BoQ) & Cost Schedule</h2>
              <p className="text-xs text-slate-400">Variant: {activeAlternative.name}</p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handleDownloadCSV}
              className="bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold px-3 py-1.5 rounded-lg flex items-center space-x-1.5 shadow-sm transition"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export CSV</span>
            </button>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Top KPI Summaries */}
        <div className="p-4 bg-slate-950/60 border-b border-slate-800 grid grid-cols-5 gap-3">
          <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800">
            <span className="text-[11px] text-slate-400 block">Flooring Area</span>
            <span className="text-sm font-mono font-bold text-sky-400">
              {boq.totalFlooringAreaM2.toFixed(2)} m²
            </span>
          </div>
          <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800">
            <span className="text-[11px] text-slate-400 block">Net Wall Finish</span>
            <span className="text-sm font-mono font-bold text-indigo-400">
              {boq.netWallAreaM2.toFixed(2)} m²
            </span>
          </div>
          <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800">
            <span className="text-[11px] text-slate-400 block">Doors & Windows</span>
            <span className="text-sm font-mono font-bold text-slate-200">
              {boq.doorCount} doors / {boq.windowCount} win
            </span>
          </div>
          <div className="p-2.5 rounded-xl bg-slate-900 border border-slate-800">
            <span className="text-[11px] text-slate-400 block">Furniture Units</span>
            <span className="text-sm font-mono font-bold text-slate-200">
              {boq.furnitureCount} pcs
            </span>
          </div>
          <div className="p-2.5 rounded-xl bg-emerald-950/30 border border-emerald-500/30">
            <span className="text-[11px] text-emerald-400 block">Grand Total</span>
            <span className="text-sm font-mono font-bold text-emerald-400">
              {formatCurrency(boq.totalCostCents)}
            </span>
          </div>
        </div>

        {/* Schedule Table */}
        <div className="flex-1 overflow-y-auto p-4">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400 font-semibold">
                <th className="pb-2">Category</th>
                <th className="pb-2">Item Description</th>
                <th className="pb-2">Specification</th>
                <th className="pb-2 text-right">Quantity</th>
                <th className="pb-2 text-right">Unit Price</th>
                <th className="pb-2 text-right">Total Line Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {boq.items.map((item) => (
                <tr key={item.id} className="hover:bg-slate-800/30 transition">
                  <td className="py-2.5">
                    <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300">
                      {item.category}
                    </span>
                  </td>
                  <td className="py-2.5 font-medium text-slate-200">{item.name}</td>
                  <td className="py-2.5 text-slate-400 text-[11px]">{item.specification}</td>
                  <td className="py-2.5 font-mono text-slate-300 text-right">
                    {item.quantity} {item.unit}
                  </td>
                  <td className="py-2.5 font-mono text-slate-300 text-right">
                    {formatCurrency(item.unitCostCents)}
                  </td>
                  <td className="py-2.5 font-mono font-semibold text-emerald-400 text-right">
                    {formatCurrency(item.totalCostCents)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
