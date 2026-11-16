import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const ISLAND_CENTER = new THREE.Vector2(0, -28);
const ISLAND_COLLISION_RADIUS = 22;
const OCEAN_BOUNDARY_RADIUS = 148;
const INITIAL_BOAT_POS = { x: 0, z: 18, yaw: 0 };

const TIME_PRESETS = {
  day: {
    sky: new THREE.Color('#7ec8e3'),
    fog: new THREE.Color('#9cd7ec'),
    fogDensity: 0.0042,
    sunPos: new THREE.Vector3(58, 66, -72),
    sunColor: new THREE.Color('#fff5d6'),
    sunIntensity: 2.35,
    hemiSky: new THREE.Color('#bde8ff'),
    hemiGround: new THREE.Color('#d2b48c'),
    hemiIntensity: 1.05,
    deepOcean: new THREE.Color('#041f36'),
    midOcean: new THREE.Color('#094c6b'),
    shallowOcean: new THREE.Color('#1996ad'),
    foamColor: new THREE.Color('#ecf8ff'),
    starOpacity: 0.0,
    lanternIntensity: 0.25,
    beaconIntensity: 0.2,
    campfireIntensity: 0.8,
    exposure: 1.05,
  },
  sunset: {
    sky: new THREE.Color('#d97a54'),
    fog: new THREE.Color('#c87158'),
    fogDensity: 0.0056,
    sunPos: new THREE.Vector3(-42, 16, -98),
    sunColor: new THREE.Color('#ff9d4d'),
    sunIntensity: 2.6,
    hemiSky: new THREE.Color('#ffaf7a'),
    hemiGround: new THREE.Color('#3b2c44'),
    hemiIntensity: 0.85,
    deepOcean: new THREE.Color('#0c213d'),
    midOcean: new THREE.Color('#1a4463'),
    shallowOcean: new THREE.Color('#2c7682'),
    foamColor: new THREE.Color('#ffe0c8'),
    starOpacity: 0.28,
    lanternIntensity: 3.4,
    beaconIntensity: 2.8,
    campfireIntensity: 3.2,
    exposure: 1.0,
  },
  night: {
    sky: new THREE.Color('#071324'),
    fog: new THREE.Color('#0a192e'),
    fogDensity: 0.0062,
    sunPos: new THREE.Vector3(46, 54, -84),
    sunColor: new THREE.Color('#c7dbff'),
    sunIntensity: 0.85,
    hemiSky: new THREE.Color('#28466e'),
    hemiGround: new THREE.Color('#09131f'),
    hemiIntensity: 0.55,
    deepOcean: new THREE.Color('#031324'),
    midOcean: new THREE.Color('#082a45'),
    shallowOcean: new THREE.Color('#0e4763'),
    foamColor: new THREE.Color('#95bed9'),
    starOpacity: 0.95,
    lanternIntensity: 6.2,
    beaconIntensity: 5.5,
    campfireIntensity: 5.2,
    exposure: 1.15,
  },
};

// Layered Gerstner swells + cross wind waves + choppy crests
const GERSTNER_WAVES = [
  { dx: 0.84, dz: 0.54, amp: 0.36, wavelength: 28.0, speed: 1.18, steepness: 0.68 },
  { dx: 0.38, dz: 0.92, amp: 0.27, wavelength: 20.0, speed: 1.02, steepness: 0.62 },
  { dx: -0.56, dz: 0.83, amp: 0.21, wavelength: 15.5, speed: 1.26, steepness: 0.56 },
  { dx: 0.95, dz: -0.31, amp: 0.14, wavelength: 10.5, speed: 1.48, steepness: 0.54 },
  { dx: 0.16, dz: 0.99, amp: 0.10, wavelength: 7.6, speed: 1.72, steepness: 0.50 },
  { dx: -0.84, dz: 0.54, amp: 0.08, wavelength: 5.4, speed: 1.95, steepness: 0.46 },
  { dx: 0.68, dz: 0.73, amp: 0.052, wavelength: 4.1, speed: 2.25, steepness: 0.44 },
  { dx: -0.64, dz: -0.77, amp: 0.038, wavelength: 3.3, speed: 2.55, steepness: 0.40 },
].map((w) => {
  const len = Math.hypot(w.dx, w.dz) || 1;
  const dx = w.dx / len;
  const dz = w.dz / len;
  const k = (Math.PI * 2) / w.wavelength;
  const q = w.steepness / (k * w.amp * 5.6);
  return {
    dx,
    dz,
    amp: w.amp,
    k,
    speed: w.speed,
    steepness: w.steepness,
    qAmpDx: q * w.amp * dx,
    qAmpDz: q * w.amp * dz,
  };
});

const _waveEvalOut = { dispX: 0, dispZ: 0, height: 0, pinch: 0 };

/**
 * Evaluate layered Gerstner wave displacement, height, and crest pinch at (x, z, time).
 */
function evaluateOceanWave(x, z, time, out = _waveEvalOut) {
  const distToIsland = Math.hypot(x - ISLAND_CENTER.x, z - ISLAND_CENTER.y);
  const shoreDamp = THREE.MathUtils.smoothstep(distToIsland, 13, 29);
  const amplitudeScale = 0.18 + 0.82 * shoreDamp;

  let dispX = 0;
  let dispZ = 0;
  let height = 0;
  let pinch = 0;

  for (let i = 0; i < GERSTNER_WAVES.length; i++) {
    const w = GERSTNER_WAVES[i];
    const theta = w.k * (w.dx * x + w.dz * z) + time * w.speed;
    const cosT = Math.cos(theta);
    const sinT = Math.sin(theta);

    dispX += w.qAmpDx * cosT;
    dispZ += w.qAmpDz * cosT;
    height += w.amp * sinT;
    pinch += (w.steepness / GERSTNER_WAVES.length) * sinT;
  }

  // Fine physical surface chop detail
  const ripple =
    Math.sin(x * 0.92 + z * 0.68 + time * 2.15) * 0.026 +
    Math.cos(x * 1.35 - z * 1.12 - time * 1.85) * 0.018;

  out.dispX = dispX * amplitudeScale;
  out.dispZ = dispZ * amplitudeScale;
  out.height = (height + ripple) * amplitudeScale;
  out.pinch = pinch * amplitudeScale;
  return out;
}

/**
 * Compute wave elevation at world coordinates (x, z) for a given elapsed time.
 */
function getWaveHeight(x, z, time) {
  return evaluateOceanWave(x, z, time).height;
}

/**
 * Compute wave height and surface slopes using finite central differences.
 */
function getWaveSlope(x, z, time) {
  const eps = 0.5;
  const height = evaluateOceanWave(x, z, time).height;
  const hRight = evaluateOceanWave(x + eps, z, time).height;
  const hLeft = evaluateOceanWave(x - eps, z, time).height;
  const hFront = evaluateOceanWave(x, z + eps, time).height;
  const hBack = evaluateOceanWave(x, z - eps, time).height;

  return {
    height,
    dx: (hRight - hLeft) / (2 * eps),
    dz: (hFront - hBack) / (2 * eps),
  };
}

/**
 * Generate a seamlessly tileable procedural normal map DataTexture for ocean micro-ripples.
 */
function createWaveNormalTexture(size = 256, freqScale = 1, seed = 0) {
  const data = new Uint8Array(size * size * 4);
  const twoPi = Math.PI * 2;
  const baseHarmonics = [
    [1, 2, 0.34],
    [2, -1, 0.31],
    [3, 1, 0.25],
    [-2, 3, 0.22],
    [4, -3, 0.18],
    [1, -5, 0.15],
    [5, 2, 0.14],
    [-4, -3, 0.12],
    [6, -1, 0.10],
    [-3, 6, 0.09],
    [7, 4, 0.08],
    [-5, 6, 0.07],
  ];

  const harmonics = baseHarmonics.map(([kx, ky, amp], idx) => ({
    kx: kx * freqScale,
    ky: ky * freqScale,
    amp: amp / Math.sqrt(freqScale),
    phase: seed + idx * 1.43,
  }));

  const slopeScale = 0.068;

  for (let py = 0; py < size; py++) {
    const v = py / size;
    for (let px = 0; px < size; px++) {
      const u = px / size;
      let dHdu = 0;
      let dHdv = 0;

      for (let i = 0; i < harmonics.length; i++) {
        const h = harmonics[i];
        const theta = twoPi * (h.kx * u + h.ky * v) + h.phase;
        const cosT = Math.cos(theta) * h.amp;
        dHdu += cosT * h.kx * twoPi;
        dHdv += cosT * h.ky * twoPi;
      }

      const nx = -dHdu * slopeScale;
      const ny = -dHdv * slopeScale;
      const nz = 1.0;
      const invLen = 1 / Math.hypot(nx, ny, nz);

      const offset = (py * size + px) * 4;
      data[offset] = Math.round((nx * invLen * 0.5 + 0.5) * 255);
      data[offset + 1] = Math.round((ny * invLen * 0.5 + 0.5) * 255);
      data[offset + 2] = Math.round((nz * invLen * 0.5 + 0.5) * 255);
      data[offset + 3] = 255;
    }
  }

  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  return texture;
}

/**
 * Generate a seamlessly tileable procedural normal map DataTexture for fractured coastal rock pores and strata.
 */
function createRockNormalTexture(size = 256) {
  const heights = new Float32Array(size * size);
  const twoPi = Math.PI * 2;
  const rockHarmonics = [
    [2, 1, 0.30, 0.2],
    [-3, 2, 0.24, 1.1],
    [4, -3, 0.20, 2.3],
    [7, -5, 0.14, 0.8],
    [-9, 11, 0.10, 1.9],
    [13, 8, 0.08, 3.1],
    [-15, -12, 0.06, 0.5],
    [19, -17, 0.045, 2.7],
    [23, 21, 0.035, 1.4],
  ];

  for (let py = 0; py < size; py++) {
    const v = py / size;
    for (let px = 0; px < size; px++) {
      const u = px / size;
      // Sedimentary strata bands + sharp micro-fissure creases + mineral grain
      const strata = Math.sin(twoPi * (3 * v + 1 * u) + 0.45 * Math.sin(twoPi * (2 * u - v)));
      let detail = 0;
      for (let i = 0; i < rockHarmonics.length; i++) {
        const [kx, ky, amp, phase] = rockHarmonics[i];
        detail += Math.sin(twoPi * (kx * u + ky * v) + phase) * amp;
      }
      const crease = -Math.abs(Math.sin(twoPi * (4 * u - 3 * v) + 0.55 * detail)) * 0.42;
      heights[py * size + px] = strata * 0.34 + detail + crease;
    }
  }

  const data = new Uint8Array(size * size * 4);
  const strength = 2.6;
  for (let py = 0; py < size; py++) {
    const ym = (py - 1 + size) % size;
    const yp = (py + 1) % size;
    for (let px = 0; px < size; px++) {
      const xm = (px - 1 + size) % size;
      const xp = (px + 1) % size;
      const dHdx = (heights[py * size + xp] - heights[py * size + xm]) * 0.5 * size * 0.01;
      const dHdy = (heights[yp * size + px] - heights[ym * size + px]) * 0.5 * size * 0.01;

      const nx = -dHdx * strength;
      const ny = -dHdy * strength;
      const nz = 1.0;
      const invLen = 1 / Math.hypot(nx, ny, nz);

      const offset = (py * size + px) * 4;
      data[offset] = Math.round((nx * invLen * 0.5 + 0.5) * 255);
      data[offset + 1] = Math.round((ny * invLen * 0.5 + 0.5) * 255);
      data[offset + 2] = Math.round((nz * invLen * 0.5 + 0.5) * 255);
      data[offset + 3] = 255;
    }
  }

  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  return texture;
}

