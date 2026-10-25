/**
 * Procedural Three.js Architectural Materials
 * Uses in-memory procedural canvas textures without external CDN downloads.
 */

import * as THREE from 'three';
import {
  generateWoodTexture,
  generateTerrazzoTexture,
  generateConcreteTexture,
  generateTileTexture,
  generateFabricTexture,
} from '../catalog/textures.js';

// Cache materials to avoid redundant shader compilation
const materialCache = new Map<string, THREE.Material>();

export function getProceduralMaterial(finishKey: string): THREE.Material {
  if (materialCache.has(finishKey)) {
    return materialCache.get(finishKey)!;
  }

  let mat: THREE.Material;

  switch (finishKey) {
    case 'wood_oak':
    case 'oak_parquet': {
      const tex = generateWoodTexture(false);
      mat = new THREE.MeshStandardMaterial({
        map: tex,
        roughness: 0.45,
        metalness: 0.05,
      });
      break;
    }

    case 'wood_walnut': {
      const tex = generateWoodTexture(true);
      mat = new THREE.MeshStandardMaterial({
        map: tex,
        roughness: 0.4,
        metalness: 0.05,
      });
      break;
    }

    case 'terrazzo': {
      const tex = generateTerrazzoTexture();
      mat = new THREE.MeshStandardMaterial({
        map: tex,
        roughness: 0.25, // polished reflective sheen
        metalness: 0.1,
      });
      break;
    }

    case 'concrete': {
      const tex = generateConcreteTexture();
      mat = new THREE.MeshStandardMaterial({
        map: tex,
        roughness: 0.7,
        metalness: 0.05,
      });
      break;
    }

    case 'tile_subway':
    case 'subway_tile': {
      const tex = generateTileTexture();
      mat = new THREE.MeshStandardMaterial({
        map: tex,
        roughness: 0.2, // glossy tile
        metalness: 0.05,
      });
      break;
    }

    case 'marble_carrara':
    case 'marble': {
      mat = new THREE.MeshStandardMaterial({
        color: 0xf8fafc,
        roughness: 0.2,
        metalness: 0.1,
      });
      break;
    }

    case 'fabric_beige':
    case 'fabric_jute':
    case 'fabric_boucle': {
      const tex = generateFabricTexture('#dfd7cb');
      mat = new THREE.MeshStandardMaterial({
        map: tex,
        roughness: 0.85,
        metalness: 0.0,
      });
      break;
    }

    case 'fabric_terracotta': {
      const tex = generateFabricTexture('#a44a3f');
      mat = new THREE.MeshStandardMaterial({
        map: tex,
        roughness: 0.85,
        metalness: 0.0,
      });
      break;
    }

    case 'fabric_gray':
    case 'fabric_black': {
      const tex = generateFabricTexture('#27272a');
      mat = new THREE.MeshStandardMaterial({
        map: tex,
        roughness: 0.85,
        metalness: 0.0,
      });
      break;
    }

    case 'metal_black':
    case 'aluminum_black': {
      mat = new THREE.MeshStandardMaterial({
        color: 0x1e293b,
        roughness: 0.4,
        metalness: 0.8,
      });
      break;
    }

    case 'metal_brass': {
      mat = new THREE.MeshStandardMaterial({
        color: 0xd4af37,
        roughness: 0.3,
        metalness: 0.85,
      });
      break;
    }

    case 'metal_stainless':
    case 'steel': {
      mat = new THREE.MeshStandardMaterial({
        color: 0xcfd4dc,
        roughness: 0.35,
        metalness: 0.9,
      });
      break;
    }

    case 'glass': {
      mat = new THREE.MeshPhysicalMaterial({
        color: 0xe0f2fe,
        transparent: true,
        opacity: 0.4,
        roughness: 0.1,
        metalness: 0.1,
        transmission: 0.7,
        ior: 1.5,
      });
      break;
    }

    case 'paint_white':
    case 'wall_default':
    default: {
      mat = new THREE.MeshStandardMaterial({
        color: 0xf1f5f9, // Architectural off-white
        roughness: 0.85,
        metalness: 0.02,
      });
      break;
    }
  }

  materialCache.set(finishKey, mat);
  return mat;
}

// Highlight material for selected objects in 3D
export const SELECTION_HIGHLIGHT_MATERIAL = new THREE.MeshBasicMaterial({
  color: 0x38bdf8,
  wireframe: true,
  wireframeLinewidth: 2,
});

// Warning material for collisions in 3D
export const COLLISION_WARNING_MATERIAL = new THREE.MeshBasicMaterial({
  color: 0xef4444,
  wireframe: true,
  wireframeLinewidth: 2,
});
