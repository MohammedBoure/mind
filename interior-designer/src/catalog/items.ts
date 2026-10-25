/**
 * Procedural Interior & Commercial Catalog Definition
 * Provides 18 modern parametric commercial & interior architectural items.
 * All pricing stored in integer cents.
 */

import { CatalogItemDef } from '../types/catalog.js';

export const CATALOG_ITEMS: CatalogItemDef[] = [
  {
    id: 'furn_dining_rect',
    name: 'Modern Dining Table (Rectangular)',
    category: 'dining',
    defaultWidth: 1.6,
    defaultDepth: 0.9,
    defaultHeight: 0.75,
    isFloorCovering: false,
    defaultFinish: 'wood_oak',
    defaultCostCents: 42000, // $420.00
    description: 'Solid oak dining table with chamfered edge and powder-coated steel legs.',
    proceduralType: 'table_dining_rect',
  },
  {
    id: 'furn_table_bistro_round',
    name: 'Round Bistro Table',
    category: 'dining',
    defaultWidth: 0.8,
    defaultDepth: 0.8,
    defaultHeight: 0.75,
    isFloorCovering: false,
    defaultFinish: 'marble_carrara',
    defaultCostCents: 24000, // $240.00
    description: 'Compact round cafe table with honed marble top and central cast iron base.',
    proceduralType: 'table_bistro_round',
  },
  {
    id: 'furn_chair_bistro',
    name: 'Bistro Dining Chair',
    category: 'seating',
    defaultWidth: 0.48,
    defaultDepth: 0.5,
    defaultHeight: 0.82,
    isFloorCovering: false,
    defaultFinish: 'wood_walnut',
    defaultCostCents: 12500, // $125.00
    description: 'Bentwood dining chair with ergonomic curved backrest and upholstered seat.',
    proceduralType: 'chair_bistro',
  },
  {
    id: 'furn_bar_stool',
    name: 'Modern Bar Stool',
    category: 'seating',
    defaultWidth: 0.42,
    defaultDepth: 0.42,
    defaultHeight: 0.95,
    isFloorCovering: false,
    defaultFinish: 'metal_black',
    defaultCostCents: 14500, // $145.00
    description: 'Counter-height bar stool with tubular metal frame and saddle seat.',
    proceduralType: 'bar_stool',
  },
  {
    id: 'furn_counter_straight',
    name: 'Commercial Service Counter (Straight)',
    category: 'counters',
    defaultWidth: 2.2,
    defaultDepth: 0.75,
    defaultHeight: 0.95,
    isFloorCovering: false,
    defaultFinish: 'terrazzo',
    defaultCostCents: 115000, // $1,150.00
    description: 'Heavy-duty commercial barista/pos service counter with recessed kickplate.',
    proceduralType: 'counter_straight',
  },
  {
    id: 'furn_counter_corner',
    name: 'Commercial Service Counter (Corner L-Shape)',
    category: 'counters',
    defaultWidth: 1.8,
    defaultDepth: 1.8,
    defaultHeight: 0.95,
    isFloorCovering: false,
    defaultFinish: 'terrazzo',
    defaultCostCents: 165000, // $1,650.00
    description: 'L-shaped commercial counter with stone worktop and storage casework.',
    proceduralType: 'counter_corner',
  },
  {
    id: 'furn_lounge_booth',
    name: 'Fluted Restaurant Lounge Booth',
    category: 'seating',
    defaultWidth: 1.8,
    defaultDepth: 0.75,
    defaultHeight: 1.05,
    isFloorCovering: false,
    defaultFinish: 'fabric_terracotta',
    defaultCostCents: 85000, // $850.00
    description: 'High-back banquette dining booth with vertical fluted upholstery.',
    proceduralType: 'lounge_booth',
  },
  {
    id: 'furn_acoustic_divider',
    name: 'Acoustic Partition Divider',
    category: 'partitions',
    defaultWidth: 1.2,
    defaultDepth: 0.25,
    defaultHeight: 1.6,
    isFloorCovering: false,
    defaultFinish: 'fabric_gray',
    defaultCostCents: 31000, // $310.00
    description: 'Freestanding sound-absorbing felt acoustic screen with wooden footings.',
    proceduralType: 'acoustic_divider',
  },
  {
    id: 'furn_pendant_light',
    name: 'Architectural Dome Pendant Light',
    category: 'lighting',
    defaultWidth: 0.45,
    defaultDepth: 0.45,
    defaultHeight: 0.35,
    isFloorCovering: false,
    defaultFinish: 'metal_brass',
    defaultCostCents: 18000, // $180.00
    description: 'Spun brass pendant light with warm internal LED luminaire.',
    proceduralType: 'pendant_light',
  },
  {
    id: 'furn_rug_rectangular',
    name: 'Modern Wool Area Rug (Rectangular)',
    category: 'flooring',
    defaultWidth: 2.4,
    defaultDepth: 1.6,
    defaultHeight: 0.015, // <= 0.06m: non-blocking floor covering
    isFloorCovering: true,
    defaultFinish: 'fabric_beige',
    defaultCostCents: 26000, // $260.00
    description: 'Geometric low-pile wool rug. Non-blocking footprint allows tables/chairs over top.',
    proceduralType: 'rug_rectangular',
  },
  {
    id: 'furn_rug_circular',
    name: 'Round Jute Area Rug',
    category: 'flooring',
    defaultWidth: 2.0,
    defaultDepth: 2.0,
    defaultHeight: 0.015, // <= 0.06m: non-blocking floor covering
    isFloorCovering: true,
    defaultFinish: 'fabric_jute',
    defaultCostCents: 21000, // $210.00
    description: 'Natural woven jute circular rug. Permissive placement beneath furniture.',
    proceduralType: 'rug_circular',
  },
  {
    id: 'furn_planter_foliage',
    name: 'Ceramic Planter & Indoor Foliage',
    category: 'decor',
    defaultWidth: 0.5,
    defaultDepth: 0.5,
    defaultHeight: 1.4,
    isFloorCovering: false,
    defaultFinish: 'ceramic_white',
    defaultCostCents: 19500, // $195.00
    description: 'Cylindrical architectural ceramic pot with lush procedural indoor plant.',
    proceduralType: 'planter_foliage',
  },
  {
    id: 'furn_office_desk',
    name: 'Minimalist Executive Desk',
    category: 'office',
    defaultWidth: 1.6,
    defaultDepth: 0.8,
    defaultHeight: 0.74,
    isFloorCovering: false,
    defaultFinish: 'wood_walnut',
    defaultCostCents: 58000, // $580.00
    description: 'Executive workstation with modesty panel, wire tray, and metal trestle legs.',
    proceduralType: 'office_desk',
  },
  {
    id: 'furn_task_chair',
    name: 'Ergonomic Task Chair',
    category: 'office',
    defaultWidth: 0.65,
    defaultDepth: 0.65,
    defaultHeight: 0.98,
    isFloorCovering: false,
    defaultFinish: 'fabric_black',
    defaultCostCents: 34000, // $340.00
    description: 'High-performance task chair with 5-star castor base and lumbar curve.',
    proceduralType: 'task_chair',
  },
  {
    id: 'furn_credenza_bookshelf',
    name: 'Low Credenza Bookshelf',
    category: 'office',
    defaultWidth: 1.8,
    defaultDepth: 0.45,
    defaultHeight: 0.85,
    isFloorCovering: false,
    defaultFinish: 'wood_oak',
    defaultCostCents: 62000, // $620.00
    description: 'Multi-compartment storage console for books, hospitality wares, and decor.',
    proceduralType: 'credenza_bookshelf',
  },
  {
    id: 'furn_display_showcase',
    name: 'Glass Commercial Showcase',
    category: 'counters',
    defaultWidth: 1.0,
    defaultDepth: 0.5,
    defaultHeight: 1.7,
    isFloorCovering: false,
    defaultFinish: 'aluminum_black',
    defaultCostCents: 89000, // $890.00
    description: 'Illuminated retail glass display showcase with bottom storage compartment.',
    proceduralType: 'display_showcase',
  },
  {
    id: 'furn_coffee_station',
    name: 'Commercial Espresso Station',
    category: 'counters',
    defaultWidth: 0.9,
    defaultDepth: 0.6,
    defaultHeight: 0.95,
    isFloorCovering: false,
    defaultFinish: 'metal_stainless',
    defaultCostCents: 78000, // $780.00
    description: 'Dedicated stainless steel cafe station for grinding and espresso brewing.',
    proceduralType: 'coffee_station',
  },
  {
    id: 'furn_armchair_lounge',
    name: 'Upholstered Lounge Armchair',
    category: 'seating',
    defaultWidth: 0.85,
    defaultDepth: 0.85,
    defaultHeight: 0.78,
    isFloorCovering: false,
    defaultFinish: 'fabric_boucle',
    defaultCostCents: 48000, // $480.00
    description: 'Cozy accent lounge armchair with thick cushioned seat and angled timber legs.',
    proceduralType: 'armchair_lounge',
  },
];

export const CATALOG_MAP = new Map<string, CatalogItemDef>(
  CATALOG_ITEMS.map((item) => [item.id, item])
);
