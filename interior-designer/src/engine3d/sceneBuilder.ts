/**
 * Three.js Scene Builder & Synchronizer
 * Rebuilds and synchronizes procedural 3D scene elements:
 * - Walls with true geometric carved voids
 * - Presentation Cutaway dynamic wall heights
 * - Doors with swing angle leaves and windows with physical glass
 * - Procedural floors with room finishes
 * - Procedural furniture meshes with selection wireframes
 */

import * as THREE from 'three';
import {
  Point2D,
  Wall,
  Opening,
  Room,
  FurnitureItem,
  SelectionState,
} from '../types/plan.js';
import { carveWallSegments } from '../core/wallCarving.js';
import { triangulatePolygon, distance } from '../core/geometry.js';
import { computeEffectiveWallHeight } from './cutaway.js';
import { getProceduralMaterial, SELECTION_HIGHLIGHT_MATERIAL } from './materials.js';
import { createProceduralFurnitureMesh } from './proceduralMeshes.js';
import { CATALOG_MAP } from '../catalog/items.js';

export interface SceneObjects {
  wallsGroup: THREE.Group;
  openingsGroup: THREE.Group;
  floorsGroup: THREE.Group;
  furnitureGroup: THREE.Group;
  selectionGroup: THREE.Group;
}

export function initSceneHierarchy(scene: THREE.Scene): SceneObjects {
  const wallsGroup = new THREE.Group();
  const openingsGroup = new THREE.Group();
  const floorsGroup = new THREE.Group();
  const furnitureGroup = new THREE.Group();
  const selectionGroup = new THREE.Group();

  scene.add(floorsGroup);
  scene.add(wallsGroup);
  scene.add(openingsGroup);
  scene.add(furnitureGroup);
  scene.add(selectionGroup);

  return {
    wallsGroup,
    openingsGroup,
    floorsGroup,
    furnitureGroup,
    selectionGroup,
  };
}

