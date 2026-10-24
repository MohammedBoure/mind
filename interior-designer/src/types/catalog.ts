/**
 * Parametric catalog item definitions for interior, hospitality, and commercial spaces.
 */

export type CatalogCategory =
  | 'dining'
  | 'seating'
  | 'counters'
  | 'partitions'
  | 'lighting'
  | 'flooring'
  | 'office'
  | 'decor';

export interface CatalogItemDef {
  id: string;
  name: string;
  category: CatalogCategory;
  defaultWidth: number; // in meters
  defaultDepth: number; // in meters
  defaultHeight: number; // in meters
  isFloorCovering: boolean; // items <= 0.06m height (like rugs) allow furniture placed on top
  defaultFinish: string;
  defaultCostCents: number; // in integer cents
  description: string;
  proceduralType:
    | 'table_dining_rect'
    | 'table_bistro_round'
    | 'chair_bistro'
    | 'bar_stool'
    | 'counter_straight'
    | 'counter_corner'
    | 'lounge_booth'
    | 'acoustic_divider'
    | 'pendant_light'
    | 'rug_rectangular'
    | 'rug_circular'
    | 'planter_foliage'
    | 'office_desk'
    | 'task_chair'
    | 'credenza_bookshelf'
    | 'display_showcase'
    | 'coffee_station'
    | 'armchair_lounge';
}
