/**
 * Bill of Quantities (BoQ) & Cost Estimation Engine
 * Calculates real-time floor areas, net wall finish areas, openings, and furniture schedules.
 * All monetary calculations use integer cents to eliminate floating-point drift.
 */

import { AlternativeDesign } from '../types/plan.js';
import { BoQItem, BoQSummary, BoQCategory } from '../types/boq.js';
import { distance } from './geometry.js';

export function formatCurrency(cents: number): string {
  const isNegative = cents < 0;
  const absCents = Math.abs(cents);
  const dollars = Math.floor(absCents / 100);
  const remainder = absCents % 100;
  const formattedDollars = dollars.toLocaleString('en-US');
  const formattedCents = remainder.toString().padStart(2, '0');
  return `${isNegative ? '-' : ''}$${formattedDollars}.${formattedCents}`;
}

export function calculateBoQ(design: AlternativeDesign): BoQSummary {
  const items: BoQItem[] = [];
  const categoryTotals: Record<BoQCategory, number> = {
    Flooring: 0,
    Walls: 0,
    Openings: 0,
    Furniture: 0,
    Fixtures: 0,
  };

  // 1. Flooring
  let totalFlooringAreaM2 = 0;
  for (const room of design.rooms) {
    const area = room.area;
    totalFlooringAreaM2 += area;
    const itemCost = Math.round(area * room.floorCostCentsPerM2);

    categoryTotals.Flooring += itemCost;
    items.push({
      id: `boq_floor_${room.id}`,
      category: 'Flooring',
      name: `Flooring Finish: ${room.name}`,
      specification: `${room.floorFinish.replace(/_/g, ' ').toUpperCase()} (${area.toFixed(2)} m²)`,
      quantity: Math.round(area * 1000) / 1000,
      unit: 'm²',
      unitCostCents: room.floorCostCentsPerM2,
      totalCostCents: itemCost,
    });
  }

  // 2. Walls (Gross and Net Area Calculation)
  let totalGrossWallAreaM2 = 0;
  for (const wall of Object.values(design.walls)) {
    const p1 = design.vertices[wall.startId];
    const p2 = design.vertices[wall.endId];
    if (!p1 || !p2) continue;
    const len = distance(p1, p2);
    // Two faces per wall
    totalGrossWallAreaM2 += 2 * len * wall.height;
  }

  // Openings deduction
  let openingsDeductionAreaM2 = 0;
  let doorCount = 0;
  let windowCount = 0;

  for (const op of Object.values(design.openings)) {
    // Both sides of the wall opening cut area
    const openingArea2Faces = 2 * op.width * op.height;
    openingsDeductionAreaM2 += openingArea2Faces;

    if (op.type === 'door') doorCount++;
    else windowCount++;

    const isDoor = op.type === 'door';
    const unitPrice = op.costCents > 0 ? op.costCents : (isDoor ? 48000 : 36000); // $480 or $360
    categoryTotals.Openings += unitPrice;

    items.push({
      id: `boq_op_${op.id}`,
      category: 'Openings',
      name: isDoor ? `Door (${op.width.toFixed(2)}m × ${op.height.toFixed(2)}m)` : `Window (${op.width.toFixed(2)}m × ${op.height.toFixed(2)}m)`,
      specification: `${op.finish.replace(/_/g, ' ')} / Sill: ${op.sillElevation.toFixed(2)}m`,
      quantity: 1,
      unit: 'pcs',
      unitCostCents: unitPrice,
      totalCostCents: unitPrice,
    });
  }

  const netWallAreaM2 = Math.max(0, totalGrossWallAreaM2 - openingsDeductionAreaM2);
  const wallUnitCost = design.wallFinishCostPerM2 > 0 ? design.wallFinishCostPerM2 : 2500; // $25.00/m² default
  const wallCostTotal = Math.round(netWallAreaM2 * wallUnitCost);
  categoryTotals.Walls += wallCostTotal;

  if (netWallAreaM2 > 0) {
    items.push({
      id: 'boq_walls_paint',
      category: 'Walls',
      name: 'Architectural Wall Paint & Primer',
      specification: `Net 2-face wall surface finish (${netWallAreaM2.toFixed(2)} m²)`,
      quantity: Math.round(netWallAreaM2 * 100) / 100,
      unit: 'm²',
      unitCostCents: wallUnitCost,
      totalCostCents: wallCostTotal,
    });
  }

  // 3. Furniture & Fixtures (Grouped by catalog ID)
  const furnitureGrouped = new Map<string, { item: typeof design.furniture[string]; count: number }>();
  let totalFurnitureCount = 0;

  for (const f of Object.values(design.furniture)) {
    totalFurnitureCount++;
    const key = `${f.catalogId}:${f.finish}`;
    const existing = furnitureGrouped.get(key);
    if (existing) {
      existing.count++;
    } else {
      furnitureGrouped.set(key, { item: f, count: 1 });
    }
  }

  for (const group of furnitureGrouped.values()) {
    const f = group.item;
    const count = group.count;
    const unitPrice = f.costCents;
    const lineTotal = count * unitPrice;
    const cat: BoQCategory = f.catalogId.includes('light') ? 'Fixtures' : 'Furniture';

    categoryTotals[cat] += lineTotal;
    items.push({
      id: `boq_furn_${f.catalogId}_${f.finish}`,
      category: cat,
      name: f.name,
      specification: `${f.width.toFixed(2)}m × ${f.depth.toFixed(2)}m × ${f.height.toFixed(2)}m | ${f.finish}`,
      quantity: count,
      unit: 'pcs',
      unitCostCents: unitPrice,
      totalCostCents: lineTotal,
    });
  }

  const totalCostCents =
    categoryTotals.Flooring +
    categoryTotals.Walls +
    categoryTotals.Openings +
    categoryTotals.Furniture +
    categoryTotals.Fixtures;

  return {
    totalFlooringAreaM2: Math.round(totalFlooringAreaM2 * 1000) / 1000,
    totalGrossWallAreaM2: Math.round(totalGrossWallAreaM2 * 100) / 100,
    openingsDeductionAreaM2: Math.round(openingsDeductionAreaM2 * 100) / 100,
    netWallAreaM2: Math.round(netWallAreaM2 * 100) / 100,
    doorCount,
    windowCount,
    furnitureCount: totalFurnitureCount,
    categoryTotalsCents: categoryTotals,
    totalCostCents,
    items,
  };
}