export function updateScene3D(
  sceneObjects: SceneObjects,
  vertices: Record<string, Point2D>,
  walls: Record<string, Wall>,
  openings: Record<string, Opening>,
  furniture: Record<string, FurnitureItem>,
  rooms: Room[],
  selection: SelectionState,
  cameraPos: THREE.Vector3,
  sceneCenter: THREE.Vector3,
  isCutawayActive: boolean
) {
  const { wallsGroup, openingsGroup, floorsGroup, furnitureGroup, selectionGroup } = sceneObjects;

  // Clear previous meshes
  while (wallsGroup.children.length > 0) {
    const obj = wallsGroup.children[0];
    wallsGroup.remove(obj);
  }
  while (openingsGroup.children.length > 0) {
    const obj = openingsGroup.children[0];
    openingsGroup.remove(obj);
  }
  while (floorsGroup.children.length > 0) {
    const obj = floorsGroup.children[0];
    floorsGroup.remove(obj);
  }
  while (furnitureGroup.children.length > 0) {
    const obj = furnitureGroup.children[0];
    furnitureGroup.remove(obj);
  }
  while (selectionGroup.children.length > 0) {
    const obj = selectionGroup.children[0];
    selectionGroup.remove(obj);
  }

  // 1. Build Procedural Floors
  for (const room of rooms) {
    if (room.polygon.length < 3) continue;

    const triangles = triangulatePolygon(room.polygon);
    if (triangles.length === 0) continue;

    const positions: number[] = [];
    const uvs: number[] = [];
    const normals: number[] = [];

    for (const tri of triangles) {
      for (const idx of tri) {
        const pt = room.polygon[idx];
        positions.push(pt.x, 0.001, -pt.y); // Floor at Y=0.001 to prevent z-fighting with ground
        uvs.push(pt.x * 0.5, pt.y * 0.5);
        normals.push(0, 1, 0);
      }
    }

    const floorGeo = new THREE.BufferGeometry();
    floorGeo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    floorGeo.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
    floorGeo.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3));

    const floorMat = getProceduralMaterial(room.floorFinish);
    const floorMesh = new THREE.Mesh(floorGeo, floorMat);
    floorMesh.receiveShadow = true;
    floorMesh.userData = { type: 'room', id: room.id };
    floorsGroup.add(floorMesh);
  }

  // 2. Build Walls with True Carved Openings
  const openingsByWall: Record<string, Opening[]> = {};
  for (const op of Object.values(openings)) {
    if (!openingsByWall[op.wallId]) openingsByWall[op.wallId] = [];
    openingsByWall[op.wallId].push(op);
  }

  for (const wall of Object.values(walls)) {
    const p1 = vertices[wall.startId];
    const p2 = vertices[wall.endId];
    if (!p1 || !p2) continue;

    // Presentation cutaway dynamic height calculation
    const effHeight = computeEffectiveWallHeight(
      wall,
      p1,
      p2,
      cameraPos,
      sceneCenter,
      isCutawayActive,
      0.25
    );

    const wallOpenings = openingsByWall[wall.id] || [];
    const segments = carveWallSegments(wall, p1, p2, wallOpenings, effHeight);
    const wallMat = getProceduralMaterial(wall.finish || 'paint_white');

    for (const seg of segments) {
      const boxGeo = new THREE.BoxGeometry(seg.length, seg.height, seg.width);
      const boxMesh = new THREE.Mesh(boxGeo, wallMat);

      boxMesh.position.set(seg.centerX, seg.centerZ, -seg.centerY);
      boxMesh.rotation.y = -seg.angleY;
      boxMesh.castShadow = true;
      boxMesh.receiveShadow = true;
      boxMesh.userData = { type: 'wall', id: wall.id };

      wallsGroup.add(boxMesh);

      // Selection wireframe highlight
      if (selection.type === 'wall' && selection.id === wall.id) {
        const wireGeo = new THREE.BoxGeometry(seg.length + 0.02, seg.height + 0.02, seg.width + 0.02);
        const wireMesh = new THREE.Mesh(wireGeo, SELECTION_HIGHLIGHT_MATERIAL);
        wireMesh.position.copy(boxMesh.position);
        wireMesh.rotation.copy(boxMesh.rotation);
        selectionGroup.add(wireMesh);
      }
    }
  }

  // 3. Build Doors and Windows
  for (const op of Object.values(openings)) {
    const wall = walls[op.wallId];
    if (!wall) continue;
    const p1 = vertices[wall.startId];
    const p2 = vertices[wall.endId];
    if (!p1 || !p2) continue;

    const wallLen = distance(p1, p2);
    if (wallLen < 0.1) continue;

    const angle = Math.atan2(p2.y - p1.y, p2.x - p1.x);
    const uCenter = op.offset * wallLen;
    const worldCenterX = p1.x + uCenter * Math.cos(angle);
    const worldCenterY = p1.y + uCenter * Math.sin(angle);

    const opGroup = new THREE.Group();
    opGroup.position.set(worldCenterX, 0, -worldCenterY);
    opGroup.rotation.y = -angle;
    opGroup.userData = { type: 'opening', id: op.id };

    if (op.type === 'door') {
      // Door Leaf pivoted at hinge
      const isLeft = op.swingDirection === 'left';
      const leafPivot = new THREE.Group();
      const hingeX = isLeft ? -op.width / 2 : op.width / 2;
      leafPivot.position.set(hingeX, 0, 0);

      // Swing rotation around Y axis
      const swingSign = isLeft ? 1 : -1;
      const swingRad = ((op.swingAngle * Math.PI) / 180) * swingSign;
      leafPivot.rotation.y = swingRad;

      // Door leaf panel
      const leafThick = 0.04;
      const leafGeo = new THREE.BoxGeometry(op.width, op.height, leafThick);
      const leafMat = getProceduralMaterial(op.finish || 'wood_oak');
      const leafMesh = new THREE.Mesh(leafGeo, leafMat);
      // Offset leaf from pivot so hinge is on the edge
      leafMesh.position.set(isLeft ? op.width / 2 : -op.width / 2, op.height / 2, 0);
      leafMesh.castShadow = true;
      leafPivot.add(leafMesh);

      // Handle / Knob
      const knobGeo = new THREE.CylinderGeometry(0.015, 0.015, 0.08, 12);
      const knobMesh = new THREE.Mesh(knobGeo, getProceduralMaterial('metal_brass'));
      knobMesh.rotation.x = Math.PI / 2;
      knobMesh.position.set(isLeft ? op.width - 0.08 : -op.width + 0.08, 0.95, 0.04);
      leafPivot.add(knobMesh);

      opGroup.add(leafPivot);
    } else {
      // Window: Frame + Glass Pane
      const frameThick = wall.thickness * 0.8;
      const frameMat = getProceduralMaterial(op.finish || 'aluminum_black');

      // Glass Pane
      const glassGeo = new THREE.BoxGeometry(op.width - 0.08, op.height - 0.08, 0.015);
      const glassMat = getProceduralMaterial('glass');
      const glassMesh = new THREE.Mesh(glassGeo, glassMat);
      glassMesh.position.set(0, op.sillElevation + op.height / 2, 0);
      opGroup.add(glassMesh);

      // Surrounding sill & sash frame
      const frameGeo = new THREE.BoxGeometry(op.width, 0.04, frameThick);
      const sillMesh = new THREE.Mesh(frameGeo, frameMat);
      sillMesh.position.set(0, op.sillElevation, 0);
      opGroup.add(sillMesh);
    }

    openingsGroup.add(opGroup);

    // Selection highlight for opening
    if (selection.type === 'opening' && selection.id === op.id) {
      const boxWire = new THREE.BoxGeometry(op.width + 0.04, op.height + 0.04, wall.thickness + 0.04);
      const wireMesh = new THREE.Mesh(boxWire, SELECTION_HIGHLIGHT_MATERIAL);
      wireMesh.position.set(worldCenterX, op.sillElevation + op.height / 2, -worldCenterY);
      wireMesh.rotation.y = -angle;
      selectionGroup.add(wireMesh);
    }
  }

  // 4. Build Procedural Furniture
  for (const item of Object.values(furniture)) {
    const catDef = CATALOG_MAP.get(item.catalogId);
    const procType = catDef?.proceduralType || 'armchair_lounge';

    const itemMesh = createProceduralFurnitureMesh(
      procType,
      item.width,
      item.depth,
      item.height,
      item.finish
    );

    itemMesh.position.set(item.x, item.z || 0, -item.y);
    itemMesh.rotation.y = item.rotation;
    itemMesh.userData = { type: 'furniture', id: item.id };

    furnitureGroup.add(itemMesh);

    // Selection Bounding Wireframe
    if (selection.type === 'furniture' && selection.id === item.id) {
      const boxGeo = new THREE.BoxGeometry(item.width + 0.04, item.height + 0.04, item.depth + 0.04);
      const wireMesh = new THREE.Mesh(boxGeo, SELECTION_HIGHLIGHT_MATERIAL);
      wireMesh.position.set(item.x, (item.z || 0) + item.height / 2, -item.y);
      wireMesh.rotation.y = item.rotation;
      selectionGroup.add(wireMesh);
    }
  }
}