/**
 * Equip rock_cluster meshes with 3D-projected UVs and procedural normal maps while keeping GLB vertex colors.
 */
function prepareRockClusterAsset(rockAsset, rockNormalMap) {
  if (!rockAsset) return;
  rockAsset.traverse((child) => {
    if (!child.isMesh || !child.geometry) return;

    const geo = child.geometry;
    const pos = geo.attributes.position;
    if (pos) {
      const uvs = new Float32Array(pos.count * 2);
      for (let i = 0; i < pos.count; i++) {
        const vx = pos.getX(i);
        const vy = pos.getY(i);
        const vz = pos.getZ(i);
        uvs[i * 2] = (vx + vy * 0.65) * 1.6;
        uvs[i * 2 + 1] = (vz + vy * 0.65) * 1.6;
      }
      geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    }

    const isBarnacle = child.name === 'BarnacleClusters';
    child.material = new THREE.MeshStandardMaterial({
      vertexColors: Boolean(geo.attributes.color),
      normalMap: rockNormalMap,
      normalScale: new THREE.Vector2(isBarnacle ? 0.55 : 0.95, isBarnacle ? 0.55 : 0.95),
      roughness: isBarnacle ? 0.78 : 0.78,
      metalness: isBarnacle ? 0.04 : 0.06,
      envMapIntensity: isBarnacle ? 0.55 : 0.65,
      side: THREE.DoubleSide,
    });
    child.castShadow = true;
    child.receiveShadow = true;
  });
}

/**
 * Generate a seamlessly tileable procedural normal map DataTexture for beach sand grain, ripples, and soil clods.
 */
function createTerrainNormalTexture(size = 256) {
  const heights = new Float32Array(size * size);
  const twoPi = Math.PI * 2;
  const grainHarmonics = [
    [6, 4, 0.24, 0.5],
    [-8, 7, 0.20, 1.3],
    [13, 9, 0.14, 2.2],
    [-17, 14, 0.11, 0.9],
    [23, -19, 0.08, 3.1],
    [-29, 27, 0.06, 1.8],
    [37, -31, 0.045, 2.6],
  ];

  for (let py = 0; py < size; py++) {
    const v = py / size;
    for (let px = 0; px < size; px++) {
      const u = px / size;
      const windRipple = Math.sin(twoPi * (3 * u - 2 * v) + 0.45 * Math.sin(twoPi * (u + v)));
      let grain = 0;
      for (let i = 0; i < grainHarmonics.length; i++) {
        const [kx, ky, amp, phase] = grainHarmonics[i];
        grain += Math.sin(twoPi * (kx * u + ky * v) + phase) * amp;
      }
      heights[py * size + px] = windRipple * 0.22 + grain;
    }
  }

  const data = new Uint8Array(size * size * 4);
  const strength = 2.1;
  for (let py = 0; py < size; py++) {
    const ym = (py - 1 + size) % size;
    const yp = (py + 1) % size;
    for (let px = 0; px < size; px++) {
      const xm = (px - 1 + size) % size;
      const xp = (px + 1) % size;
      const dHdx = (heights[py * size + xp] - heights[py * size + xm]) * 0.5 * size * 0.01;
      const dHdy = (heights[yp * size + px] - heights[ym * size + px]) * 0.5 * size * 0.01;

      const nx = -dHdx * strength;
      const ny = -dHdy * strength;
      const nz = 1.0;
      const invLen = 1 / Math.hypot(nx, ny, nz);

      const offset = (py * size + px) * 4;
      data[offset] = Math.round((nx * invLen * 0.5 + 0.5) * 255);
      data[offset + 1] = Math.round((ny * invLen * 0.5 + 0.5) * 255);
      data[offset + 2] = Math.round((nz * invLen * 0.5 + 0.5) * 255);
      data[offset + 3] = 255;
    }
  }

  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  return texture;
}

/**
 * Configure island terrain, shells, and 3D grass tufts with tiled UVs and surface detail materials.
 */
function prepareIslandAsset(islandAsset, terrainNormalMap) {
  if (!islandAsset) return;
  islandAsset.traverse((child) => {
    if (!child.isMesh || !child.geometry) return;
    const geo = child.geometry;
    const isGrass = child.name === 'IslandGrassTufts' || child.name === 'CoastalDuneGrass';

    if (isGrass) {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: Boolean(geo.attributes.color),
        roughness: 0.50,
        metalness: 0.02,
        envMapIntensity: 0.55,
        side: THREE.DoubleSide,
      });
    } else {
      const pos = geo.attributes.position;
      if (pos) {
        const uvs = new Float32Array(pos.count * 2);
        for (let i = 0; i < pos.count; i++) {
          uvs[i * 2] = pos.getX(i) * 0.45;
          uvs[i * 2 + 1] = pos.getZ(i) * 0.45;
        }
        geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
      }
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: Boolean(geo.attributes.color),
        normalMap: terrainNormalMap,
        normalScale: new THREE.Vector2(0.72, 0.72),
        roughness: 0.82,
        metalness: 0.04,
        envMapIntensity: 0.55,
      });
    }

    child.castShadow = true;
    child.receiveShadow = true;
  });
}

/**
 * Convert a periodic height function h(u, v) in [0, 1)^2 into a seamlessly tileable normal map DataTexture.
 */
function buildPeriodicNormalTexture(size, heightFn, strength) {
  const heights = new Float32Array(size * size);
  for (let py = 0; py < size; py++) {
    const v = py / size;
    for (let px = 0; px < size; px++) {
      heights[py * size + px] = heightFn(px / size, v);
    }
  }

  const data = new Uint8Array(size * size * 4);
  for (let py = 0; py < size; py++) {
    const ym = (py - 1 + size) % size;
    const yp = (py + 1) % size;
    for (let px = 0; px < size; px++) {
      const xm = (px - 1 + size) % size;
      const xp = (px + 1) % size;
      const dHdx = (heights[py * size + xp] - heights[py * size + xm]) * 0.5 * size * 0.01;
      const dHdy = (heights[yp * size + px] - heights[ym * size + px]) * 0.5 * size * 0.01;

      const nx = -dHdx * strength;
      const ny = -dHdy * strength;
      const nz = 1.0;
      const invLen = 1 / Math.hypot(nx, ny, nz);

      const offset = (py * size + px) * 4;
      data[offset] = Math.round((nx * invLen * 0.5 + 0.5) * 255);
      data[offset + 1] = Math.round((ny * invLen * 0.5 + 0.5) * 255);
      data[offset + 2] = Math.round((nz * invLen * 0.5 + 0.5) * 255);
      data[offset + 3] = 255;
    }
  }

  const texture = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  return texture;
}

/**
 * Generate seamless wood grain and woven sail canvas normal maps for sailboat materials.
 */
function createWoodAndCanvasNormalTextures(size = 256) {
  const twoPi = Math.PI * 2;
  const woodNormalMap = buildPeriodicNormalTexture(
    size,
    (u, v) => {
      const warp = Math.sin(twoPi * (2 * u + v)) * 0.25 + Math.cos(twoPi * (3 * u - 2 * v)) * 0.14;
      const grain =
        Math.sin(twoPi * (14 * u + v + warp)) * 0.34 +
        Math.sin(twoPi * (28 * u - 2 * v + warp)) * 0.16 +
        Math.cos(twoPi * (19 * u + 7 * v)) * 0.08;
      return grain;
    },
    1.85
  );

  const canvasNormalMap = buildPeriodicNormalTexture(
    size,
    (u, v) => {
      const warpU = Math.sin(twoPi * 26 * u) * 0.32;
      const weftV = Math.sin(twoPi * 26 * v) * 0.32;
      const twill = Math.sin(twoPi * (13 * u + 13 * v)) * 0.08;
      return warpU + weftV + twill;
    },
    1.45
  );

  return { woodNormalMap, canvasNormalMap };
}

/**
 * Equip sailboat meshes with UVs, wood/canvas normal maps, metallic fittings, and lantern emission.
 */
function prepareSailboatAsset(sailboatAsset) {
  if (!sailboatAsset) return;
  const { woodNormalMap, canvasNormalMap } = createWoodAndCanvasNormalTextures(256);

  const matteTeakNames = new Set(['BoatDeck', 'CockpitFloor', 'CockpitBenches', 'BoatKeel']);
  const glossyHullNames = new Set(['BoatHull', 'LifeBuoy']);
  const brassNames = new Set(['MastHoops', 'RudderHardware', 'BowLanternFrame', 'DeckCleats']);

  sailboatAsset.traverse((child) => {
    if (!child.isMesh || !child.geometry) return;
    const geo = child.geometry;
    const hasVCol = Boolean(geo.attributes.color);

    if (child.name === 'BowLanternBulb') {
      child.material = new THREE.MeshStandardMaterial({
        color: '#ffd584',
        emissive: new THREE.Color('#ff9d2e'),
        emissiveIntensity: 0.85,
        roughness: 0.2,
        metalness: 0.0,
      });
      child.castShadow = false;
      return;
    }

    const pos = geo.attributes.position;
    const isSail = child.name === 'MainSail' || child.name === 'JibSail';
    const isSpar = child.name === 'SparsAndMast';
    if (pos) {
      const uvs = new Float32Array(pos.count * 2);
      for (let i = 0; i < pos.count; i++) {
        const vx = pos.getX(i);
        const vy = pos.getY(i);
        const vz = pos.getZ(i);
        if (isSail) {
          uvs[i * 2] = (vx + vz) * 0.72;
          uvs[i * 2 + 1] = vy * 0.72;
        } else if (isSpar) {
          uvs[i * 2] = vx * 4.0 + vz * 0.15;
          uvs[i * 2 + 1] = (vy + vz) * 0.42;
        } else {
          uvs[i * 2] = (vx + vy) * 1.35;
          uvs[i * 2 + 1] = (vz + vx * 0.25) * 0.42;
        }
      }
      geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    }

    if (isSail) {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        normalMap: canvasNormalMap,
        normalScale: new THREE.Vector2(0.45, 0.45),
        roughness: 0.62,
        metalness: 0.02,
        envMapIntensity: 0.45,
        side: THREE.DoubleSide,
      });
    } else if (child.name === 'BowAnchor') {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        roughness: 0.52,
        metalness: 0.82,
        envMapIntensity: 0.9,
      });
    } else if (brassNames.has(child.name)) {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        roughness: 0.26,
        metalness: 0.86,
        envMapIntensity: 1.0,
      });
    } else if (child.name === 'PulleyBlocks') {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        normalMap: woodNormalMap,
        normalScale: new THREE.Vector2(0.35, 0.35),
        roughness: 0.42,
        metalness: 0.35,
        envMapIntensity: 0.8,
      });
    } else if (child.name === 'RiggingLines') {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        normalMap: canvasNormalMap,
        normalScale: new THREE.Vector2(0.35, 0.35),
        roughness: 0.84,
        metalness: 0.08,
      });
    } else if (glossyHullNames.has(child.name)) {
      child.material = new THREE.MeshPhysicalMaterial({
        vertexColors: hasVCol,
        normalMap: woodNormalMap,
        normalScale: new THREE.Vector2(0.42, 0.42),
        roughness: 0.3,
        metalness: 0.05,
        clearcoat: 0.42,
        clearcoatRoughness: 0.14,
        envMapIntensity: 0.78,
        side: THREE.DoubleSide,
      });
    } else if (matteTeakNames.has(child.name)) {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        normalMap: woodNormalMap,
        normalScale: new THREE.Vector2(0.65, 0.65),
        roughness: 0.68,
        metalness: 0.04,
        envMapIntensity: 0.55,
      });
    } else {
      child.material = new THREE.MeshPhysicalMaterial({
        vertexColors: hasVCol,
        normalMap: woodNormalMap,
        normalScale: new THREE.Vector2(0.55, 0.55),
        roughness: 0.38,
        metalness: 0.05,
        clearcoat: 0.28,
        clearcoatRoughness: 0.16,
        envMapIntensity: 0.68,
        side: THREE.DoubleSide,
      });
    }

    child.castShadow = true;
    child.receiveShadow = true;
  });
}

