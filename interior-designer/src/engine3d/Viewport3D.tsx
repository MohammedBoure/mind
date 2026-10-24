import React, { useRef, useEffect, useState, useCallback, useImperativeHandle, forwardRef } from 'react';
import * as THREE from 'three';
import {
  Point2D,
  Wall,
  Opening,
  Room,
  FurnitureItem,
  SelectionState,
} from '../types/plan.js';
import { initSceneHierarchy, updateScene3D, SceneObjects } from './sceneBuilder.js';
import { WalkthroughController } from './walkthrough.js';

export interface Viewport3DHandle {
  captureSnapshot: () => string;
}

interface Viewport3DProps {
  vertices: Record<string, Point2D>;
  walls: Record<string, Wall>;
  openings: Record<string, Opening>;
  furniture: Record<string, FurnitureItem>;
  rooms: Room[];
  selection: SelectionState;
  isWalkthrough: boolean;
  cutawayMode: boolean;
  onSelect: (selection: SelectionState) => void;
  onToggleWalkthrough: (active: boolean) => void;
}

export const Viewport3D = forwardRef<Viewport3DHandle, Viewport3DProps>(({
  vertices,
  walls,
  openings,
  furniture,
  rooms,
  selection,
  isWalkthrough,
  cutawayMode,
  onSelect,
  onToggleWalkthrough,
}, ref) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const orbitCameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const walkCameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const sceneObjectsRef = useRef<SceneObjects | null>(null);
  const walkthroughControllerRef = useRef<WalkthroughController | null>(null);

  // Orbit camera parameters
  const orbitState = useRef({
    radius: 14,
    theta: Math.PI / 4, // Azimuth angle
    phi: Math.PI / 3,   // Polar elevation angle (60°)
    target: new THREE.Vector3(0, 1.2, 0),
    isDragging: false,
    dragButton: 0,
    lastX: 0,
    lastY: 0,
  });

  const [isPointerLocked, setIsPointerLocked] = useState(false);

  // Provide imperative snapshot method
  useImperativeHandle(ref, () => ({
    captureSnapshot: () => {
      if (!rendererRef.current || !sceneRef.current) return '';
      const activeCam = isWalkthrough ? walkCameraRef.current : orbitCameraRef.current;
      if (!activeCam) return '';
      rendererRef.current.render(sceneRef.current, activeCam);
      return rendererRef.current.domElement.toDataURL('image/png');
    },
  }));

  // Update Orbit Camera Position based on Spherical coordinates
  const updateOrbitCamera = useCallback(() => {
    const cam = orbitCameraRef.current;
    if (!cam) return;
    const s = orbitState.current;

    // Convert spherical to cartesian
    const x = s.target.x + s.radius * Math.sin(s.phi) * Math.sin(s.theta);
    const y = s.target.y + s.radius * Math.cos(s.phi);
    const z = s.target.z + s.radius * Math.sin(s.phi) * Math.cos(s.theta);

    cam.position.set(x, y, z);
    cam.lookAt(s.target);
  }, []);

  // Initialize Three.js
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // 1. Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f172a); // Slate 900 architectural background
    scene.fog = new THREE.FogExp2(0x0f172a, 0.015);
    sceneRef.current = scene;

    // 2. Cameras
    const width = container.clientWidth;
    const height = container.clientHeight;
    const aspect = width / height || 1;

    const orbitCam = new THREE.PerspectiveCamera(45, aspect, 0.1, 100);
    orbitCameraRef.current = orbitCam;
    updateOrbitCamera();

    const walkCam = new THREE.PerspectiveCamera(65, aspect, 0.05, 50);
    walkCam.position.set(0, 1.65, 0);
    walkCameraRef.current = walkCam;

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      preserveDrawingBuffer: true,
      powerPreference: 'high-performance',
    });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;

    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 4. Lighting
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x334155, 0.7);
    hemiLight.position.set(0, 20, 0);
    scene.add(hemiLight);

    const dirLight = new THREE.DirectionalLight(0xfff8ee, 1.4);
    dirLight.position.set(12, 18, 10);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    dirLight.shadow.camera.near = 0.5;
    dirLight.shadow.camera.far = 40;
    const d = 14;
    dirLight.shadow.camera.left = -d;
    dirLight.shadow.camera.right = d;
    dirLight.shadow.camera.top = d;
    dirLight.shadow.camera.bottom = -d;
    dirLight.shadow.bias = -0.0003;
    scene.add(dirLight);

    // Subtle Ground Grid Plane
    const gridHelper = new THREE.GridHelper(30, 30, 0x38bdf8, 0x1e293b);
    gridHelper.position.y = -0.005;
    scene.add(gridHelper);

    // 5. Scene Objects Hierarchy
    sceneObjectsRef.current = initSceneHierarchy(scene);

    // 6. Walkthrough Controller
    const controller = new WalkthroughController(walkCam, renderer.domElement);
    walkthroughControllerRef.current = controller;

    // Animation Loop
    let animId: number;
    let lastTime = performance.now();

    const animate = (time: number) => {
      animId = requestAnimationFrame(animate);
      const deltaSec = (time - lastTime) / 1000;
      lastTime = time;

      if (isWalkthrough && walkthroughControllerRef.current) {
        walkthroughControllerRef.current.update(
          Math.min(deltaSec, 0.1),
          walls,
          openings,
          vertices,
          furniture
        );
        setIsPointerLocked(walkthroughControllerRef.current.getIsLocked());
        renderer.render(scene, walkCam);
      } else {
        renderer.render(scene, orbitCam);
      }
    };
    animId = requestAnimationFrame(animate);

    // Resize Observer
    const resizeObserver = new ResizeObserver(() => {
      if (!containerRef.current || !rendererRef.current) return;
      const w = containerRef.current.clientWidth;
      const h = containerRef.current.clientHeight;
      const a = w / h;

      if (orbitCameraRef.current) {
        orbitCameraRef.current.aspect = a;
        orbitCameraRef.current.updateProjectionMatrix();
      }
      if (walkCameraRef.current) {
        walkCameraRef.current.aspect = a;
        walkCameraRef.current.updateProjectionMatrix();
      }
      rendererRef.current.setSize(w, h);
    });
    resizeObserver.observe(container);

    return () => {
      cancelAnimationFrame(animId);
      resizeObserver.disconnect();
      if (renderer.domElement.parentElement) {
        renderer.domElement.parentElement.removeChild(renderer.domElement);
      }
      renderer.dispose();
    };
  }, []);

  // Synchronize 3D scene elements when state changes
  useEffect(() => {
    if (!sceneObjectsRef.current || !orbitCameraRef.current) return;

    // In walkthrough mode, cutaway is strictly disabled so walls regain full height!
    const effectiveCutaway = isWalkthrough ? false : cutawayMode;
    const activeCam = isWalkthrough ? walkCameraRef.current! : orbitCameraRef.current!;

    updateScene3D(
      sceneObjectsRef.current,
      vertices,
      walls,
      openings,
      furniture,
      rooms,
      selection,
      activeCam.position,
      orbitState.current.target,
      effectiveCutaway
    );

    // Automatic recovery check: If a wall edit traps the camera inside solid geometry
    if (isWalkthrough && walkthroughControllerRef.current) {
      walkthroughControllerRef.current.recoverIfTrapped(
        rooms,
        walls,
        openings,
        vertices,
        furniture
      );
    }
  }, [vertices, walls, openings, furniture, rooms, selection, isWalkthrough, cutawayMode]);

  // When switching to walkthrough mode: auto-position player into room center
  useEffect(() => {
    if (isWalkthrough && walkthroughControllerRef.current) {
      walkthroughControllerRef.current.recoverIfTrapped(
        rooms,
        walls,
        openings,
        vertices,
        furniture
      );
    }
  }, [isWalkthrough]);

  // Orbit Mouse & Pointer Controls
  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (isWalkthrough) return;
    orbitState.current.isDragging = true;
    orbitState.current.dragButton = e.button;
    orbitState.current.lastX = e.clientX;
    orbitState.current.lastY = e.clientY;
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (isWalkthrough || !orbitState.current.isDragging) return;
    const s = orbitState.current;
    const dx = e.clientX - s.lastX;
    const dy = e.clientY - s.lastY;
    s.lastX = e.clientX;
    s.lastY = e.clientY;

    if (s.dragButton === 0) {
      // Left button: Orbit rotation
      s.theta -= dx * 0.007;
      s.phi = Math.max(0.1, Math.min(Math.PI / 2 - 0.05, s.phi - dy * 0.007));
      updateOrbitCamera();

      // Trigger cutaway wall update as camera orbits
      if (cutawayMode && sceneObjectsRef.current && orbitCameraRef.current) {
        updateScene3D(
          sceneObjectsRef.current,
          vertices,
          walls,
          openings,
          furniture,
          rooms,
          selection,
          orbitCameraRef.current.position,
          s.target,
          true
        );
      }
    } else if (s.dragButton === 2 || s.dragButton === 1) {
      // Right or middle button: Pan target
      const panSpeed = s.radius * 0.0015;
      const forwardX = -Math.sin(s.theta);
      const forwardZ = -Math.cos(s.theta);
      const rightX = Math.cos(s.theta);
      const rightZ = -Math.sin(s.theta);

      s.target.x -= (rightX * dx - forwardX * dy) * panSpeed;
      s.target.z -= (rightZ * dx - forwardZ * dy) * panSpeed;
      updateOrbitCamera();
    }
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isWalkthrough && orbitState.current.isDragging) {
      const movedDist = Math.hypot(
        e.clientX - orbitState.current.lastX,
        e.clientY - orbitState.current.lastY
      );

      orbitState.current.isDragging = false;

      // Click selection raycast
      if (movedDist < 3 && e.button === 0 && rendererRef.current && sceneRef.current && orbitCameraRef.current) {
        const rect = rendererRef.current.domElement.getBoundingClientRect();
        const mouse = new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          -((e.clientY - rect.top) / rect.height) * 2 + 1
        );

        const raycaster = new THREE.Raycaster();
        raycaster.setFromCamera(mouse, orbitCameraRef.current);

        const intersects = raycaster.intersectObjects(sceneRef.current.children, true);
        let found = false;

        for (const hit of intersects) {
          let curr: THREE.Object3D | null = hit.object;
          while (curr && curr !== sceneRef.current) {
            if (curr.userData && curr.userData.type && curr.userData.id) {
              onSelect({ type: curr.userData.type, id: curr.userData.id });
              found = true;
              break;
            }
            curr = curr.parent;
          }
          if (found) break;
        }

        if (!found) {
          onSelect({ type: 'none', id: null });
        }
      }
    }
  };

  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (isWalkthrough) return;
    const s = orbitState.current;
    const zoomFactor = e.deltaY > 0 ? 1.1 : 0.9;
    s.radius = Math.max(2, Math.min(45, s.radius * zoomFactor));
    updateOrbitCamera();

    if (cutawayMode && sceneObjectsRef.current && orbitCameraRef.current) {
      updateScene3D(
        sceneObjectsRef.current,
        vertices,
        walls,
        openings,
        furniture,
        rooms,
        selection,
        orbitCameraRef.current.position,
        s.target,
        true
      );
    }
  };

  return (
    <div
      ref={containerRef}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onWheel={handleWheel}
      onContextMenu={(e) => e.preventDefault()}
      className="relative w-full h-full overflow-hidden bg-slate-900 select-none cursor-grab active:cursor-grabbing"
    >
      {/* 3D Viewport Mode HUD Overlay */}
      <div className="absolute top-3 left-3 bg-slate-900/80 backdrop-blur border border-slate-800 text-xs text-slate-300 px-3 py-1.5 rounded-lg flex items-center space-x-3 pointer-events-none shadow-md">
        <span className="font-semibold text-sky-400">
          {isWalkthrough ? '🚶 Walkthrough Mode' : '🪐 Orbit 3D'}
        </span>
        <span className="text-slate-500">|</span>
        <span>{isWalkthrough ? 'Eye Level: 1.65m' : cutawayMode ? 'Cutaway: ON' : 'Cutaway: OFF'}</span>
      </div>

      {/* Walkthrough Instructions Modal / Pill */}
      {isWalkthrough && (
        <div className="absolute top-3 left-1/2 -translate-x-1/2 bg-sky-950/90 border border-sky-500/60 text-sky-200 text-xs px-4 py-2 rounded-full shadow-2xl flex items-center space-x-3 pointer-events-auto">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>
            {isPointerLocked
              ? 'Click to unlock | WASD / Arrows to walk | Traversal clearance: doors open > 55°'
              : 'Click canvas to Lock Mouse & Walk (WASD)'}
          </span>
          <button
            onClick={() => {
              walkthroughControllerRef.current?.recoverIfTrapped(
                rooms,
                walls,
                openings,
                vertices,
                furniture,
                true
              );
            }}
            title="Teleport to safe center of room"
            className="bg-sky-900 hover:bg-sky-800 text-sky-200 text-xs px-2.5 py-1 rounded border border-sky-600/50 transition cursor-pointer"
          >
            Recover View
          </button>
          <button
            onClick={() => onToggleWalkthrough(false)}
            className="ml-1 bg-slate-800 hover:bg-slate-700 text-white font-medium px-2.5 py-1 rounded text-xs border border-slate-700 transition cursor-pointer"
          >
            Exit Walkthrough
          </button>
        </div>
      )}
    </div>
  );
});
