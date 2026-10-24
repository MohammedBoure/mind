/**
 * Presentation Cutaway Engine
 * Dynamically computes effective wall heights for orbit camera dollhouse views:
 * Perimeter walls on the viewer/camera side dynamically drop to low plinths (0.25m)
 * to reveal the interior without awkward wall occlusions.
 */

import * as THREE from 'three';
import { Point2D, Wall } from '../types/plan.js';
import { midpoint } from '../core/geometry.js';

export function computeEffectiveWallHeight(
  wall: Wall,
  pStart: Point2D,
  pEnd: Point2D,
  cameraPos: THREE.Vector3,
  sceneCenter: THREE.Vector3,
  isCutawayActive: boolean,
  cutawayHeight = 0.25
): number {
  if (!isCutawayActive) {
    return wall.height;
  }

  // Wall midpoint in Three.js space (X=x, Y=0, Z=-y)
  const mid = midpoint(pStart, pEnd);
  const wallMidX = mid.x;
  const wallMidZ = -mid.y;

  // Vector from scene center to camera
  const toCamX = cameraPos.x - sceneCenter.x;
  const toCamZ = cameraPos.z - sceneCenter.z;
  const camDistToCenter = Math.hypot(toCamX, toCamZ);

  // Vector from scene center to wall midpoint
  const toWallX = wallMidX - sceneCenter.x;
  const toWallZ = wallMidZ - sceneCenter.z;

  // Dot product in horizontal plane: Is wall on the camera side of the building?
  const dot = toCamX * toWallX + toCamZ * toWallZ;

  // Distance from camera to wall midpoint
  const distCamToWall = Math.hypot(cameraPos.x - wallMidX, cameraPos.z - wallMidZ);

  // Wall is on viewer side if it projects positively towards camera and is closer than scene center
  if (dot > 0 && distCamToWall < camDistToCenter * 1.05) {
    return cutawayHeight;
  }

  return wall.height;
}