/**
 * Create a depth-only occluder matching the sailboat hull volume and sheer cap so water never clips inside.
 */
function createHullWaterMask() {
  const hullStations = [
    [-3.05, 0.90, 0.74, -0.16],
    [-2.10, 1.14, 0.69, -0.35],
    [-0.80, 1.26, 0.67, -0.44],
    [0.60, 1.17, 0.69, -0.42],
    [1.90, 0.86, 0.75, -0.30],
    [2.85, 0.44, 0.88, -0.10],
    [3.58, 0.04, 1.04, 0.30],
  ];

  const evalStation = (vT) => {
    const scaled = THREE.MathUtils.clamp(vT, 0, 1) * (hullStations.length - 1);
    const idx = Math.min(hullStations.length - 2, Math.floor(scaled));
    const frac = scaled - idx;
    const fracS = frac * frac * (3 - 2 * frac);
    const a = hullStations[idx];
    const b = hullStations[idx + 1];
    return [
      a[0] + (b[0] - a[0]) * fracS,
      a[1] + (b[1] - a[1]) * fracS,
      a[2] + (b[2] - a[2]) * fracS,
      a[3] + (b[3] - a[3]) * fracS,
    ];
  };

  const slices = 24;
  const uSegs = 12;
  const ringVerts = uSegs + 1;
  const positions = [];
  const indices = [];

  for (let i = 0; i <= slices; i++) {
    const vT = 0.002 + (i / slices) * 0.996;
    const [yBlender, halfBeam, sheerZ, keelZ] = evalStation(vT);
    const topCapY = sheerZ - 0.03;

    for (let k = 0; k <= uSegs; k++) {
      const tParam = -1 + (k / uSegs) * 2;
      const u = Math.abs(tParam);
      let x = Math.sign(tParam) * halfBeam * Math.sin(u * Math.PI * 0.5);
      if (u > 0.7) {
        x *= 1 + 0.055 * (u - 0.7);
      }
      const hullZ = keelZ + (sheerZ - keelZ) * Math.pow(u, 1.65);
      const yThree = k === 0 || k === uSegs ? topCapY : Math.min(topCapY, hullZ + 0.015);
      positions.push(x * 0.985, yThree, -yBlender);
    }
  }

  for (let i = 0; i < slices; i++) {
    const r0 = i * ringVerts;
    const r1 = (i + 1) * ringVerts;
    for (let k = 0; k < uSegs; k++) {
      indices.push(r0 + k, r1 + k, r1 + k + 1);
      indices.push(r0 + k, r1 + k + 1, r0 + k + 1);
    }
    // Seal sheer-level deck/cockpit opening between port (k=0) and starboard (k=uSegs)
    indices.push(r0 + uSegs, r1 + uSegs, r1);
    indices.push(r0 + uSegs, r1, r0);
  }

  // Seal stern (i=0) and bow (i=slices) cross-section caps
  const sternBase = 0;
  const bowBase = slices * ringVerts;
  for (let k = 1; k < uSegs; k++) {
    indices.push(sternBase, sternBase + k + 1, sternBase + k);
    indices.push(bowBase, bowBase + k, bowBase + k + 1);
  }

  const maskGeo = new THREE.BufferGeometry();
  maskGeo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  maskGeo.setIndex(indices);
  maskGeo.computeVertexNormals();

  const maskMat = new THREE.MeshBasicMaterial({
    colorWrite: false,
    depthWrite: true,
    depthTest: true,
    side: THREE.DoubleSide,
  });

  const maskMesh = new THREE.Mesh(maskGeo, maskMat);
  maskMesh.name = 'HullWaterMask';
  maskMesh.renderOrder = 1;
  maskMesh.castShadow = false;
  maskMesh.receiveShadow = false;
  return maskMesh;
}

/**
 * Equip lighthouse.glb meshes with cylindrical masonry UVs, stone/copper/iron PBR materials,
 * glowing internal Fresnel optic, and transparent lantern glass.
 */
function prepareLighthouseAsset(lighthouseAsset) {
  if (!lighthouseAsset) return;
  const twoPi = Math.PI * 2;
  const masonryNormalMap = buildPeriodicNormalTexture(
    256,
    (u, v) => {
      const course = -Math.pow(Math.abs(Math.sin(twoPi * 6 * v)), 18) * 0.45;
      const grain =
        Math.sin(twoPi * (7 * u + 3 * v)) * 0.22 +
        Math.cos(twoPi * (13 * u - 11 * v)) * 0.16 +
        Math.sin(twoPi * (23 * u + 19 * v)) * 0.11 +
        Math.cos(twoPi * (37 * u - 29 * v)) * 0.07;
      return course + grain;
    },
    1.75
  );

  const stoneNames = new Set(['LHFoundation', 'LHGalleryAndCorbels', 'LHDoorAndWindows']);
  const ironNames = new Set(['LHRailing', 'LHLanternRoomFrame']);

  lighthouseAsset.traverse((child) => {
    if (!child.isMesh || !child.geometry) return;
    const geo = child.geometry;
    const hasVCol = Boolean(geo.attributes.color);

    if (child.name === 'LighthouseGlass') {
      child.material = new THREE.MeshPhysicalMaterial({
        color: '#e8f4fb',
        transparent: true,
        opacity: 0.32,
        roughness: 0.08,
        metalness: 0.05,
        transmission: 0.45,
        clearcoat: 1.0,
        clearcoatRoughness: 0.06,
        emissive: new THREE.Color('#ffcf70'),
        emissiveIntensity: 0.25,
        depthWrite: false,
        side: THREE.DoubleSide,
      });
      child.castShadow = false;
      child.receiveShadow = false;
      return;
    }

    if (child.name === 'LHFresnelOptic') {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        roughness: 0.16,
        metalness: 0.32,
        emissive: new THREE.Color('#ffbd4a'),
        emissiveIntensity: 1.4,
        envMapIntensity: 1.2,
      });
      child.castShadow = false;
      child.receiveShadow = false;
      return;
    }

    const pos = geo.attributes.position;
    if (pos) {
      const uvs = new Float32Array(pos.count * 2);
      for (let i = 0; i < pos.count; i++) {
        const vx = pos.getX(i);
        const vy = pos.getY(i);
        const vz = pos.getZ(i);
        uvs[i * 2] = (vx + vz) * 0.44;
        uvs[i * 2 + 1] = vy * 0.46;
      }
      geo.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    }

    if (ironNames.has(child.name)) {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        roughness: 0.42,
        metalness: 0.78,
        envMapIntensity: 0.95,
      });
    } else if (child.name === 'LHCupolaAndVane') {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        normalMap: masonryNormalMap,
        normalScale: new THREE.Vector2(0.22, 0.22),
        roughness: 0.42,
        metalness: 0.55,
        envMapIntensity: 0.95,
      });
    } else if (stoneNames.has(child.name)) {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        normalMap: masonryNormalMap,
        normalScale: new THREE.Vector2(0.74, 0.74),
        roughness: 0.88,
        metalness: 0.04,
        envMapIntensity: 0.52,
      });
    } else {
      child.material = new THREE.MeshStandardMaterial({
        vertexColors: hasVCol,
        normalMap: masonryNormalMap,
        normalScale: new THREE.Vector2(0.56, 0.56),
        roughness: 0.72,
        metalness: 0.04,
        envMapIntensity: 0.58,
      });
    }

    child.castShadow = true;
    child.receiveShadow = true;
  });
}

/**
 * Create a soft volumetric light beam cone with smooth axial distance falloff and silhouette edge fade.
 */
function createSoftBeamCone(radius, length, radialSegs, heightSegs, baseColorHex, baseOpacity) {
  const startZ = 0.34;
  const geo = new THREE.CylinderGeometry(0.22, radius, length, radialSegs, heightSegs, true);
  geo.translate(0, -length * 0.5, 0);
  geo.rotateX(-Math.PI * 0.5);
  geo.translate(0, 0, startZ);

  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  for (let i = 0; i < pos.count; i++) {
    const v = THREE.MathUtils.clamp((pos.getZ(i) - startZ) / length, 0, 1);
    const alpha = Math.pow(1 - v, 1.85) * THREE.MathUtils.smoothstep(v, 0.0, 0.09);
    colors[i * 3] = alpha;
    colors[i * 3 + 1] = alpha;
    colors[i * 3 + 2] = alpha;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(baseColorHex) },
      uOpacity: { value: baseOpacity },
      uTime: { value: 0 },
    },
    vertexShader: `
      attribute vec3 color;
      varying float vFalloff;
      varying vec3 vViewPos;
      varying vec3 vViewNormal;
      varying vec2 vBeamUv;
      void main() {
        vFalloff = color.r;
        vBeamUv = uv;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        vViewPos = -mvPosition.xyz;
        vViewNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uOpacity;
      uniform float uTime;
      varying float vFalloff;
      varying vec3 vViewPos;
      varying vec3 vViewNormal;
      varying vec2 vBeamUv;
      void main() {
        vec3 N = normalize(vViewNormal);
        vec3 V = normalize(vViewPos);
        float silhouette = pow(abs(dot(V, N)), 1.65);
        float mist = 0.88 + 0.12 * sin(vBeamUv.y * 14.0 - uTime * 1.3 + sin(vBeamUv.x * 6.28318) * 2.0);
        float alpha = clamp(uOpacity * vFalloff * silhouette * mist, 0.0, 1.0);
        gl_FragColor = vec4(uColor, alpha);
      }
    `,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });

  const mesh = new THREE.Mesh(geo, mat);
  mesh.frustumCulled = false;
  mesh.renderOrder = 4;
  mesh.userData = { baseOpacity, kind: 'cone' };
  return mesh;
}

/**
 * Create a soft additive radial glow / star-glint disc for lighthouse Fresnel lens apertures.
 */
function createLensHaloDisc(size, colorHex, baseOpacity) {
  const geo = new THREE.PlaneGeometry(size, size);
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(colorHex) },
      uOpacity: { value: baseOpacity },
    },
    vertexShader: `
      varying vec2 vUv;
      void main() {
        vUv = uv * 2.0 - 1.0;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform vec3 uColor;
      uniform float uOpacity;
      varying vec2 vUv;
      void main() {
        float r = length(vUv);
        float core = exp(-r * r * 5.2);
        float halo = pow(max(0.0, 1.0 - r), 2.8) * 0.65;
        float rays = exp(-abs(vUv.x) * 14.0) * exp(-abs(vUv.y) * 2.4) * 0.45
                   + exp(-abs(vUv.y) * 14.0) * exp(-abs(vUv.x) * 2.4) * 0.35;
        float alpha = clamp((core + halo + rays) * step(r, 1.0) * uOpacity, 0.0, 1.0);
        gl_FragColor = vec4(uColor, alpha);
      }
    `,
    transparent: true,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    side: THREE.DoubleSide,
  });

  const mesh = new THREE.Mesh(geo, mat);
  mesh.frustumCulled = false;
  mesh.renderOrder = 4;
  mesh.userData = { baseOpacity, kind: 'halo' };
  return mesh;
}

/**
 * Compute natural island elevation at local island coordinates (lx, lz).
 */
function getIslandElevation(lx, lz) {
  const coveFactor = lz > 4 ? Math.max(0, (lz - 4) * 0.25) : 0;
  const effectiveDist = Math.hypot(lx * 0.95, lz * 1.05 + coveFactor);
  const base = Math.max(0, 1 - effectiveDist / 22.5);
  const hill = Math.pow(base, 1.55) * 5.2;
  const ridge = Math.sin(lx * 0.22) * Math.cos(lz * 0.19) * 0.35 * base;
  return hill + ridge - 1.15;
}

