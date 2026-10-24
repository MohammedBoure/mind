/**
 * JSON Persistence, Backup & Cross-Browser Portability Engine
 * Exports and validates full interior design projects with alternatives and settings.
 */

import { AlternativeDesign, ProjectSettings } from '../types/plan.js';

export interface ExportedProjectData {
  version: string;
  timestamp: number;
  appName: string;
  activeAlternativeId: string;
  alternatives: AlternativeDesign[];
  settings: ProjectSettings;
}

export function exportProjectToJSON(
  activeAlternativeId: string,
  alternatives: AlternativeDesign[],
  settings: ProjectSettings
): string {
  const payload: ExportedProjectData = {
    version: '1.0.0',
    timestamp: Date.now(),
    appName: 'MindSpace Interior & Commercial Studio',
    activeAlternativeId,
    alternatives,
    settings,
  };
  return JSON.stringify(payload, null, 2);
}

export function importProjectFromJSON(jsonString: string): {
  success: boolean;
  data?: ExportedProjectData;
  error?: string;
} {
  try {
    const parsed = JSON.parse(jsonString);

    if (!parsed.alternatives || !Array.isArray(parsed.alternatives) || parsed.alternatives.length === 0) {
      return { success: false, error: 'Invalid project file: missing design alternatives array.' };
    }

    // Validate and sanitize each alternative
    const sanitizedAlts: AlternativeDesign[] = parsed.alternatives.map((alt: any, idx: number) => ({
      id: alt.id || `alt_${Date.now()}_${idx}`,
      name: alt.name || `Design Alternative ${idx + 1}`,
      description: alt.description || '',
      vertices: alt.vertices || {},
      walls: alt.walls || {},
      openings: alt.openings || {},
      furniture: alt.furniture || {},
      rooms: Array.isArray(alt.rooms) ? alt.rooms : [],
      wallFinishCostPerM2: typeof alt.wallFinishCostPerM2 === 'number' ? alt.wallFinishCostPerM2 : 2500,
      createdAt: alt.createdAt || Date.now(),
      updatedAt: alt.updatedAt || Date.now(),
    }));

    const sanitizedSettings: ProjectSettings = {
      unit: 'm',
      gridSnap: 0.1,
      angleSnapDeg: 45,
      cutawayMode: parsed.settings?.cutawayMode ?? true,
      cutawayHeight: 0.25,
      defaultWallHeight: 2.8,
      defaultWallThickness: 0.2,
      defaultWallFinishCostPerM2: 2500,
    };

    return {
      success: true,
      data: {
        version: parsed.version || '1.0.0',
        timestamp: parsed.timestamp || Date.now(),
        appName: 'MindSpace Interior & Commercial Studio',
        activeAlternativeId: parsed.activeAlternativeId || sanitizedAlts[0].id,
        alternatives: sanitizedAlts,
        settings: sanitizedSettings,
      },
    };
  } catch (err: any) {
    return { success: false, error: `JSON Parse error: ${err.message}` };
  }
}
