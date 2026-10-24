/**
 * 100% Procedural Texture Generator
 * Generates photorealistic architectural textures in-memory via HTML5 Canvas.
 * No external image files or CDNs are required. Runs completely offline.
 */

import * as THREE from 'three';

// Texture cache to prevent redundant canvas redraws
const textureCache = new Map<string, THREE.CanvasTexture>();

function createSafeCanvas(width: number, height: number): HTMLCanvasElement | null {
  if (typeof document === 'undefined') return null;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

/**
 * Procedural Oak Parquet / Wood Planks Texture
 */
export function generateWoodTexture(isWalnut = false): THREE.Texture {
  const cacheKey = isWalnut ? 'wood_walnut' : 'wood_oak';
  if (textureCache.has(cacheKey)) return textureCache.get(cacheKey)!;

  const canvas = createSafeCanvas(512, 512);
  if (!canvas) return new THREE.Texture();

  const ctx = canvas.getContext('2d');
  if (!ctx) return new THREE.Texture();

  const baseHue = isWalnut ? '#4a3325' : '#c89d68';
  const grainHue = isWalnut ? '#3b281c' : '#a87e4c';
  const highlightHue = isWalnut ? '#5e4332' : '#dfb582';

  ctx.fillStyle = baseHue;
  ctx.fillRect(0, 0, 512, 512);

  // Planks
  const plankHeight = 64;
  for (let y = 0; y < 512; y += plankHeight) {
    // Subtle plank variation
    const brightness = 0.9 + Math.random() * 0.2;
    ctx.fillStyle = `rgba(0,0,0,${(1 - brightness) * 0.4})`;
    ctx.fillRect(0, y, 512, plankHeight);

    // Wood grain lines
    ctx.strokeStyle = grainHue;
    ctx.lineWidth = 1;
    for (let i = 0; i < 35; i++) {
      const gy = y + Math.random() * plankHeight;
      ctx.beginPath();
      ctx.moveTo(0, gy);
      for (let x = 0; x <= 512; x += 32) {
        ctx.lineTo(x, gy + (Math.sin(x * 0.05) + Math.random() * 1.5 - 0.75));
      }
      ctx.stroke();
    }

    // Plank seam / bevel groove
    ctx.strokeStyle = 'rgba(0,0,0,0.45)';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(512, y);
    ctx.stroke();
  }

  // Staggered vertical end joints
  ctx.strokeStyle = 'rgba(0,0,0,0.5)';
  ctx.lineWidth = 2;
  for (let y = 0; y < 512; y += plankHeight) {
    const shift = (y / plankHeight) % 2 === 0 ? 128 : 256;
    for (let x = shift; x < 512; x += 256) {
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x, y + plankHeight);
      ctx.stroke();
    }
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(2, 2);
  textureCache.set(cacheKey, texture);
  return texture;
}

/**
 * Procedural Terrazzo Texture with Speckled Mineral Aggregates
 */
export function generateTerrazzoTexture(): THREE.Texture {
  const cacheKey = 'terrazzo';
  if (textureCache.has(cacheKey)) return textureCache.get(cacheKey)!;

  const canvas = createSafeCanvas(512, 512);
  if (!canvas) return new THREE.Texture();
  const ctx = canvas.getContext('2d');
  if (!ctx) return new THREE.Texture();

  // Neutral cream matrix
  ctx.fillStyle = '#f0ede6';
  ctx.fillRect(0, 0, 512, 512);

  // Speckle chips: Terracotta, Charcoal, White marble, Ochre
  const chipColors = ['#9e4a3b', '#2b2d42', '#ffffff', '#c59b27', '#6c757d', '#3a5a40'];

  for (let i = 0; i < 900; i++) {
    const x = Math.random() * 512;
    const y = Math.random() * 512;
    const size = 1.5 + Math.random() * 4.5;
    ctx.fillStyle = chipColors[Math.floor(Math.random() * chipColors.length)];

    ctx.beginPath();
    // Non-circular organic polygon chips
    const sides = 4 + Math.floor(Math.random() * 3);
    for (let s = 0; s < sides; s++) {
      const angle = (s / sides) * Math.PI * 2;
      const r = size * (0.7 + Math.random() * 0.6);
      const px = x + Math.cos(angle) * r;
      const py = y + Math.sin(angle) * r;
      if (s === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fill();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(3, 3);
  textureCache.set(cacheKey, texture);
  return texture;
}

/**
 * Procedural Polished Concrete Texture
 */
export function generateConcreteTexture(): THREE.Texture {
  const cacheKey = 'concrete';
  if (textureCache.has(cacheKey)) return textureCache.get(cacheKey)!;

  const canvas = createSafeCanvas(512, 512);
  if (!canvas) return new THREE.Texture();
  const ctx = canvas.getContext('2d');
  if (!ctx) return new THREE.Texture();

  // Base cool gray
  ctx.fillStyle = '#b8bec4';
  ctx.fillRect(0, 0, 512, 512);

  // Mottled noise layers
  for (let i = 0; i < 1500; i++) {
    const x = Math.random() * 512;
    const y = Math.random() * 512;
    const radius = 2 + Math.random() * 12;
    const isDark = Math.random() > 0.5;
    ctx.fillStyle = isDark ? 'rgba(0,0,0,0.03)' : 'rgba(255,255,255,0.04)';
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(4, 4);
  textureCache.set(cacheKey, texture);
  return texture;
}

/**
 * Procedural Subway Tile Texture with Recessed Grout
 */
export function generateTileTexture(): THREE.Texture {
  const cacheKey = 'subway_tile';
  if (textureCache.has(cacheKey)) return textureCache.get(cacheKey)!;

  const canvas = createSafeCanvas(512, 512);
  if (!canvas) return new THREE.Texture();
  const ctx = canvas.getContext('2d');
  if (!ctx) return new THREE.Texture();

  // Dark grout background
  ctx.fillStyle = '#334155';
  ctx.fillRect(0, 0, 512, 512);

  const tileW = 128;
  const tileH = 64;
  const grout = 4;

  let row = 0;
  for (let y = 0; y < 512; y += tileH) {
    const offsetX = (row % 2 === 0) ? 0 : tileW / 2;
    for (let x = -tileW; x < 512 + tileW; x += tileW) {
      // Off-white glossy tile face
      ctx.fillStyle = '#f8fafc';
      ctx.fillRect(x + offsetX + grout / 2, y + grout / 2, tileW - grout, tileH - grout);

      // Subtle bevel gradient highlight
      const grad = ctx.createLinearGradient(x + offsetX, y, x + offsetX, y + tileH);
      grad.addColorStop(0, 'rgba(255,255,255,0.4)');
      grad.addColorStop(0.2, 'rgba(255,255,255,0)');
      grad.addColorStop(0.8, 'rgba(0,0,0,0)');
      grad.addColorStop(1, 'rgba(0,0,0,0.15)');
      ctx.fillStyle = grad;
      ctx.fillRect(x + offsetX + grout / 2, y + grout / 2, tileW - grout, tileH - grout);
    }
    row++;
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(3, 3);
  textureCache.set(cacheKey, texture);
  return texture;
}

/**
 * Procedural Woven Fabric / Rug Texture
 */
export function generateFabricTexture(color = '#e2d9cc'): THREE.Texture {
  const cacheKey = `fabric_${color}`;
  if (textureCache.has(cacheKey)) return textureCache.get(cacheKey)!;

  const canvas = createSafeCanvas(256, 256);
  if (!canvas) return new THREE.Texture();
  const ctx = canvas.getContext('2d');
  if (!ctx) return new THREE.Texture();

  ctx.fillStyle = color;
  ctx.fillRect(0, 0, 256, 256);

  // Cross-hatch threads
  ctx.strokeStyle = 'rgba(0,0,0,0.08)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 256; i += 4) {
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i, 256);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(0, i);
    ctx.lineTo(256, i);
    ctx.stroke();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(4, 4);
  textureCache.set(cacheKey, texture);
  return texture;
}