/**
 * Load all Blender-exported GLB assets in parallel.
 */
async function loadBlenderAssets() {
  const loader = new GLTFLoader();
  const assetNames = [
    'sailboat',
    'island',
    'palm_tree',
    'pier',
    'lighthouse',
    'rock_cluster',
    'beach_set',
    'campfire',
    'seagull',
    'ocean',
    'person',
  ];

  const loadOne = (name) =>
    new Promise((resolve, reject) => {
      loader.load(
        `./assets/models/${name}.glb?v=5`,
        (gltf) => {
          gltf.scene.traverse((child) => {
            if (child.isMesh) {
              child.castShadow = true;
              child.receiveShadow = true;
              if (child.isSkinnedMesh) {
                child.frustumCulled = false;
              }
            }
          });
          resolve([name, gltf.scene]);
        },
        undefined,
        reject
      );
    });

  const entries = await Promise.all(assetNames.map(loadOne));
  return Object.fromEntries(entries);
}

/**
 * Create trailing water wake meshes attached behind the sailboat stern.
 */
function createWakeGroup() {
  const wakeGroup = new THREE.Group();
  const wakeMat = new THREE.MeshBasicMaterial({
    color: '#ffffff',
    transparent: true,
    opacity: 0.45,
    side: THREE.DoubleSide,
    depthWrite: false,
  });

  const leftWake = new THREE.Mesh(new THREE.PlaneGeometry(0.65, 4.8), wakeMat.clone());
  leftWake.rotation.x = -Math.PI / 2;
  leftWake.rotation.z = -0.22;
  leftWake.position.set(-0.95, 0.16, 5.4);
  wakeGroup.add(leftWake);

  const rightWake = new THREE.Mesh(new THREE.PlaneGeometry(0.65, 4.8), wakeMat.clone());
  rightWake.rotation.x = -Math.PI / 2;
  rightWake.rotation.z = 0.22;
  rightWake.position.set(0.95, 0.16, 5.4);
  wakeGroup.add(rightWake);

  const centerWake = new THREE.Mesh(new THREE.RingGeometry(0.45, 0.85, 16), wakeMat.clone());
  centerWake.rotation.x = -Math.PI / 2;
  centerWake.position.set(0, 0.15, 3.6);
  wakeGroup.add(centerWake);

  return { wakeGroup, wakeMeshes: [leftWake, rightWake, centerWake] };
}

/**
 * Pose person.glb in a seated pier fishing activity with curved rod, bucket, dynamic line, and wave-bobbing float.
 */
function createPierFisher(personAsset, scene) {
  const fisherGroup = new THREE.Group();
  // Seat thighs flush on west deck planks (y = 1.215m) with knees & shins overhanging over water
  fisherGroup.position.set(-1.22, 0.46, 1.65);
  fisherGroup.rotation.y = -Math.PI * 0.42;
  scene.add(fisherGroup);

  const bones = {};
  if (personAsset) {
    personAsset.traverse((child) => {
      if (child.isMesh) {
        child.castShadow = true;
        child.receiveShadow = true;
        child.frustumCulled = false;
      }
      if (child.isBone) {
        bones[child.name] = child;
      }
    });
    fisherGroup.add(personAsset);
  }

  const getBone = (name) => bones[name] || bones[name.replace(/\./g, '')];

  // Blender-verified seated fishing pose deltas (applied on top of glTF rest quaternions)
  const poseDeltas = {
    Spine: [0.0498, 0.0, 0.0, 0.9988],
    Chest: [0.0197, 0.0, 0.0, 0.9998],
    Head: [0.0195, 0.0, 0.0, 0.9998],
    'Thigh.L': [-0.6714, 0.0, -0.064, 0.7383],
    'Shin.L': [0.5975, 0.0, 0.0418, 0.8008],
    'Foot.L': [0.12, 0.0, 0.0, 0.9928],
    'Thigh.R': [-0.6714, 0.0, 0.064, 0.7383],
    'Shin.R': [0.5975, 0.0, -0.0418, 0.8008],
    'Foot.R': [0.12, 0.0, 0.0, 0.9928],
    'UpperArm.L': [-0.4377, 0.0, 0.0395, 0.8983],
    'Forearm.L': [-0.3946, 0.0, -0.0378, 0.9181],
    'UpperArm.R': [-0.484, 0.0, 0.0161, 0.8749],
    'Forearm.R': [-0.3812, 0.0, 0.0565, 0.9228],
  };

  const baseQuats = {};
  for (const [bName, [qx, qy, qz, qw]] of Object.entries(poseDeltas)) {
    const bone = getBone(bName);
    if (bone) {
      bone.quaternion.multiply(new THREE.Quaternion(qx, qy, qz, qw));
      baseQuats[bName] = bone.quaternion.clone();
    }
  }

  // Fishing Rod & Spinning Reel held at hands front-chest position (+Z forward in Y-up)
  const rodPivot = new THREE.Group();
  rodPivot.position.set(0.0, 1.11, 0.44);
  fisherGroup.add(rodPivot);

  const corkMat = new THREE.MeshStandardMaterial({ color: '#b88652', roughness: 0.85 });
  const rodMat = new THREE.MeshStandardMaterial({ color: '#2b3440', roughness: 0.42, metalness: 0.35 });
  const accentMat = new THREE.MeshStandardMaterial({ color: '#d4a13e', roughness: 0.3, metalness: 0.75 });
  const metalMat = new THREE.MeshStandardMaterial({ color: '#94a3b8', roughness: 0.28, metalness: 0.82 });

  const handle = new THREE.Mesh(new THREE.CylinderGeometry(0.018, 0.02, 0.38, 10), corkMat);
  handle.rotation.x = Math.PI * 0.44;
  handle.position.set(0.0, -0.02, 0.02);
  handle.castShadow = true;
  rodPivot.add(handle);

  const reelSeat = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.08, 10), accentMat);
  reelSeat.rotation.x = Math.PI * 0.44;
  reelSeat.position.set(0.0, 0.0, 0.10);
  rodPivot.add(reelSeat);

  const reelSpool = new THREE.Mesh(new THREE.CylinderGeometry(0.032, 0.032, 0.045, 12), metalMat);
  reelSpool.rotation.z = Math.PI / 2;
  reelSpool.position.set(0.0, -0.065, 0.11);
  rodPivot.add(reelSpool);

  const reelStem = new THREE.Mesh(new THREE.BoxGeometry(0.014, 0.055, 0.018), metalMat);
  reelStem.position.set(0.0, -0.032, 0.105);
  rodPivot.add(reelStem);

  // Gracefully arched multi-segment fishing pole
  const rodCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0.0, 0.02, 0.18),
    new THREE.Vector3(0.0, 0.42, 0.72),
    new THREE.Vector3(0.0, 0.82, 1.38),
    new THREE.Vector3(0.0, 1.12, 1.98),
    new THREE.Vector3(0.0, 1.24, 2.48),
    new THREE.Vector3(0.0, 1.16, 2.82),
  ]);

  const segCount = 14;
  const rodPoints = rodCurve.getPoints(segCount);
  const upAxis = new THREE.Vector3(0, 1, 0);
  for (let i = 0; i < segCount; i++) {
    const pA = rodPoints[i];
    const pB = rodPoints[i + 1];
    const dir = new THREE.Vector3().subVectors(pB, pA);
    const len = dir.length();
    const rA = THREE.MathUtils.lerp(0.016, 0.005, i / segCount);
    const rB = THREE.MathUtils.lerp(0.016, 0.005, (i + 1) / segCount);

    const seg = new THREE.Mesh(new THREE.CylinderGeometry(rB, rA, len + 0.01, 8), rodMat);
    seg.position.copy(pA).addScaledVector(dir, 0.5);
    seg.quaternion.setFromUnitVectors(upAxis, dir.clone().normalize());
    seg.castShadow = true;
    rodPivot.add(seg);

    if (i === 3 || i === 6 || i === 9 || i === 12) {
      const guide = new THREE.Mesh(new THREE.TorusGeometry(rA + 0.008, 0.0025, 6, 10), metalMat);
      guide.position.copy(pB).add(new THREE.Vector3(0, -0.012, 0));
      rodPivot.add(guide);
    }
  }

  const rodTipObj = new THREE.Object3D();
  rodTipObj.position.copy(rodPoints[rodPoints.length - 1]);
  rodPivot.add(rodTipObj);

  // Coastal Fishing Bucket resting on pier deck planks beside angler
  const bucketGroup = new THREE.Group();
  bucketGroup.position.set(-0.84, 1.215, 1.02);
  scene.add(bucketGroup);

  const bucketBody = new THREE.Mesh(
    new THREE.CylinderGeometry(0.18, 0.14, 0.30, 16, 1, false),
    new THREE.MeshStandardMaterial({ color: '#3b6d8c', roughness: 0.62 })
  );
  bucketBody.position.y = 0.15;
  bucketBody.castShadow = true;
  bucketBody.receiveShadow = true;
  bucketGroup.add(bucketBody);

  const bucketRim = new THREE.Mesh(new THREE.TorusGeometry(0.182, 0.012, 8, 20), metalMat);
  bucketRim.rotation.x = Math.PI / 2;
  bucketRim.position.y = 0.30;
  bucketGroup.add(bucketRim);

  const bucketWater = new THREE.Mesh(
    new THREE.CircleGeometry(0.162, 16),
    new THREE.MeshStandardMaterial({ color: '#0f5c78', roughness: 0.18 })
  );
  bucketWater.rotation.x = -Math.PI / 2;
  bucketWater.position.y = 0.255;
  bucketGroup.add(bucketWater);

  const fishTail = new THREE.Mesh(
    new THREE.ConeGeometry(0.045, 0.12, 6),
    new THREE.MeshStandardMaterial({ color: '#9cb8cc', roughness: 0.32, metalness: 0.55 })
  );
  fishTail.position.set(0.05, 0.29, -0.04);
  fishTail.rotation.set(0.35, 0.4, -0.45);
  bucketGroup.add(fishTail);

  const wireHandle = new THREE.Mesh(
    new THREE.TorusGeometry(0.19, 0.006, 6, 18, Math.PI),
    metalMat
  );
  wireHandle.position.set(0, 0.29, 0);
  wireHandle.rotation.z = Math.PI;
  wireHandle.rotation.y = 0.4;
  wireHandle.rotation.x = 0.55;
  bucketGroup.add(wireHandle);

  // Red-white fishing bobber floating in bay water & concentric surface ripples
  const bobberBaseX = -4.25;
  const bobberBaseZ = 2.48;
  const bobberGroup = new THREE.Group();
  bobberGroup.position.set(bobberBaseX, 0, bobberBaseZ);
  scene.add(bobberGroup);

  const bobRed = new THREE.Mesh(
    new THREE.SphereGeometry(0.062, 14, 10, 0, Math.PI * 2, 0, Math.PI * 0.5),
    new THREE.MeshStandardMaterial({ color: '#dc2626', roughness: 0.32 })
  );
  bobRed.castShadow = true;
  bobberGroup.add(bobRed);

  const bobWhite = new THREE.Mesh(
    new THREE.SphereGeometry(0.062, 14, 10, 0, Math.PI * 2, Math.PI * 0.5, Math.PI * 0.5),
    new THREE.MeshStandardMaterial({ color: '#f8fafc', roughness: 0.35 })
  );
  bobberGroup.add(bobWhite);

  const bobStem = new THREE.Mesh(
    new THREE.CylinderGeometry(0.007, 0.01, 0.16, 8),
    new THREE.MeshStandardMaterial({ color: '#f8fafc', roughness: 0.4 })
  );
  bobStem.position.y = 0.08;
  bobberGroup.add(bobStem);

  const bobberLineAnchor = new THREE.Object3D();
  bobberLineAnchor.position.set(0, 0.15, 0);
  bobberGroup.add(bobberLineAnchor);

  const rippleMatOuter = new THREE.MeshBasicMaterial({
    color: '#eef9ff',
    transparent: true,
    opacity: 0.42,
    side: THREE.DoubleSide,
    depthWrite: false,
  });
  const rippleMatInner = rippleMatOuter.clone();
  const rippleOuter = new THREE.Mesh(new THREE.RingGeometry(0.14, 0.20, 24), rippleMatOuter);
  rippleOuter.rotation.x = -Math.PI / 2;
  const rippleInner = new THREE.Mesh(new THREE.RingGeometry(0.08, 0.12, 24), rippleMatInner);
  rippleInner.rotation.x = -Math.PI / 2;
  const bobberRipple = new THREE.Group();
  bobberRipple.add(rippleOuter, rippleInner);
  bobberRipple.position.set(bobberBaseX, 0.04, bobberBaseZ);
  scene.add(bobberRipple);

  // Dynamic Catenary Fishing Line connecting rodTipObj -> bobberLineAnchor
  const lineSegments = 17;
  const linePositions = new Float32Array((lineSegments + 1) * 3);
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute('position', new THREE.BufferAttribute(linePositions, 3));
  const lineMat = new THREE.LineBasicMaterial({ color: '#e2f1ff', transparent: true, opacity: 0.8 });
  const fishingLine = new THREE.Line(lineGeo, lineMat);
  fishingLine.frustumCulled = false;
  scene.add(fishingLine);

  const tmpTipWorld = new THREE.Vector3();
  const tmpBobWorld = new THREE.Vector3();
  const rotTemp = new THREE.Quaternion();
  const eulerTemp = new THREE.Euler();

  function applyDelta(bName, rx, ry, rz) {
    const bone = getBone(bName);
    const baseQ = baseQuats[bName];
    if (!bone || !baseQ) return;
    eulerTemp.set(rx, ry, rz, 'XYZ');
    rotTemp.setFromEuler(eulerTemp);
    bone.quaternion.copy(baseQ).multiply(rotTemp);
  }

  return {
    update(elapsed) {
      // Periodic gentle nibble pulls
      const biteWave = Math.sin(elapsed * 1.9) * Math.sin(elapsed * 0.65);
      const nibble = Math.pow(Math.max(0, biteWave), 4);

      // Relaxed alternating leg swing + upper body subtle casting/tug response + head glance
      const legSwing = Math.sin(elapsed * 1.35) * 0.09;
      applyDelta('Shin.L', legSwing, 0, 0);
      applyDelta('Shin.R', -legSwing, 0, 0);
      applyDelta('Head', 0.04 + nibble * 0.06, Math.sin(elapsed * 0.45) * 0.1, 0);

      const rodTug = nibble * 0.12 - Math.sin(elapsed * 1.1) * 0.025;
      applyDelta('Spine', rodTug * 0.35, 0, 0);
      applyDelta('Chest', rodTug * 0.45, 0, 0);
      applyDelta('UpperArm.L', -rodTug * 0.55, 0, 0);
      applyDelta('UpperArm.R', -rodTug * 0.55, 0, 0);

      rodPivot.rotation.x = -rodTug * 0.65;

      // Bobber floats on ocean waves and dips sharply when nibbled
      const waveY = getWaveHeight(bobberBaseX, bobberBaseZ, elapsed);
      bobberGroup.position.set(
        bobberBaseX + Math.sin(elapsed * 1.4) * 0.03,
        waveY - nibble * 0.16,
        bobberBaseZ + Math.cos(elapsed * 1.1) * 0.03
      );
      bobberGroup.rotation.z = Math.sin(elapsed * 2.1) * 0.12;
      bobberGroup.rotation.x = Math.cos(elapsed * 1.7) * 0.1;

      const rPhase1 = (elapsed * 0.7) % 1;
      const rPhase2 = (elapsed * 0.7 + 0.5) % 1;
      bobberRipple.position.set(bobberGroup.position.x, waveY + 0.04, bobberGroup.position.z);
      rippleOuter.scale.setScalar(1.0 + rPhase1 * 2.2 + nibble * 0.8);
      rippleMatOuter.opacity = (1 - rPhase1) * (0.45 + nibble * 0.35);
      rippleInner.scale.setScalar(1.0 + rPhase2 * 1.7);
      rippleMatInner.opacity = (1 - rPhase2) * (0.38 + nibble * 0.3);

      // Sync fishing line geometry between world rod tip and bobber antenna
      fisherGroup.updateMatrixWorld(true);
      bobberGroup.updateMatrixWorld(true);
      rodTipObj.getWorldPosition(tmpTipWorld);
      bobberLineAnchor.getWorldPosition(tmpBobWorld);

      const sagAmount = 0.22 - nibble * 0.14;
      for (let i = 0; i <= lineSegments; i++) {
        const t = i / lineSegments;
        const ix = i * 3;
        linePositions[ix] = THREE.MathUtils.lerp(tmpTipWorld.x, tmpBobWorld.x, t);
        linePositions[ix + 1] =
          THREE.MathUtils.lerp(tmpTipWorld.y, tmpBobWorld.y, t) - Math.sin(t * Math.PI) * sagAmount;
        linePositions[ix + 2] = THREE.MathUtils.lerp(tmpTipWorld.z, tmpBobWorld.z, t);
      }
      lineGeo.attributes.position.needsUpdate = true;
    },
  };
}

