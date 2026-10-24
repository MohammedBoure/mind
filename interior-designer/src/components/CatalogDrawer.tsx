import React, { useState } from 'react';
import { CATALOG_ITEMS } from '../catalog/items.js';
import { CatalogCategory } from '../types/catalog.js';
import { formatCurrency } from '../core/boqCalculator.js';
import { X, Search } from 'lucide-react';

interface CatalogDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectItem: (catalogId: string) => void;
}

const CATEGORIES: Array<{ id: CatalogCategory | 'all'; label: string }> = [
  { id: 'all', label: 'All Items' },
  { id: 'dining', label: 'Dining' },
  { id: 'seating', label: 'Seating' },
  { id: 'counters', label: 'Counters' },
  { id: 'partitions', label: 'Partitions' },
  { id: 'lighting', label: 'Lighting' },
  { id: 'flooring', label: 'Rugs' },
  { id: 'office', label: 'Office' },
  { id: 'decor', label: 'Decor' },
];

export const CatalogDrawer: React.FC<CatalogDrawerProps> = ({
  isOpen,
  onClose,
  onSelectItem,
}) => {
  const [activeCategory, setActiveCategory] = useState<CatalogCategory | 'all'>('all');
  const [searchQuery, setSearchQuery] = useState('');

  if (!isOpen) return null;

  const filteredItems = CATALOG_ITEMS.filter((item) => {
    const matchesCat = activeCategory === 'all' || item.category === activeCategory;
    const matchesQuery =
      item.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.description.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesCat && matchesQuery;
  });

  return (
    <div className="absolute top-16 left-16 z-20 w-96 max-h-[calc(100vh-6rem)] bg-slate-900/95 backdrop-blur-md border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
      {/* Drawer Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-white">Procedural 3D Catalog</h2>
          <p className="text-xs text-slate-400">18 Parametric commercial & interior elements</p>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Search Input */}
      <div className="px-4 pt-3">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search catalog items..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950 text-xs text-slate-200 pl-8 pr-3 py-2 rounded-lg border border-slate-800 outline-none focus:border-sky-500 transition"
          />
        </div>
      </div>

      {/* Category Pills */}
      <div className="px-4 py-3 flex space-x-1.5 overflow-x-auto scrollbar-none">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setActiveCategory(cat.id)}
            className={`px-2.5 py-1 rounded-full text-[11px] font-medium whitespace-nowrap transition ${
              activeCategory === cat.id
                ? 'bg-sky-600 text-white shadow-sm'
                : 'bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-750'
            }`}
          >
            {cat.label}
          </button>
        ))}
      </div>

      {/* Items Grid */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2.5 max-h-[500px]">
        {filteredItems.map((item) => (
          <div
            key={item.id}
            onClick={() => {
              onSelectItem(item.id);
              onClose();
            }}
            className="group p-3 rounded-xl bg-slate-950/70 hover:bg-slate-800/80 border border-slate-800/90 hover:border-sky-500/50 cursor-pointer transition shadow-sm"
          >
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-xs font-semibold text-slate-200 group-hover:text-sky-300 transition">
                  {item.name}
                </h3>
                <p className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">
                  {item.description}
                </p>
              </div>
              <span className="text-xs font-mono font-semibold text-emerald-400 ml-2">
                {formatCurrency(item.defaultCostCents)}
              </span>
            </div>

            <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
              <span className="font-mono">
                {item.defaultWidth.toFixed(2)}m × {item.defaultDepth.toFixed(2)}m × {item.defaultHeight.toFixed(2)}m
              </span>
              {item.isFloorCovering && (
                <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                  Floor Covering (Non-blocking)
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
