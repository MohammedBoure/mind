/**
 * Real-Time First-Person Walkthrough Controller
 * - Pointer-Lock mouse look and WASD keyboard motion
 * - Eye level ~1.65m, collision radius ~0.18m
 * - Architectural traversal rules (cannot pass through walls, windows, or doors open < 55°)
 * - Automatic camera recovery when trapped inside solid geometry
 */

import * as THREE from 'three';
import { Wall, Opening, FurnitureItem, Point2D, Room } from '../types/plan.js';
import { checkWalkthroughCollision } from '../core/collision.js';
import { calculatePolygonCentroid } from '../core/geometry.js';

export class WalkthroughController {
  private camera: THREE.PerspectiveCamera;
  private domElement: HTMLElement;
  private isLocked = false;

  // Player state
  public position: THREE.Vector3;
  private eyeHeight = 1.65; // meters
  private collisionRadius = 0.18; // meters
  private moveSpeed = 4.2; // meters per second

  // Euler angles
  private pitch = 0; // vertical look
  private yaw = 0;   // horizontal look

  // Key states
  private keys = {
    forward: false,
    backward: false,
    left: false,
    right: false,
  };

  constructor(camera: THREE.PerspectiveCamera, domElement: HTMLElement) {
    this.camera = camera;
    this.domElement = domElement;
    this.position = new THREE.Vector3(0, this.eyeHeight, 0);

    this.initEventListeners();
  }

  private initEventListeners() {
    this.domElement.addEventListener('click', () => {
      if (!this.isLocked) {
        this.domElement.requestPointerLock();
      }
    });

    document.addEventListener('pointerlockchange', () => {
      this.isLocked = document.pointerLockElement === this.domElement;
    });

    document.addEventListener('mousemove', (e) => {
      if (!this.isLocked) return;

      const movementX = e.movementX || 0;
      const movementY = e.movementY || 0;

      // Sensitivity
      this.yaw -= movementX * 0.0022;
      this.pitch -= movementY * 0.0022;

      // Clamp pitch (-85° to +85°)
      const maxPitch = (85 * Math.PI) / 180;
      this.pitch = Math.max(-maxPitch, Math.min(maxPitch, this.pitch));

      this.updateCameraRotation();
    });

    window.addEventListener('keydown', (e) => {
      if (!this.isLocked) return;
      if (e.code === 'KeyW' || e.code === 'ArrowUp') this.keys.forward = true;
      if (e.code === 'KeyS' || e.code === 'ArrowDown') this.keys.backward = true;
      if (e.code === 'KeyA' || e.code === 'ArrowLeft') this.keys.left = true;
      if (e.code === 'KeyD' || e.code === 'ArrowRight') this.keys.right = true;
    });

    window.addEventListener('keyup', (e) => {
      if (e.code === 'KeyW' || e.code === 'ArrowUp') this.keys.forward = false;
      if (e.code === 'KeyS' || e.code === 'ArrowDown') this.keys.backward = false;
      if (e.code === 'KeyA' || e.code === 'ArrowLeft') this.keys.left = false;
      if (e.code === 'KeyD' || e.code === 'ArrowRight') this.keys.right = false;
    });
  }

  private updateCameraRotation() {
    this.camera.rotation.set(0, 0, 0);
    const euler = new THREE.Euler(this.pitch, this.yaw, 0, 'YXZ');
    this.camera.quaternion.setFromEuler(euler);
  }

  public teleport(x: number, z: number, targetYaw?: number) {
    this.position.set(x, this.eyeHeight, z);
    if (targetYaw !== undefined) this.yaw = targetYaw;
    this.updateCameraRotation();
    this.camera.position.copy(this.position);
  }

  public update(
    deltaSec: number,
    walls: Record<string, Wall>,
    openings: Record<string, Opening>,
    vertices: Record<string, Point2D>,
    furniture: Record<string, FurnitureItem>
  ) {
    if (!this.isLocked) return;

    const moveX = (this.keys.right ? 1 : 0) - (this.keys.left ? 1 : 0);
    const moveZ = (this.keys.backward ? 1 : 0) - (this.keys.forward ? 1 : 0);

    if (moveX === 0 && moveZ === 0) return;

    // Movement direction relative to yaw
    const forwardX = -Math.sin(this.yaw);
    const forwardZ = -Math.cos(this.yaw);
    const rightX = Math.cos(this.yaw);
    const rightZ = -Math.sin(this.yaw);

    const dir = new THREE.Vector3(
      forwardX * -moveZ + rightX * moveX,
      0,
      forwardZ * -moveZ + rightZ * moveX
    ).normalize();

    const dist = this.moveSpeed * deltaSec;
    const targetX = this.position.x + dir.x * dist;
    const targetZ = this.position.z + dir.z * dist;

    // Convert Three.js (X, -Z) to 2D Planar (x, y)
    const planTarget = { x: targetX, y: -targetZ };

    // Check collision with walls, closed doors, windows, and furniture
    const colResult = checkWalkthroughCollision(
      planTarget,
      this.collisionRadius,
      walls,
      openings,
      vertices,
      furniture
    );

    // Apply corrected position
    this.position.x = colResult.correctedPos.x;
    this.position.z = -colResult.correctedPos.y;
    this.position.y = this.eyeHeight;

    this.camera.position.copy(this.position);
  }

  /**
   * Automatic recovery mechanism: If camera is trapped inside solid geometry
   * (e.g. wall edit or initial spawn), teleports safely to the center of the largest cleared room.
   */
  public recoverIfTrapped(
    rooms: Room[],
    walls: Record<string, Wall>,
    openings: Record<string, Opening>,
    vertices: Record<string, Point2D>,
    furniture: Record<string, FurnitureItem>,
    force = false
  ): boolean {
    const curPlanPos = { x: this.position.x, y: -this.position.z };
    const col = checkWalkthroughCollision(
      curPlanPos,
      this.collisionRadius,
      walls,
      openings,
      vertices,
      furniture
    );

    const isInitialZero = Math.abs(this.position.x) < 0.01 && Math.abs(this.position.z) < 0.01;

    if (force || col.hasCollision || isInitialZero) {
      // Find largest cleared room
      let bestRoom = rooms[0];
      for (const r of rooms) {
        if (r.area > (bestRoom?.area || 0)) {
          bestRoom = r;
        }
      }

      if (bestRoom && bestRoom.polygon.length >= 3) {
        const centroid = calculatePolygonCentroid(bestRoom.polygon);
        this.teleport(centroid.x, -centroid.y);
        return true;
      }
    }
    return false;
  }

  public getIsLocked(): boolean {
    return this.isLocked;
  }
}