async function init() {
  const canvas = document.getElementById('ocean-canvas');
  const speedEl = document.getElementById('speed-value');
  const headingEl = document.getElementById('heading-value');
  const zoneEl = document.getElementById('zone-value');
  const resetBtn = document.getElementById('reset-boat-btn');
  const timeRadios = document.querySelectorAll('input[name="time-of-day"]');
  const cameraRadios = document.querySelectorAll('input[name="camera-mode"]');
  const steerButtons = document.querySelectorAll('.steer-btn[data-control]');

  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: 'high-performance',
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = TIME_PRESETS.day.exposure;

  const scene = new THREE.Scene();
  scene.background = TIME_PRESETS.day.sky.clone();
  scene.fog = new THREE.FogExp2(TIME_PRESETS.day.fog.getHex(), TIME_PRESETS.day.fogDensity);

  const camera = new THREE.PerspectiveCamera(52, window.innerWidth / window.innerHeight, 0.5, 520);
  camera.position.set(-18, 15, 43);

  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.maxPolarAngle = Math.PI * 0.485;
  controls.minDistance = 8;
  controls.maxDistance = 140;
  controls.target.set(0, 1.5, -5);
  controls.update();

  // Lighting
  const hemiLight = new THREE.HemisphereLight(
    TIME_PRESETS.day.hemiSky,
    TIME_PRESETS.day.hemiGround,
    TIME_PRESETS.day.hemiIntensity
  );
  scene.add(hemiLight);

  const dirLight = new THREE.DirectionalLight(
    TIME_PRESETS.day.sunColor,
    TIME_PRESETS.day.sunIntensity
  );
  dirLight.position.copy(TIME_PRESETS.day.sunPos);
  dirLight.castShadow = true;
  dirLight.shadow.mapSize.set(2048, 2048);
  dirLight.shadow.camera.near = 10;
  dirLight.shadow.camera.far = 220;
  const shadowBounds = 65;
  dirLight.shadow.camera.left = -shadowBounds;
  dirLight.shadow.camera.right = shadowBounds;
  dirLight.shadow.camera.top = shadowBounds;
  dirLight.shadow.camera.bottom = -shadowBounds;
  dirLight.shadow.bias = -0.0006;
  scene.add(dirLight);

  // Celestial orb (sun / moon)
  const sunOrbMat = new THREE.MeshBasicMaterial({ color: '#fff2be' });
  const sunOrb = new THREE.Mesh(new THREE.SphereGeometry(6.5, 24, 24), sunOrbMat);
  sunOrb.position.copy(TIME_PRESETS.day.sunPos).multiplyScalar(1.65);
  scene.add(sunOrb);

  // Starfield for dusk & night
  const starCount = 900;
  const starPositions = new Float32Array(starCount * 3);
  for (let i = 0; i < starCount; i++) {
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.random() * Math.PI * 0.44;
    const radius = 210 + Math.random() * 45;
    starPositions[i * 3] = Math.sin(phi) * Math.cos(theta) * radius;
    starPositions[i * 3 + 1] = Math.cos(phi) * radius + 12;
    starPositions[i * 3 + 2] = Math.sin(phi) * Math.sin(theta) * radius;
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
  const starMat = new THREE.PointsMaterial({
    color: '#e2eeff',
    size: 1.35,
    transparent: true,
    opacity: 0,
    depthWrite: false,
  });
  const stars = new THREE.Points(starGeo, starMat);
  scene.add(stars);

  // Load Blender 3D Models (including sculpted OceanSurface & OceanSeabed from ocean.glb)
  const assets = await loadBlenderAssets();

  // Dynamic Realistic Ocean Mesh from ocean.glb
  const waveNormalMap = createWaveNormalTexture(256, 1, 0.4);
  const capillaryNormalMap = createWaveNormalTexture(256, 2, 4.7);

  const oceanAsset = assets.ocean;
  const loadedSeabed = oceanAsset ? oceanAsset.getObjectByName('OceanSeabed') : null;
  if (loadedSeabed) {
    loadedSeabed.scale.set(4.0, 1.0, 4.0);
    loadedSeabed.position.set(0, -0.5, 0);
    loadedSeabed.castShadow = false;
    loadedSeabed.receiveShadow = true;
    scene.add(loadedSeabed);
  }

  const loadedOcean = oceanAsset ? oceanAsset.getObjectByName('OceanSurface') : null;
  let oceanGeo;
  if (loadedOcean && loadedOcean.isMesh && loadedOcean.geometry) {
    oceanGeo = loadedOcean.geometry;
  } else {
    oceanGeo = new THREE.PlaneGeometry(360, 360, 180, 180);
    oceanGeo.rotateX(-Math.PI / 2);
  }

  const oceanHorizScale = loadedOcean ? 4.0 : 1.0;
  const posAttr = oceanGeo.attributes.position;
  const oceanVertexCount = posAttr.count;
  const oceanRestX = new Float32Array(oceanVertexCount);
  const oceanRestZ = new Float32Array(oceanVertexCount);
  const oceanUVs = new Float32Array(oceanVertexCount * 2);
  const oceanColors = new Float32Array(oceanVertexCount * 3);

  for (let i = 0; i < oceanVertexCount; i++) {
    const rx = posAttr.getX(i) * oceanHorizScale;
    const rz = posAttr.getZ(i) * oceanHorizScale;
    oceanRestX[i] = rx;
    oceanRestZ[i] = rz;
    posAttr.setX(i, rx);
    posAttr.setZ(i, rz);
    oceanUVs[i * 2] = ((rx + 180) / 360) * 28;
    oceanUVs[i * 2 + 1] = ((rz + 180) / 360) * 28;
  }
  posAttr.needsUpdate = true;
  oceanGeo.setAttribute('uv', new THREE.BufferAttribute(oceanUVs, 2));
  oceanGeo.setAttribute('color', new THREE.BufferAttribute(oceanColors, 3));
  oceanGeo.computeBoundingBox();
  oceanGeo.computeBoundingSphere();

  const oceanMat = new THREE.MeshPhysicalMaterial({
    vertexColors: true,
    roughness: 0.11,
    metalness: 0.08,
    ior: 1.333,
    reflectivity: 0.88,
    clearcoat: 0.68,
    clearcoatRoughness: 0.05,
    normalMap: waveNormalMap,
    normalScale: new THREE.Vector2(0.75, 0.75),
    clearcoatNormalMap: capillaryNormalMap,
    clearcoatNormalScale: new THREE.Vector2(0.48, 0.48),
    envMapIntensity: 1.25,
  });

  const oceanMesh = new THREE.Mesh(oceanGeo, oceanMat);
  oceanMesh.renderOrder = 2;
  oceanMesh.castShadow = false;
  oceanMesh.receiveShadow = true;
  scene.add(oceanMesh);

  // 1. Island Terrain (rippled sand, soil transition, 3D grass tufts & coastal shells)
  const terrainNormalMap = createTerrainNormalTexture(256);
  prepareIslandAsset(assets.island, terrainNormalMap);
  const islandModel = assets.island;
  islandModel.position.set(ISLAND_CENTER.x, 0, ISLAND_CENTER.y);
  scene.add(islandModel);

  // 2. Coastal Rock Clusters (shoreline capes, lighthouse cliff base, and shallow reef outcrops)
  const rockNormalMap = createRockNormalTexture(256);
  prepareRockClusterAsset(assets.rock_cluster, rockNormalMap);

  const rockPlacements = [
    // Shoreline capes
    { x: -13.5, z: -15.5, scale: 1.35, rot: 0.4, yOffset: 0.0, hitRadius: 2.9, foamInner: 1.2, foamRadius: 2.9 },
    { x: 13.8, z: -17.5, scale: 1.25, rot: 2.1, yOffset: 0.0, hitRadius: 2.75, foamInner: 1.1, foamRadius: 2.7 },
    { x: -16.8, z: -34.0, scale: 1.6, rot: 1.1, yOffset: -0.04, hitRadius: 3.3, foamInner: 1.4, foamRadius: 3.4 },
    { x: 16.5, z: -33.5, scale: 1.45, rot: 3.7, yOffset: -0.04, hitRadius: 3.05, foamInner: 1.3, foamRadius: 3.1 },
    // Lighthouse cliff base rocks
    { x: -12.6, z: -29.2, scale: 1.18, rot: 1.85, yOffset: -0.14, hitRadius: 2.4, foamInner: 0.0, foamRadius: 0.0 },
    { x: -9.2, z: -33.4, scale: 1.08, rot: 4.15, yOffset: -0.18, hitRadius: 2.2, foamInner: 0.0, foamRadius: 0.0 },
    // Offshore shallow reef rocks (tidal zone seated in surf)
    { x: -18.5, z: -22.5, scale: 1.32, rot: 2.75, yOffset: -0.06, hitRadius: 2.85, foamInner: 1.25, foamRadius: 3.25 },
    { x: 18.2, z: -24.5, scale: 1.28, rot: 0.92, yOffset: -0.06, hitRadius: 2.78, foamInner: 1.2, foamRadius: 3.15 },
  ];
  const foamRocks = rockPlacements.filter((r) => r.foamRadius > 0);

  for (const r of rockPlacements) {
    const cluster = assets.rock_cluster.clone(true);
    const groundY = getIslandElevation(r.x - ISLAND_CENTER.x, r.z - ISLAND_CENTER.y);
    cluster.position.set(r.x, Math.max(-0.22, groundY) + r.yOffset, r.z);
    cluster.scale.setScalar(r.scale);
    cluster.rotation.y = r.rot;
    scene.add(cluster);
  }

  // 3. Wooden Pier with Hanging Lantern Lights & Pier Fisher
  const pierModel = assets.pier;
  scene.add(pierModel);

  const pierFisher = createPierFisher(assets.person, scene);

  const pierLanternLights = [];
  const lanternGlassMats = [];
  for (const lanternName of ['PierLantern_L', 'PierLantern_R']) {
    const bulbObj = pierModel.getObjectByName(lanternName);
    if (bulbObj) {
      if (bulbObj.material) {
        lanternGlassMats.push(bulbObj.material);
      }
      const pLight = new THREE.PointLight('#ffaa44', 0.25, 22, 1.6);
      pLight.position.copy(bulbObj.position);
      pierModel.add(pLight);
      pierLanternLights.push(pLight);
    }
  }

  // 4. Coastal Lighthouse with Fresnel Optic & Volumetric Sweeping Beacon
  prepareLighthouseAsset(assets.lighthouse);
  const lighthouseGroup = new THREE.Group();
  const lhX = -10.5;
  const lhZ = -31;
  const lhBaseY = getIslandElevation(lhX - ISLAND_CENTER.x, lhZ - ISLAND_CENTER.y);
  lighthouseGroup.position.set(lhX, lhBaseY - 0.1, lhZ);
  lighthouseGroup.add(assets.lighthouse);

  const lighthouseGlass = assets.lighthouse.getObjectByName('LighthouseGlass');
  const lanternRoomMat = lighthouseGlass ? lighthouseGlass.material : null;
  const fresnelOpticObj = assets.lighthouse.getObjectByName('LHFresnelOptic');
  const fresnelOpticMat = fresnelOpticObj ? fresnelOpticObj.material : null;

  const beaconGroup = new THREE.Group();
  beaconGroup.position.y = 10.62;
  const beaconLight = new THREE.PointLight('#ffd269', 0.2, 55, 1.5);
  beaconGroup.add(beaconLight);

  const beaconSpotLight = new THREE.SpotLight('#ffd885', 0.4, 95, Math.PI * 0.16, 0.82, 1.3);
  beaconSpotLight.castShadow = false;
  const beaconSpotTarget = new THREE.Object3D();
  beaconSpotTarget.position.set(0, -3.2, 28);
  beaconSpotLight.target = beaconSpotTarget;
  beaconGroup.add(beaconSpotLight);
  beaconGroup.add(beaconSpotTarget);

  const fwdBeamArm = new THREE.Group();
  fwdBeamArm.rotation.x = 0.105;
  const fwdCoreCone = createSoftBeamCone(2.1, 34, 24, 24, '#ffebb3', 0.34);
  const fwdHazeCone = createSoftBeamCone(5.2, 44, 24, 24, '#ffd27a', 0.14);
  const fwdLensHalo = createLensHaloDisc(1.5, '#ffe7a0', 0.65);
  fwdLensHalo.position.set(0, 0, 0.46);
  fwdBeamArm.add(fwdCoreCone, fwdHazeCone, fwdLensHalo);
  beaconGroup.add(fwdBeamArm);

  const backBeamYaw = new THREE.Group();
  backBeamYaw.rotation.y = Math.PI;
  const backBeamArm = new THREE.Group();
  backBeamArm.rotation.x = 0.095;
  const backCoreCone = createSoftBeamCone(1.7, 26, 20, 20, '#ffebb3', 0.24);
  const backHazeCone = createSoftBeamCone(4.0, 34, 20, 20, '#ffd27a', 0.10);
  const backLensHalo = createLensHaloDisc(1.25, '#ffe7a0', 0.48);
  backLensHalo.position.set(0, 0, 0.46);
  backBeamArm.add(backCoreCone, backHazeCone, backLensHalo);
  backBeamYaw.add(backBeamArm);
  beaconGroup.add(backBeamYaw);

  const beaconFlashDisc = createLensHaloDisc(3.2, '#ffe8aa', 0.85);
  lighthouseGroup.add(beaconGroup);
  beaconFlashDisc.position.set(0, 10.62, 0);
  lighthouseGroup.add(beaconFlashDisc);
  scene.add(lighthouseGroup);

  const beamLayers = [
    fwdCoreCone,
    fwdHazeCone,
    fwdLensHalo,
    backCoreCone,
    backHazeCone,
    backLensHalo,
  ];
  const beaconWorldPos = new THREE.Vector3(lhX, lhBaseY - 0.1 + 10.62, lhZ);
  let currentBeamScale = 0.06;

  // 5. Beach Umbrella & Lounger Sets
  const beachSpots = [
    { x: -6.2, z: -15.5, rot: 0.25 },
    { x: 5.5, z: -14.8, rot: -0.45 },
  ];
  for (const spot of beachSpots) {
    const setObj = assets.beach_set.clone(true);
    const gy = getIslandElevation(spot.x - ISLAND_CENTER.x, spot.z - ISLAND_CENTER.y);
    setObj.position.set(spot.x, gy - 0.05, spot.z);
    setObj.rotation.y = spot.rot;
    scene.add(setObj);
  }

  // 6. Beach Campfire
  const fireGroup = new THREE.Group();
  const fireX = 7.5;
  const fireZ = -19.2;
  const fireY = getIslandElevation(fireX - ISLAND_CENTER.x, fireZ - ISLAND_CENTER.y);
  fireGroup.position.set(fireX, fireY, fireZ);
  fireGroup.add(assets.campfire);

  const flameMesh = assets.campfire.getObjectByName('CampfireFlame');
  const campfireLight = new THREE.PointLight('#ff6a1a', 0.8, 22, 1.6);
  campfireLight.position.set(0, 0.85, 0);
  fireGroup.add(campfireLight);
  scene.add(fireGroup);

  // 7. Palm Trees across the Island
  const palmPlacements = [
    { x: -5.5, z: -23.5, s: 1.05, lean: 0.26, dir: 0.6 },
    { x: -11.5, z: -22.0, s: 0.92, lean: 0.3, dir: 2.3 },
    { x: -1.5, z: -28.0, s: 1.18, lean: 0.18, dir: -0.4 },
    { x: 4.5, z: -25.5, s: 1.0, lean: 0.28, dir: -1.2 },
    { x: 10.5, z: -22.5, s: 0.95, lean: 0.32, dir: -0.6 },
    { x: 12.2, z: -29.0, s: 1.1, lean: 0.24, dir: 0.9 },
    { x: 2.5, z: -34.5, s: 1.08, lean: 0.22, dir: 1.5 },
    { x: -6.8, z: -36.5, s: 0.96, lean: 0.26, dir: 2.8 },
    { x: 8.5, z: -36.0, s: 0.88, lean: 0.3, dir: -2.1 },
  ];
  const palmTrees = [];
  for (const p of palmPlacements) {
    const py = getIslandElevation(p.x - ISLAND_CENTER.x, p.z - ISLAND_CENTER.y);
    const tree = assets.palm_tree.clone(true);
    tree.position.set(p.x, py - 0.15, p.z);
    tree.scale.setScalar(p.s);
    tree.rotation.y = p.dir;
    tree.rotation.z = p.lean * 0.25;
    tree.userData.crown = tree.getObjectByName('PalmCrown');
    tree.userData.phase = Math.random() * Math.PI * 2;
    scene.add(tree);
    palmTrees.push(tree);
  }

  // 8. Circling Seagulls
  const seagulls = [];
  for (let i = 0; i < 5; i++) {
    const gull = assets.seagull.clone(true);
    gull.userData = {
      leftWing: gull.getObjectByName('WingLeft'),
      rightWing: gull.getObjectByName('WingRight'),
      radius: 14 + Math.random() * 20,
      altitude: 9 + Math.random() * 7,
      speed: 0.22 + Math.random() * 0.14,
      phase: Math.random() * Math.PI * 2,
    };
    scene.add(gull);
    seagulls.push(gull);
  }

  // 9. Interactive Sailboat
  prepareSailboatAsset(assets.sailboat);
  const boatGroup = new THREE.Group();
  boatGroup.add(assets.sailboat);
  boatGroup.add(createHullWaterMask());

  const bowBulbObj = assets.sailboat.getObjectByName('BowLanternBulb');
  const lanternBulbMat = bowBulbObj ? bowBulbObj.material : null;
  const rudderObj = assets.sailboat.getObjectByName('Rudder');

  const bowLight = new THREE.PointLight('#ffaa44', 1.5, 24, 1.7);
  bowLight.position.set(0, 1.55, -3.05);
  boatGroup.add(bowLight);

  const { wakeGroup, wakeMeshes } = createWakeGroup();
  boatGroup.add(wakeGroup);

  boatGroup.position.set(INITIAL_BOAT_POS.x, 0, INITIAL_BOAT_POS.z);
  boatGroup.rotation.y = INITIAL_BOAT_POS.yaw;
  scene.add(boatGroup);

  // Boat State & Input
  const input = {
    forward: false,
    backward: false,
    left: false,
    right: false,
  };
  const boatState = {
    x: INITIAL_BOAT_POS.x,
    z: INITIAL_BOAT_POS.z,
    yaw: INITIAL_BOAT_POS.yaw,
    speed: 0,
    pitch: 0,
    roll: 0,
    zone: 'Teluk Terbuka',
  };

  let currentTimePreset = TIME_PRESETS.day;
  let cameraMode = 'free';

  // Dynamic sky & sun reflection probe for realistic ocean Fresnel highlights
  const pmremGenerator = new THREE.PMREMGenerator(renderer);
  pmremGenerator.compileEquirectangularShader();
  let currentEnvRenderTarget = null;

  const envScene = new THREE.Scene();
  const envDomeGeo = new THREE.SphereGeometry(24, 24, 16);
  const envDomePos = envDomeGeo.attributes.position;
  const envDomeColors = new Float32Array(envDomePos.count * 3);
  envDomeGeo.setAttribute('color', new THREE.BufferAttribute(envDomeColors, 3));
  const envDomeMat = new THREE.MeshBasicMaterial({
    vertexColors: true,
    side: THREE.BackSide,
  });
  const envDome = new THREE.Mesh(envDomeGeo, envDomeMat);
  envScene.add(envDome);

  const envSunMat = new THREE.MeshBasicMaterial({ color: TIME_PRESETS.day.sunColor });
  const envSunDisc = new THREE.Mesh(new THREE.SphereGeometry(2.6, 16, 12), envSunMat);
  envScene.add(envSunDisc);

  function updateSkyEnvironment(preset) {
    const colAttr = envDomeGeo.attributes.color;
    const pos = envDomeGeo.attributes.position;
    const skyTop = preset.sky.clone().lerp(preset.hemiSky, 0.35);
    const horizon = preset.fog.clone();
    const ground = preset.hemiGround.clone().lerp(preset.deepOcean, 0.55);
    const workColor = new THREE.Color();

    for (let i = 0; i < pos.count; i++) {
      const ny = pos.getY(i) / 24;
      if (ny >= 0) {
        workColor.copy(horizon).lerp(skyTop, Math.pow(ny, 0.55));
      } else {
        workColor.copy(horizon).lerp(ground, Math.pow(-ny, 0.45));
      }
      colAttr.setXYZ(i, workColor.r, workColor.g, workColor.b);
    }
    colAttr.needsUpdate = true;

    envSunDisc.position.copy(preset.sunPos).normalize().multiplyScalar(18);
    envSunMat.color.copy(preset.sunColor).multiplyScalar(2.4);

    if (currentEnvRenderTarget) {
      currentEnvRenderTarget.dispose();
    }
    currentEnvRenderTarget = pmremGenerator.fromScene(envScene, 0.03);
    scene.environment = currentEnvRenderTarget.texture;
  }

  function applyTimeOfDay(key) {
    const preset = TIME_PRESETS[key] || TIME_PRESETS.day;
    currentTimePreset = preset;

    scene.background.copy(preset.sky);
    scene.fog.color.copy(preset.fog);
    scene.fog.density = preset.fogDensity;

    dirLight.position.copy(preset.sunPos);
    dirLight.color.copy(preset.sunColor);
    dirLight.intensity = preset.sunIntensity;

    sunOrb.position.copy(preset.sunPos).multiplyScalar(1.65);
    sunOrbMat.color.copy(preset.sunColor);

    hemiLight.color.copy(preset.hemiSky);
    hemiLight.groundColor.copy(preset.hemiGround);
    hemiLight.intensity = preset.hemiIntensity;

    starMat.opacity = preset.starOpacity;
    renderer.toneMappingExposure = preset.exposure;
    updateSkyEnvironment(preset);

    const nightFactor = key === 'night' ? 1 : key === 'sunset' ? 0.65 : 0.15;
    bowLight.intensity = preset.lanternIntensity * 0.6;
    if (lanternBulbMat) {
      lanternBulbMat.emissiveIntensity = 0.6 + nightFactor * 1.6;
    }
    if (lanternRoomMat) {
      lanternRoomMat.emissiveIntensity = 0.22 + nightFactor * 0.55;
    }
    if (fresnelOpticMat) {
      fresnelOpticMat.emissiveIntensity = 0.75 + nightFactor * 2.2;
    }
    currentBeamScale = key === 'night' ? 1.0 : key === 'sunset' ? 0.62 : 0.06;
    for (const layer of beamLayers) {
      layer.material.uniforms.uOpacity.value = layer.userData.baseOpacity * currentBeamScale;
    }
    beaconFlashDisc.material.uniforms.uOpacity.value =
      beaconFlashDisc.userData.baseOpacity * currentBeamScale * 0.22;
    beaconLight.intensity = preset.beaconIntensity;
    beaconSpotLight.intensity = preset.beaconIntensity * (key === 'night' ? 7.5 : key === 'sunset' ? 4.2 : 0.3);

    for (const pl of pierLanternLights) {
      pl.intensity = preset.lanternIntensity;
    }
    for (const gm of lanternGlassMats) {
      gm.emissiveIntensity = 0.5 + nightFactor * 1.6;
    }
  }

  function resetBoat() {
    boatState.x = INITIAL_BOAT_POS.x;
    boatState.z = INITIAL_BOAT_POS.z;
    boatState.yaw = INITIAL_BOAT_POS.yaw;
    boatState.speed = 0;
    boatState.pitch = 0;
    boatState.roll = 0;
    boatState.zone = 'Teluk Terbuka';
    boatGroup.position.set(boatState.x, getWaveHeight(boatState.x, boatState.z, 0) + 0.12, boatState.z);
    boatGroup.rotation.set(0, boatState.yaw, 0);

    if (cameraMode === 'follow') {
      controls.target.set(boatState.x, 1.5, boatState.z);
      camera.position.set(boatState.x + 12, 10, boatState.z + 20);
    }
  }

  // Event Listeners
  const keyMap = {
    KeyW: 'forward',
    ArrowUp: 'forward',
    KeyS: 'backward',
    ArrowDown: 'backward',
    KeyA: 'left',
    ArrowLeft: 'left',
    KeyD: 'right',
    ArrowRight: 'right',
  };

  function setSteerState(controlKey, pressed) {
    input[controlKey] = pressed;
    steerButtons.forEach((btn) => {
      if (btn.dataset.control === controlKey) {
        btn.classList.toggle('is-active', pressed);
      }
    });
  }

  window.addEventListener('keydown', (e) => {
    const action = keyMap[e.code];
    if (action) {
      if (e.code.startsWith('Arrow')) {
        e.preventDefault();
      }
      setSteerState(action, true);
    }
  });

  window.addEventListener('keyup', (e) => {
    const action = keyMap[e.code];
    if (action) {
      setSteerState(action, false);
    }
  });

  window.addEventListener('blur', () => {
    Object.keys(input).forEach((k) => setSteerState(k, false));
  });

  steerButtons.forEach((btn) => {
    const ctrl = btn.dataset.control;
    btn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      setSteerState(ctrl, true);
    });
    const release = () => setSteerState(ctrl, false);
    btn.addEventListener('pointerup', release);
    btn.addEventListener('pointerleave', release);
    btn.addEventListener('pointercancel', release);
  });

  resetBtn.addEventListener('click', resetBoat);

  timeRadios.forEach((radio) => {
    radio.addEventListener('change', (e) => {
      if (e.target.checked) {
        applyTimeOfDay(e.target.value);
      }
    });
  });

  cameraRadios.forEach((radio) => {
    radio.addEventListener('change', (e) => {
      if (e.target.checked) {
        cameraMode = e.target.value;
        if (cameraMode === 'follow') {
          controls.target.set(boatState.x, 1.5, boatState.z);
        }
      }
    });
  });

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  window.__beachSceneState = {
    getBoatState: () => ({ ...boatState }),
    setTimeOfDay: applyTimeOfDay,
    focusCamera: (pos, target) => {
      camera.position.set(pos[0], pos[1], pos[2]);
      controls.target.set(target[0], target[1], target[2]);
      controls.update();
    },
  };

  applyTimeOfDay('day');

  // Animation loop
  const clock = new THREE.Clock();
  const colorWorking = new THREE.Color();

  function updateOceanVertices(elapsed, dt) {
    if (dt > 0) {
      waveNormalMap.offset.x = (waveNormalMap.offset.x + dt * 0.022) % 1;
      waveNormalMap.offset.y = (waveNormalMap.offset.y + dt * 0.014) % 1;
      capillaryNormalMap.offset.x = (capillaryNormalMap.offset.x - dt * 0.031 + 1) % 1;
      capillaryNormalMap.offset.y = (capillaryNormalMap.offset.y + dt * 0.026) % 1;
    }

    const posArr = oceanGeo.attributes.position.array;
    const colArr = oceanGeo.attributes.color.array;
    const { deepOcean, midOcean, shallowOcean, foamColor } = currentTimePreset;

    for (let i = 0; i < oceanVertexCount; i++) {
      const idx3 = i * 3;
      const rx = oceanRestX[i];
      const rz = oceanRestZ[i];
      const wave = evaluateOceanWave(rx, rz, elapsed, _waveEvalOut);

      posArr[idx3] = rx + wave.dispX;
      posArr[idx3 + 1] = wave.height;
      posArr[idx3 + 2] = rz + wave.dispZ;

      const distToIsland = Math.hypot(rx - ISLAND_CENTER.x, rz - ISLAND_CENTER.y);
      const shallowMix = 1 - THREE.MathUtils.smoothstep(distToIsland, 16, 38);
      const hNorm = THREE.MathUtils.clamp((wave.height + 0.85) / 1.85, 0, 1);

      colorWorking
        .copy(deepOcean)
        .lerp(midOcean, THREE.MathUtils.smoothstep(hNorm, 0.2, 0.72))
        .lerp(
          shallowOcean,
          Math.max(shallowMix, THREE.MathUtils.smoothstep(hNorm, 0.68, 0.96) * 0.65)
        );

      const cellular =
        (0.5 + 0.5 * Math.sin(rx * 0.55 - rz * 0.45 + wave.height * 2.1 + elapsed * 0.9)) *
        (0.5 + 0.5 * Math.cos(rx * 0.95 + rz * 1.15 - elapsed * 0.7));

      const crestScore = THREE.MathUtils.clamp(
        (wave.height - 0.52) * 1.35 + (wave.pinch - 0.20) * 1.15,
        0,
        1
      );
      const crestFoam = THREE.MathUtils.smoothstep(
        crestScore * (0.45 + 0.85 * cellular),
        0.34,
        0.86
      ) * 0.88;

      const shoreRing =
        19.8 + Math.sin(elapsed * 2.0 + rx * 0.25) * 1.05 + Math.cos(rz * 0.32 - elapsed * 1.4) * 0.55;
      const shoreFoam =
        distToIsland > 15.8 && distToIsland < shoreRing
          ? THREE.MathUtils.smoothstep(distToIsland, 15.8, 17.8) *
            (1 - THREE.MathUtils.smoothstep(distToIsland, shoreRing - 1.4, shoreRing)) *
            (0.45 + 0.55 * cellular) *
            0.85
          : 0;

      let rockFoam = 0;
      for (let j = 0; j < foamRocks.length; j++) {
        const rk = foamRocks[j];
        if (Math.abs(rx - rk.x) < 5.5 && Math.abs(rz - rk.z) < 5.5) {
          const dRock = Math.hypot(rx - rk.x, rz - rk.z);
          const outerFoam = rk.foamRadius + Math.sin(elapsed * 2.4 + rx * 0.6 + rz * 0.4) * 0.38;
          if (dRock < outerFoam) {
            const f =
              (1 - THREE.MathUtils.smoothstep(dRock, rk.foamInner, outerFoam)) *
              (0.5 + 0.5 * cellular) *
              0.9;
            if (f > rockFoam) {
              rockFoam = f;
            }
          }
        }
      }

      const foamAmount = Math.max(crestFoam, shoreFoam, rockFoam);
      if (foamAmount > 0) {
        colorWorking.lerp(foamColor, foamAmount);
      }

      colArr[idx3] = colorWorking.r;
      colArr[idx3 + 1] = colorWorking.g;
      colArr[idx3 + 2] = colorWorking.b;
    }

    oceanGeo.attributes.position.needsUpdate = true;
    oceanGeo.attributes.color.needsUpdate = true;
    oceanGeo.computeVertexNormals();
  }

  function updateBoatPhysics(dt, elapsed) {
    const accel = 13.5;
    const reverseAccel = 7.5;
    const maxForward = 14.5;
    const maxReverse = -5.5;

    if (input.forward) {
      boatState.speed += accel * dt;
    } else if (input.backward) {
      boatState.speed -= reverseAccel * dt;
    } else {
      boatState.speed *= Math.exp(-1.45 * dt);
    }

    boatState.speed = THREE.MathUtils.clamp(boatState.speed, maxReverse, maxForward);

    // Steering responsiveness
    const steerInput = (input.left ? 1 : 0) - (input.right ? 1 : 0);
    const turnScale = 0.65 + 0.35 * Math.min(1, Math.abs(boatState.speed) / 4);
    const reverseSign = boatState.speed < -0.5 ? -1 : 1;
    boatState.yaw += steerInput * 1.45 * turnScale * reverseSign * dt;

    // Advance position along local -Z forward vector
    const fwdX = -Math.sin(boatState.yaw);
    const fwdZ = -Math.cos(boatState.yaw);
    const prevX = boatState.x;
    const prevZ = boatState.z;

    let nextX = boatState.x + fwdX * boatState.speed * dt;
    let nextZ = boatState.z + fwdZ * boatState.speed * dt;

    let zone = 'Teluk Terbuka';

    // Island shallow-water collision avoidance
    const dxIsland = nextX - ISLAND_CENTER.x;
    const dzIsland = nextZ - ISLAND_CENTER.y;
    const distIsland = Math.hypot(dxIsland, dzIsland);
    if (distIsland < ISLAND_COLLISION_RADIUS) {
      const nx = dxIsland / (distIsland || 1);
      const nz = dzIsland / (distIsland || 1);
      nextX = ISLAND_CENTER.x + nx * ISLAND_COLLISION_RADIUS;
      nextZ = ISLAND_CENTER.y + nz * ISLAND_COLLISION_RADIUS;
      boatState.speed *= 0.65;
      zone = 'Perairan Dangkal';
    } else if (distIsland < 30) {
      zone = 'Pesisir Pantai';
    }

    // Pier collision avoidance (x in [-3.1, 3.1], z in [-19.5, 5.4])
    const pierHalfW = 3.1;
    const pierMinZ = -19.5;
    const pierMaxZ = 5.4;
    if (Math.abs(nextX) < pierHalfW && nextZ > pierMinZ && nextZ < pierMaxZ) {
      const pushLeft = Math.abs(nextX - -pierHalfW);
      const pushRight = Math.abs(pierHalfW - nextX);
      const pushFront = Math.abs(pierMaxZ - nextZ);
      if (pushFront < pushLeft && pushFront < pushRight) {
        nextZ = pierMaxZ;
      } else if (nextX >= 0) {
        nextX = pierHalfW;
      } else {
        nextX = -pierHalfW;
      }
      boatState.speed *= 0.6;
      zone = 'Dekat Dermaga';
    } else if (Math.abs(nextX) < 7.5 && nextZ > -20 && nextZ < 10) {
      zone = 'Dekat Dermaga';
    }

    // Coastal rock & shallow reef collision avoidance
    for (let j = 0; j < rockPlacements.length; j++) {
      const rk = rockPlacements[j];
      const hitRadius = rk.hitRadius;
      if (Math.abs(nextX - rk.x) < hitRadius && Math.abs(nextZ - rk.z) < hitRadius) {
        const dxR = nextX - rk.x;
        const dzR = nextZ - rk.z;
        const dR = Math.hypot(dxR, dzR);
        if (dR < hitRadius) {
          const nx = dxR / (dR || 1);
          const nz = dzR / (dR || 1);
          nextX = rk.x + nx * hitRadius;
          nextZ = rk.z + nz * hitRadius;
          boatState.speed *= 0.6;
          zone = 'Karang Pesisir';
        }
      } else if (
        Math.abs(nextX - rk.x) < hitRadius + 3.2 &&
        Math.abs(nextZ - rk.z) < hitRadius + 3.2 &&
        Math.hypot(nextX - rk.x, nextZ - rk.z) < hitRadius + 3.2
      ) {
        zone = 'Karang Pesisir';
      }
    }

    // Outer ocean containment
    const distOrigin = Math.hypot(nextX, nextZ);
    if (distOrigin > OCEAN_BOUNDARY_RADIUS) {
      const clampScale = OCEAN_BOUNDARY_RADIUS / distOrigin;
      nextX *= clampScale;
      nextZ *= clampScale;
      boatState.speed *= 0.5;
      zone = 'Batas Laut';
    }

    boatState.x = nextX;
    boatState.z = nextZ;
    boatState.zone = zone;

    // Buoyancy & wave pitch/roll in boat local frame
    const wave = getWaveSlope(boatState.x, boatState.z, elapsed);
    const sinY = Math.sin(boatState.yaw);
    const cosY = Math.cos(boatState.yaw);

    // Local forward (-Z) and right (+X) wave slopes
    const forwardSlope = -sinY * wave.dx - cosY * wave.dz;
    const rightSlope = cosY * wave.dx - sinY * wave.dz;

    const targetPitch = Math.atan(forwardSlope) * 0.78 + (boatState.speed / maxForward) * 0.04;
    const targetRoll = -Math.atan(rightSlope) * 0.78 - steerInput * 0.08;

    boatState.pitch = THREE.MathUtils.lerp(boatState.pitch, targetPitch, Math.min(1, dt * 6));
    boatState.roll = THREE.MathUtils.lerp(boatState.roll, targetRoll, Math.min(1, dt * 6));

    boatGroup.position.set(boatState.x, wave.height + 0.22, boatState.z);
    boatGroup.rotation.order = 'YXZ';
    boatGroup.rotation.y = boatState.yaw;
    boatGroup.rotation.x = boatState.pitch;
    boatGroup.rotation.z = boatState.roll;

    // Rudder & wake animation
    if (rudderObj) {
      rudderObj.rotation.y = THREE.MathUtils.lerp(
        rudderObj.rotation.y,
        steerInput * 0.45,
        Math.min(1, dt * 10)
      );
    }

    const speedRatio = Math.min(1, Math.abs(boatState.speed) / maxForward);
    wakeGroup.visible = speedRatio > 0.04;
    wakeGroup.scale.set(0.65 + speedRatio * 0.55, 1, 0.5 + speedRatio * 1.15);
    wakeMeshes.forEach((wm, idx) => {
      wm.material.opacity = (idx === 2 ? 0.35 : 0.48) * speedRatio;
    });

    // Follow camera smoothly moves with boat delta
    if (cameraMode === 'follow') {
      const deltaX = boatState.x - prevX;
      const deltaZ = boatState.z - prevZ;
      camera.position.x += deltaX;
      camera.position.z += deltaZ;
      controls.target.lerp(new THREE.Vector3(boatState.x, 1.5, boatState.z), Math.min(1, dt * 5));
    }

    // Update HUD telemetry
    const knots = Math.abs(boatState.speed) * 1.45;
    const deg = Math.round((((-boatState.yaw * 180) / Math.PI) % 360 + 360) % 360);
    speedEl.textContent = `${knots.toFixed(1)} kn`;
    headingEl.textContent = `${String(deg).padStart(3, '0')}°`;
    zoneEl.textContent = boatState.zone;
  }

  function animate() {
    requestAnimationFrame(animate);
    const dt = Math.min(clock.getDelta(), 0.05);
    const elapsed = clock.elapsedTime;
    const animTime = prefersReducedMotion ? 0 : elapsed;

    updateOceanVertices(animTime, prefersReducedMotion ? 0 : dt);
    updateBoatPhysics(dt, animTime);
    pierFisher.update(animTime);

    if (!prefersReducedMotion) {
      for (const tree of palmTrees) {
        if (tree.userData.crown) {
          const phase = tree.userData.phase;
          tree.userData.crown.rotation.z = Math.sin(elapsed * 1.15 + phase) * 0.045;
          tree.userData.crown.rotation.x = Math.cos(elapsed * 0.95 + phase) * 0.035;
        }
      }

      const beaconAngle = elapsed * 0.65;
      beaconGroup.rotation.y = beaconAngle;
      if (fresnelOpticObj) {
        fresnelOpticObj.rotation.y = beaconAngle;
      }

      const dxCam = camera.position.x - beaconWorldPos.x;
      const dzCam = camera.position.z - beaconWorldPos.z;
      const invCamLen = 1 / (Math.hypot(dxCam, dzCam) || 1);
      const beamAlign = Math.abs(
        Math.sin(beaconAngle) * (dxCam * invCamLen) + Math.cos(beaconAngle) * (dzCam * invCamLen)
      );
      const flashFactor = Math.pow(beamAlign, 12.0);
      for (const layer of beamLayers) {
        const uniforms = layer.material.uniforms;
        if (uniforms.uTime) {
          uniforms.uTime.value = elapsed;
        }
        uniforms.uOpacity.value =
          layer.userData.baseOpacity * currentBeamScale * (1.0 + flashFactor * 0.25);
      }
      beaconFlashDisc.lookAt(camera.position);
      beaconFlashDisc.material.uniforms.uOpacity.value =
        beaconFlashDisc.userData.baseOpacity * currentBeamScale * (0.22 + flashFactor * 1.15);
      beaconFlashDisc.scale.setScalar(0.85 + flashFactor * 0.65);

      const flicker = 0.85 + Math.sin(elapsed * 14) * 0.1 + Math.cos(elapsed * 23) * 0.08;
      if (flameMesh) {
        flameMesh.scale.set(1, flicker, 1);
      }
      campfireLight.intensity = currentTimePreset.campfireIntensity * flicker;

      for (const gull of seagulls) {
        const { leftWing, rightWing, radius, altitude, speed, phase } = gull.userData;
        const angle = elapsed * speed + phase;
        const gx = ISLAND_CENTER.x + Math.cos(angle) * radius;
        const gz = ISLAND_CENTER.y + Math.sin(angle) * radius;
        const gy = altitude + Math.sin(elapsed * 1.4 + phase) * 0.8;

        gull.position.set(gx, gy, gz);
        gull.rotation.y = Math.PI - angle;

        const flap = Math.sin(elapsed * 6.5 + phase) * 0.42;
        if (rightWing) rightWing.rotation.z = flap;
        if (leftWing) leftWing.rotation.z = -flap;
      }
    }

    controls.update();
    renderer.render(scene, camera);
  }

  animate();
}

init().catch((err) => {
  console.error('Failed to initialize beach 3D scene:', err);
});
