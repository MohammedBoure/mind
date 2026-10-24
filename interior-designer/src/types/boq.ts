/**
 * Bill of Quantities (BoQ) & Cost Schedule Types
 * All financial amounts are stored as integer cents to avoid floating-point rounding errors.
 */

export type BoQCategory = 'Flooring' | 'Walls' | 'Openings' | 'Furniture' | 'Fixtures';

export interface BoQItem {
  id: string;
  category: BoQCategory;
  name: string;
  specification: string;
  quantity: number; // m², units, or linear meters
  unit: 'm²' | 'pcs' | 'm';
  unitCostCents: number; // e.g. 4500 cents = $45.00
  totalCostCents: number; // quantity * unitCostCents (rounded integer)
}

export interface BoQSummary {
  totalFlooringAreaM2: number;
  totalGrossWallAreaM2: number;
  openingsDeductionAreaM2: number;
  netWallAreaM2: number;
  doorCount: number;
  windowCount: number;
  furnitureCount: number;
  categoryTotalsCents: Record<BoQCategory, number>;
  totalCostCents: number;
  items: BoQItem[];
}

export interface AlternativeDelta {
  baseAlternativeId: string;
  baseName: string;
  targetAlternativeId: string;
  targetName: string;
  totalCostDeltaCents: number;
  flooringAreaDeltaM2: number;
  furnitureCostDeltaCents: number;
  itemCountDeltas: {
    furnitureDelta: number;
    doorsDelta: number;
    windowsDelta: number;
  };
  comparisonRows: Array<{
    category: string;
    item: string;
    baseValue: string;
    targetValue: string;
    deltaValue: string;
    isCost?: boolean;
  }>;
}
