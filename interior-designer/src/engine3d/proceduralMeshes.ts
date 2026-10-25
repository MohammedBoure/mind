/**
 * Procedural 3D Furniture & Architectural Fixture Geometries
 * Generates all 18 parametric catalog elements procedurally via Three.js primitives.
 * Completely offline with zero external 3D model dependencies.
 */

import * as THREE from 'three';
import { getProceduralMaterial } from './materials.js';

export function createProceduralFurnitureMesh(
  type: string,
  width: number,
  depth: number,
  height: number,
  finish: string
): THREE.Group {
  const group = new THREE.Group();
  const mat = getProceduralMaterial(finish);
  const metalMat = getProceduralMaterial('metal_black');
  const woodMat = getProceduralMaterial('wood_oak');

  switch (type) {
    case 'table_dining_rect': {
      // Tabletop
      const topThick = 0.04;
      const topGeo = new THREE.BoxGeometry(width, topThick, depth);
      const topMesh = new THREE.Mesh(topGeo, mat);
      topMesh.position.y = height - topThick / 2;
      topMesh.castShadow = true;
      topMesh.receiveShadow = true;
      group.add(topMesh);

      // 4 Metal Legs
      const legRadius = 0.025;
      const legHeight = height - topThick;
      const legGeo = new THREE.CylinderGeometry(legRadius, legRadius, legHeight, 16);
      const insetX = width / 2 - 0.08;
      const insetZ = depth / 2 - 0.08;

      const legPositions = [
        { x: insetX, z: insetZ },
        { x: -insetX, z: insetZ },
        { x: insetX, z: -insetZ },
        { x: -insetX, z: -insetZ },
      ];

      for (const pos of legPositions) {
        const leg = new THREE.Mesh(legGeo, metalMat);
        leg.position.set(pos.x, legHeight / 2, pos.z);
        leg.castShadow = true;
        group.add(leg);
      }
      break;
    }

    case 'table_bistro_round': {
      const topRadius = width / 2;
      const topThick = 0.03;
      const topGeo = new THREE.CylinderGeometry(topRadius, topRadius, topThick, 32);
      const topMesh = new THREE.Mesh(topGeo, mat);
      topMesh.position.y = height - topThick / 2;
      topMesh.castShadow = true;
      group.add(topMesh);

      // Central pedestal post
      const postRadius = 0.035;
      const postHeight = height - topThick - 0.02;
      const postGeo = new THREE.CylinderGeometry(postRadius, postRadius, postHeight, 16);
      const postMesh = new THREE.Mesh(postGeo, metalMat);
      postMesh.position.y = postHeight / 2 + 0.02;
      postMesh.castShadow = true;
      group.add(postMesh);

      // Weighted Base Disk
      const baseGeo = new THREE.CylinderGeometry(topRadius * 0.55, topRadius * 0.55, 0.02, 32);
      const baseMesh = new THREE.Mesh(baseGeo, metalMat);
      baseMesh.position.y = 0.01;
      baseMesh.receiveShadow = true;
      group.add(baseMesh);
      break;
    }

    case 'chair_bistro': {
      const seatHeight = height * 0.55;
      const seatGeo = new THREE.BoxGeometry(width, 0.04, depth);
      const seatMesh = new THREE.Mesh(seatGeo, mat);
      seatMesh.position.y = seatHeight;
      seatMesh.castShadow = true;
      group.add(seatMesh);

      // 4 Legs
      const legGeo = new THREE.CylinderGeometry(0.015, 0.012, seatHeight, 12);
      const sx = width / 2 - 0.04;
      const sz = depth / 2 - 0.04;
      const legs = [
        { x: sx, z: sz },
        { x: -sx, z: sz },
        { x: sx, z: -sz },
        { x: -sx, z: -sz },
      ];
      for (const pos of legs) {
        const leg = new THREE.Mesh(legGeo, woodMat);
        leg.position.set(pos.x, seatHeight / 2, pos.z);
        leg.castShadow = true;
        group.add(leg);
      }

      // Curved Backrest Posts and Slat
      const backHeight = height - seatHeight;
      const backGeo = new THREE.BoxGeometry(width * 0.85, backHeight * 0.45, 0.02);
      const backMesh = new THREE.Mesh(backGeo, woodMat);
      backMesh.position.set(0, height - backHeight * 0.25, -depth / 2 + 0.02);
      backMesh.castShadow = true;
      group.add(backMesh);
      break;
    }

    case 'bar_stool': {
      const seatThick = 0.04;
      const seatGeo = new THREE.CylinderGeometry(width / 2, width / 2, seatThick, 24);
      const seatMesh = new THREE.Mesh(seatGeo, woodMat);
      seatMesh.position.y = height - seatThick / 2;
      seatMesh.castShadow = true;
      group.add(seatMesh);

      // 4 Slender tall legs
      const legH = height - seatThick;
      const legGeo = new THREE.CylinderGeometry(0.014, 0.014, legH, 12);
      const off = width * 0.32;
      const legs = [
        { x: off, z: off },
        { x: -off, z: off },
        { x: off, z: -off },
        { x: -off, z: -off },
      ];
      for (const pos of legs) {
        const leg = new THREE.Mesh(legGeo, metalMat);
        leg.position.set(pos.x, legH / 2, pos.z);
        leg.castShadow = true;
        group.add(leg);
      }

      // Footrest Ring
      const ringGeo = new THREE.TorusGeometry(width * 0.35, 0.012, 8, 24);
      const ringMesh = new THREE.Mesh(ringGeo, metalMat);
      ringMesh.rotation.x = Math.PI / 2;
      ringMesh.position.y = height * 0.35;
      group.add(ringMesh);
      break;
    }

    case 'counter_straight': {
      // Base Casework
      const kickH = 0.1;
      const kickGeo = new THREE.BoxGeometry(width * 0.96, kickH, depth * 0.9);
      const kickMesh = new THREE.Mesh(kickGeo, metalMat);
      kickMesh.position.y = kickH / 2;
      group.add(kickMesh);

      // Main Cabinet body
      const bodyH = height - kickH - 0.05;
      const bodyGeo = new THREE.BoxGeometry(width, bodyH, depth);
      const bodyMesh = new THREE.Mesh(bodyGeo, woodMat);
      bodyMesh.position.y = kickH + bodyH / 2;
      bodyMesh.castShadow = true;
      bodyMesh.receiveShadow = true;
      group.add(bodyMesh);

      // Countertop with Overhang
      const topGeo = new THREE.BoxGeometry(width + 0.08, 0.05, depth + 0.08);
      const topMesh = new THREE.Mesh(topGeo, mat);
      topMesh.position.y = height - 0.025;
      topMesh.castShadow = true;
      group.add(topMesh);
      break;
    }

    case 'counter_corner': {
      // L-shaped counter composed of two intersecting wings
      const wingA = new THREE.BoxGeometry(width, height, depth * 0.5);
      const meshA = new THREE.Mesh(wingA, mat);
      meshA.position.set(0, height / 2, -depth * 0.25);
      meshA.castShadow = true;
      group.add(meshA);

      const wingB = new THREE.BoxGeometry(depth * 0.5, height, depth * 0.5);
      const meshB = new THREE.Mesh(wingB, mat);
      meshB.position.set(-width / 2 + depth * 0.25, height / 2, depth * 0.25);
      meshB.castShadow = true;
      group.add(meshB);
      break;
    }

    case 'lounge_booth': {
      // Plinth base
      const plinthH = 0.12;
      const plinthGeo = new THREE.BoxGeometry(width, plinthH, depth * 0.9);
      const plinthMesh = new THREE.Mesh(plinthGeo, metalMat);
      plinthMesh.position.y = plinthH / 2;
      group.add(plinthMesh);

      // Deep Seat Cushion
      const seatH = 0.35;
      const seatGeo = new THREE.BoxGeometry(width, seatH, depth * 0.65);
      const seatMesh = new THREE.Mesh(seatGeo, mat);
      seatMesh.position.set(0, plinthH + seatH / 2, depth * 0.1);
      seatMesh.castShadow = true;
      group.add(seatMesh);

      // High Vertical Backrest with Fluting
      const backH = height - plinthH;
      const backThick = depth * 0.35;
      const backGeo = new THREE.BoxGeometry(width, backH, backThick);
      const backMesh = new THREE.Mesh(backGeo, mat);
      backMesh.position.set(0, plinthH + backH / 2, -depth / 2 + backThick / 2);
      backMesh.castShadow = true;
      group.add(backMesh);
      break;
    }

    case 'acoustic_divider': {
      // Screen Felt Panel
      const panelThick = 0.04;
      const panelH = height * 0.92;
      const panelGeo = new THREE.BoxGeometry(width, panelH, panelThick);
      const panelMesh = new THREE.Mesh(panelGeo, mat);
      panelMesh.position.y = height / 2;
      panelMesh.castShadow = true;
      group.add(panelMesh);

      // Two stabilizing wooden foot trestles
      const footGeo = new THREE.BoxGeometry(0.06, 0.04, depth);
      const f1 = new THREE.Mesh(footGeo, woodMat);
      f1.position.set(width * 0.32, 0.02, 0);
      f1.castShadow = true;
      group.add(f1);

      const f2 = new THREE.Mesh(footGeo, woodMat);
      f2.position.set(-width * 0.32, 0.02, 0);
      f2.castShadow = true;
      group.add(f2);
      break;
    }

    case 'pendant_light': {
      // Dome Shade
      const shadeRadius = width / 2;
      const domeGeo = new THREE.SphereGeometry(
        shadeRadius,
        24,
        16,
        0,
        Math.PI * 2,
        0,
        Math.PI * 0.55
      );
      const domeMesh = new THREE.Mesh(domeGeo, mat);
      domeMesh.position.y = height;
      domeMesh.rotation.x = Math.PI; // open downwards
      domeMesh.castShadow = true;
      group.add(domeMesh);

      // Suspension Cable to ceiling
      const cableH = 0.8;
      const cableGeo = new THREE.CylinderGeometry(0.004, 0.004, cableH, 8);
      const cableMesh = new THREE.Mesh(cableGeo, metalMat);
      cableMesh.position.y = height + cableH / 2;
      group.add(cableMesh);

      // Interior Light Source
      const light = new THREE.PointLight(0xfff1dc, 1.2, 5);
      light.position.set(0, height - 0.05, 0);
      light.castShadow = false; // lightweight
      group.add(light);
      break;
    }

    case 'rug_rectangular': {
      const rugThick = 0.015;
      const rugGeo = new THREE.BoxGeometry(width, rugThick, depth);
      const rugMesh = new THREE.Mesh(rugGeo, mat);
      rugMesh.position.y = rugThick / 2;
      rugMesh.receiveShadow = true;
      group.add(rugMesh);
      break;
    }

    case 'rug_circular': {
      const rugThick = 0.015;
      const rugGeo = new THREE.CylinderGeometry(width / 2, width / 2, rugThick, 32);
      const rugMesh = new THREE.Mesh(rugGeo, mat);
      rugMesh.position.y = rugThick / 2;
      rugMesh.receiveShadow = true;
      group.add(rugMesh);
      break;
    }

    case 'planter_foliage': {
      // Ceramic Pot
      const potH = height * 0.4;
      const potRadius = width / 2;
      const potGeo = new THREE.CylinderGeometry(potRadius, potRadius * 0.85, potH, 24);
      const potMesh = new THREE.Mesh(potGeo, getProceduralMaterial('ceramic_white'));
      potMesh.position.y = potH / 2;
      potMesh.castShadow = true;
      group.add(potMesh);

      // Soil
      const soilGeo = new THREE.CylinderGeometry(potRadius * 0.95, potRadius * 0.95, 0.02, 16);
      const soilMesh = new THREE.Mesh(soilGeo, getProceduralMaterial('concrete'));
      soilMesh.position.y = potH - 0.01;
      group.add(soilMesh);

      // Foliage Spheres / Fronds
      const plantMat = new THREE.MeshStandardMaterial({
        color: 0x2d6a4f,
        roughness: 0.6,
      });
      const crownGeo = new THREE.DodecahedronGeometry(width * 0.55, 1);
      const crownMesh = new THREE.Mesh(crownGeo, plantMat);
      crownMesh.position.y = height * 0.72;
      crownMesh.castShadow = true;
      group.add(crownMesh);
      break;
    }

    case 'office_desk': {
      // Top
      const topThick = 0.035;
      const topGeo = new THREE.BoxGeometry(width, topThick, depth);
      const topMesh = new THREE.Mesh(topGeo, mat);
      topMesh.position.y = height - topThick / 2;
      topMesh.castShadow = true;
      group.add(topMesh);

      // Modesty panel
      const modH = height * 0.45;
      const modGeo = new THREE.BoxGeometry(width * 0.85, modH, 0.02);
      const modMesh = new THREE.Mesh(modGeo, woodMat);
      modMesh.position.set(0, height - topThick - modH / 2, -depth * 0.35);
      group.add(modMesh);

      // U-frame metal legs
      const legW = 0.04;
      const legH = height - topThick;
      const frameGeo = new THREE.BoxGeometry(legW, legH, depth * 0.85);
      const leftLeg = new THREE.Mesh(frameGeo, metalMat);
      leftLeg.position.set(-width / 2 + 0.06, legH / 2, 0);
      leftLeg.castShadow = true;
      group.add(leftLeg);

      const rightLeg = new THREE.Mesh(frameGeo, metalMat);
      rightLeg.position.set(width / 2 - 0.06, legH / 2, 0);
      rightLeg.castShadow = true;
      group.add(rightLeg);
      break;
    }

    case 'task_chair': {
      // 5-Star castor base
      const baseGeo = new THREE.CylinderGeometry(width * 0.4, width * 0.4, 0.04, 5);
      const baseMesh = new THREE.Mesh(baseGeo, metalMat);
      baseMesh.position.y = 0.06;
      group.add(baseMesh);

      // Gas lift
      const liftH = height * 0.4;
      const liftGeo = new THREE.CylinderGeometry(0.025, 0.025, liftH, 12);
      const liftMesh = new THREE.Mesh(liftGeo, metalMat);
      liftMesh.position.y = liftH / 2 + 0.06;
      group.add(liftMesh);

      // Contoured seat
      const seatH = 0.06;
      const seatGeo = new THREE.BoxGeometry(width * 0.7, seatH, depth * 0.7);
      const seatMesh = new THREE.Mesh(seatGeo, mat);
      seatMesh.position.y = liftH + 0.06 + seatH / 2;
      seatMesh.castShadow = true;
      group.add(seatMesh);

      // Mesh Backrest
      const backH = height * 0.45;
      const backGeo = new THREE.BoxGeometry(width * 0.65, backH, 0.03);
      const backMesh = new THREE.Mesh(backGeo, mat);
      backMesh.position.set(0, height - backH / 2, -depth * 0.3);
      backMesh.castShadow = true;
      group.add(backMesh);
      break;
    }

    case 'credenza_bookshelf': {
      // Box frame
      const credGeo = new THREE.BoxGeometry(width, height, depth);
      const credMesh = new THREE.Mesh(credGeo, mat);
      credMesh.position.y = height / 2;
      credMesh.castShadow = true;
      credMesh.receiveShadow = true;
      group.add(credMesh);
      break;
    }

    case 'display_showcase': {
      // Bottom opaque cabinet
      const baseH = height * 0.28;
      const baseGeo = new THREE.BoxGeometry(width, baseH, depth);
      const baseMesh = new THREE.Mesh(baseGeo, woodMat);
      baseMesh.position.y = baseH / 2;
      baseMesh.castShadow = true;
      group.add(baseMesh);

      // Upper glass display box
      const glassH = height - baseH;
      const glassGeo = new THREE.BoxGeometry(width * 0.96, glassH, depth * 0.96);
      const glassMesh = new THREE.Mesh(glassGeo, getProceduralMaterial('glass'));
      glassMesh.position.y = baseH + glassH / 2;
      group.add(glassMesh);
      break;
    }

    case 'coffee_station': {
      // Counter Base
      const baseH = height * 0.65;
      const baseGeo = new THREE.BoxGeometry(width, baseH, depth);
      const baseMesh = new THREE.Mesh(baseGeo, woodMat);
      baseMesh.position.y = baseH / 2;
      baseMesh.castShadow = true;
      group.add(baseMesh);

      // Stainless Espresso Machine on Top
      const espH = height - baseH;
      const espGeo = new THREE.BoxGeometry(width * 0.75, espH, depth * 0.7);
      const espMesh = new THREE.Mesh(espGeo, getProceduralMaterial('metal_stainless'));
      espMesh.position.set(0, baseH + espH / 2, 0);
      espMesh.castShadow = true;
      group.add(espMesh);
      break;
    }

    case 'armchair_lounge':
    default: {
      // Thick Lounge Armchair
      const seatH = height * 0.45;
      const seatGeo = new THREE.BoxGeometry(width * 0.75, 0.15, depth * 0.75);
      const seatMesh = new THREE.Mesh(seatGeo, mat);
      seatMesh.position.set(0, seatH, 0);
      seatMesh.castShadow = true;
      group.add(seatMesh);

      // Backrest
      const backH = height * 0.55;
      const backGeo = new THREE.BoxGeometry(width * 0.85, backH, 0.18);
      const backMesh = new THREE.Mesh(backGeo, mat);
      backMesh.position.set(0, height - backH / 2, -depth / 2 + 0.09);
      backMesh.castShadow = true;
      group.add(backMesh);

      // Arms
      const armW = 0.12;
      const armH = height * 0.35;
      const armGeo = new THREE.BoxGeometry(armW, armH, depth * 0.75);
      const leftArm = new THREE.Mesh(armGeo, mat);
      leftArm.position.set(-width / 2 + armW / 2, seatH + armH / 2 - 0.05, 0);
      leftArm.castShadow = true;
      group.add(leftArm);

      const rightArm = new THREE.Mesh(armGeo, mat);
      rightArm.position.set(width / 2 - armW / 2, seatH + armH / 2 - 0.05, 0);
      rightArm.castShadow = true;
      group.add(rightArm);
      break;
    }
  }

  return group;
}
