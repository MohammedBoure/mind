/**
 * Alternative Design Branching & Delta Comparison Engine
 * Allows branching project into parallel variants (Alternative A vs Alternative B)
 * to test layouts, finishes, and budgets with side-by-side delta schedules.
 */

import { AlternativeDesign } from '../types/plan.js';
import { AlternativeDelta } from '../types/boq.js';
import { calculateBoQ, formatCurrency } from './boqCalculator.js';

export function cloneAlternative(
  base: AlternativeDesign,
  newName: string,
  newDesc = ''
): AlternativeDesign {
  return {
    id: `alt_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`,
    name: newName,
    description: newDesc,
    vertices: JSON.parse(JSON.stringify(base.vertices)),
    walls: JSON.parse(JSON.stringify(base.walls)),
    openings: JSON.parse(JSON.stringify(base.openings)),
    furniture: JSON.parse(JSON.stringify(base.furniture)),
    rooms: JSON.parse(JSON.stringify(base.rooms)),
    wallFinishCostPerM2: base.wallFinishCostPerM2,
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
}

export function compareAlternatives(
  base: AlternativeDesign,
  target: AlternativeDesign
): AlternativeDelta {
  const baseBoQ = calculateBoQ(base);
  const targetBoQ = calculateBoQ(target);

  const totalCostDeltaCents = targetBoQ.totalCostCents - baseBoQ.totalCostCents;
  const flooringAreaDeltaM2 =
    Math.round((targetBoQ.totalFlooringAreaM2 - baseBoQ.totalFlooringAreaM2) * 1000) / 1000;
  const furnitureCostDeltaCents =
    targetBoQ.categoryTotalsCents.Furniture - baseBoQ.categoryTotalsCents.Furniture;

  const furnitureDelta = targetBoQ.furnitureCount - baseBoQ.furnitureCount;
  const doorsDelta = targetBoQ.doorCount - baseBoQ.doorCount;
  const windowsDelta = targetBoQ.windowCount - baseBoQ.windowCount;

  const comparisonRows: AlternativeDelta['comparisonRows'] = [
    {
      category: 'Financial',
      item: 'Total Estimated Budget',
      baseValue: formatCurrency(baseBoQ.totalCostCents),
      targetValue: formatCurrency(targetBoQ.totalCostCents),
      deltaValue: `${totalCostDeltaCents >= 0 ? '+' : ''}${formatCurrency(totalCostDeltaCents)}`,
      isCost: true,
    },
    {
      category: 'Flooring',
      item: 'Total Enclosed Area',
      baseValue: `${baseBoQ.totalFlooringAreaM2.toFixed(2)} m²`,
      targetValue: `${targetBoQ.totalFlooringAreaM2.toFixed(2)} m²`,
      deltaValue: `${flooringAreaDeltaM2 >= 0 ? '+' : ''}${flooringAreaDeltaM2.toFixed(2)} m²`,
    },
    {
      category: 'Flooring',
      item: 'Flooring Finishes Cost',
      baseValue: formatCurrency(baseBoQ.categoryTotalsCents.Flooring),
      targetValue: formatCurrency(targetBoQ.categoryTotalsCents.Flooring),
      deltaValue: formatCurrency(targetBoQ.categoryTotalsCents.Flooring - baseBoQ.categoryTotalsCents.Flooring),
      isCost: true,
    },
    {
      category: 'Walls',
      item: 'Net Finished Wall Surface',
      baseValue: `${baseBoQ.netWallAreaM2.toFixed(2)} m²`,
      targetValue: `${targetBoQ.netWallAreaM2.toFixed(2)} m²`,
      deltaValue: `${(targetBoQ.netWallAreaM2 - baseBoQ.netWallAreaM2).toFixed(2)} m²`,
    },
    {
      category: 'Walls',
      item: 'Wall Paint/Finish Cost',
      baseValue: formatCurrency(baseBoQ.categoryTotalsCents.Walls),
      targetValue: formatCurrency(targetBoQ.categoryTotalsCents.Walls),
      deltaValue: formatCurrency(targetBoQ.categoryTotalsCents.Walls - baseBoQ.categoryTotalsCents.Walls),
      isCost: true,
    },
    {
      category: 'Openings',
      item: 'Doors & Windows Total',
      baseValue: `${baseBoQ.doorCount} doors, ${baseBoQ.windowCount} windows`,
      targetValue: `${targetBoQ.doorCount} doors, ${targetBoQ.windowCount} windows`,
      deltaValue: `${doorsDelta >= 0 ? '+' : ''}${doorsDelta} doors / ${windowsDelta >= 0 ? '+' : ''}${windowsDelta} win`,
    },
    {
      category: 'Furniture',
      item: 'Furniture Count & Schedule',
      baseValue: `${baseBoQ.furnitureCount} pcs (${formatCurrency(baseBoQ.categoryTotalsCents.Furniture)})`,
      targetValue: `${targetBoQ.furnitureCount} pcs (${formatCurrency(targetBoQ.categoryTotalsCents.Furniture)})`,
      deltaValue: `${furnitureDelta >= 0 ? '+' : ''}${furnitureDelta} pcs (${furnitureCostDeltaCents >= 0 ? '+' : ''}${formatCurrency(furnitureCostDeltaCents)})`,
      isCost: true,
    },
  ];

  return {
    baseAlternativeId: base.id,
    baseName: base.name,
    targetAlternativeId: target.id,
    targetName: target.name,
    totalCostDeltaCents,
    flooringAreaDeltaM2,
    furnitureCostDeltaCents,
    itemCountDeltas: {
      furnitureDelta,
      doorsDelta,
      windowsDelta,
    },
    comparisonRows,
  };
}
