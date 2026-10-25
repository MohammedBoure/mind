/**
 * Clean CSV Exporter for Bill of Quantities (BoQ)
 * Outputs area schedules, openings counts, furniture costs, and project financial totals.
 */

import { AlternativeDesign } from '../types/plan.js';
import { calculateBoQ } from '../core/boqCalculator.js';

export function exportBoQToCSV(design: AlternativeDesign): string {
  const boq = calculateBoQ(design);

  const rows: string[][] = [
    ['MINDSPACE ARCHITECTURAL DESIGN STUDIO — BILL OF QUANTITIES (BoQ)'],
    [`Project Design Variant:`, `"${design.name}"`],
    [`Export Date:`, new Date().toISOString().split('T')[0]],
    [`Total Enclosed Flooring Area:`, `${boq.totalFlooringAreaM2.toFixed(3)} m²`],
    [`Net Finished Wall Surface:`, `${boq.netWallAreaM2.toFixed(2)} m²`],
    [`Total Doors / Windows:`, `${boq.doorCount} doors / ${boq.windowCount} windows`],
    [`Total Furniture Units:`, `${boq.furnitureCount} pcs`],
    [`Grand Total Estimated Cost:`, `$${(boq.totalCostCents / 100).toFixed(2)}`],
    [],
    ['Category', 'Item Description', 'Specification', 'Quantity', 'Unit', 'Unit Price ($)', 'Total Line Cost ($)'],
  ];

  for (const item of boq.items) {
    rows.push([
      item.category,
      `"${item.name.replace(/"/g, '""')}"`,
      `"${item.specification.replace(/"/g, '""')}"`,
      item.quantity.toString(),
      item.unit,
      (item.unitCostCents / 100).toFixed(2),
      (item.totalCostCents / 100).toFixed(2),
    ]);
  }

  // Category Summaries
  rows.push([]);
  rows.push(['--- CATEGORY FINANCIAL TOTALS ---']);
  for (const [cat, cents] of Object.entries(boq.categoryTotalsCents)) {
    rows.push([cat, '', '', '', '', '', (cents / 100).toFixed(2)]);
  }
  rows.push(['GRAND TOTAL', '', '', '', '', '', (boq.totalCostCents / 100).toFixed(2)]);

  return rows.map((r) => r.join(',')).join('\n');
}
