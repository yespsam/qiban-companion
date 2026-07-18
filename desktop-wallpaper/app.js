import * as THREE from './vendor/three.module.js';

const canvas = document.getElementById('scene');
const nameEl = document.getElementById('name');
const lineEl = document.getElementById('line');
const serverStateEl = document.getElementById('server-state');
const personaButtons = {
  female: document.getElementById('female-btn'),
  male: document.getElementById('male-btn')
};
const actionButtons = [...document.querySelectorAll('[data-action]')];

const params = new URLSearchParams(window.location.search);
const voiceEnabledInPage = params.get('voice') === '1';
const voiceApiBase = (params.get('api') || 'http://127.0.0.1:8766').replace(/\/+$/, '');

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0x000000, 0);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(33, 1, 0.1, 100);
camera.position.set(0, 0.22, 7.2);

const personas = {
  female: {
    id: 'female_companion',
    name: '小栖',
    idleLine: '我在桌面旁边，等你随时叫我。',
    voiceLine: '主人，我是小栖。这个声音，主人喜欢吗？',
    actionLines: {
      idle: '我在桌面旁边，等你随时叫我。',
      wave: '看到你啦，我一直在。',
      nod: '嗯，我听着。',
      turn: '换个角度，也还是陪着你。',
      heart: '收到，我会认真回应你。',
      voice: '主人，我是小栖。这个声音，主人喜欢吗？'
    },
    hair: 0x2b2035,
    hairAlt: 0x695085,
    eye: 0x23d982,
    jacket: 0x111816,
    outfit: 0x173d35,
    inner: 0xf2eadf,
    accent: 0x07c160,
    panel: 0xa9f6c2,
    cheek: 0xff99ad,
    scale: 1,
    shoulder: 0.88,
    hip: 0.82,
    stance: 0.18,
    legSkin: true,
    longHair: true
  },
  male: {
    id: 'male_companion',
    name: '栖安',
    idleLine: '我在这里，先把心放稳。',
    voiceLine: '主人，我是栖安。我会一直在这里陪你。',
    actionLines: {
      idle: '我在这里，先把心放稳。',
      wave: '我看见你了，先慢慢来。',
      nod: '我明白，我们一步一步处理。',
      turn: '我换个位置，继续守着你。',
      heart: '放心，我会把你的话放在心上。',
      voice: '主人，我是栖安。我会一直在这里陪你。'
    },
    hair: 0x1d1c25,
    hairAlt: 0x4f435f,
    eye: 0x81d7a0,
    jacket: 0x15171b,
    outfit: 0x26352f,
    inner: 0xeee6dc,
    accent: 0x7dda96,
    panel: 0xb7ffd1,
    cheek: 0xf0a996,
    scale: 1.04,
    shoulder: 1.04,
    hip: 0.76,
    stance: 0.14,
    legSkin: false,
    longHair: false
  }
};

const state = {
  activePersona: 'female',
  action: 'idle',
  actionStarted: 0,
  dragYaw: -0.08,
  pointerX: 0,
  pointerY: 0,
  isDragging: false,
  dragStartX: 0,
  dragStartYaw: 0,
  lastPointerMovedAt: 0,
  voiceReady: false,
  voiceError: '',
  speaking: false,
  currentAudio: null
};

const rig = {
  femaleOnly: [],
  maleOnly: [],
  hairStrands: [],
  coatPanels: [],
  trimPieces: []
};

const mats = {
  skin: new THREE.MeshToonMaterial({ color: 0xffd8c8 }),
  skinShade: new THREE.MeshToonMaterial({ color: 0xf2bfae }),
  hair: new THREE.MeshToonMaterial({ color: personas.female.hair }),
  hairAlt: new THREE.MeshToonMaterial({ color: personas.female.hairAlt }),
  jacket: new THREE.MeshToonMaterial({ color: personas.female.jacket }),
  outfit: new THREE.MeshToonMaterial({ color: personas.female.outfit }),
  inner: new THREE.MeshToonMaterial({ color: personas.female.inner }),
  accent: new THREE.MeshToonMaterial({ color: personas.female.accent }),
  eye: new THREE.MeshBasicMaterial({ color: personas.female.eye }),
  white: new THREE.MeshBasicMaterial({ color: 0xfffbf3 }),
  dark: new THREE.MeshBasicMaterial({ color: 0x130f13 }),
  boot: new THREE.MeshToonMaterial({ color: 0x121215 }),
  metal: new THREE.MeshToonMaterial({ color: 0xc0aa79 }),
  cheek: new THREE.MeshBasicMaterial({ color: personas.female.cheek, transparent: true, opacity: 0.5 }),
  panel: new THREE.MeshBasicMaterial({
    color: personas.female.panel,
    transparent: true,
    opacity: 0.23,
    side: THREE.DoubleSide,
    depthWrite: false
  }),
  glow: new THREE.MeshBasicMaterial({
    color: personas.female.accent,
    transparent: true,
    opacity: 0.78
  }),
  floor: new THREE.MeshBasicMaterial({ color: 0x07110d, transparent: true, opacity: 0.32 }),
  particle: new THREE.PointsMaterial({ color: 0xc8ead7, size: 0.024, transparent: true, opacity: 0.58 }),
  outline: new THREE.MeshBasicMaterial({ color: 0x120d12, side: THREE.BackSide })
};

const ambient = new THREE.AmbientLight(0xffffff, 1.1);
scene.add(ambient);

const keyLight = new THREE.DirectionalLight(0xf8ffe9, 3.8);
keyLight.position.set(-3.2, 4.4, 4.4);
scene.add(keyLight);

const fillLight = new THREE.PointLight(0xffa4ba, 2, 8);
fillLight.position.set(3.1, 1.8, 2.8);
scene.add(fillLight);

const rimLight = new THREE.PointLight(personas.female.accent, 3.2, 9);
rimLight.position.set(2.8, -0.4, 3.2);
scene.add(rimLight);

const avatar = new THREE.Group();
const body = new THREE.Group();
const head = new THREE.Group();
const leftArm = new THREE.Group();
const rightArm = new THREE.Group();
const leftForearm = new THREE.Group();
const rightForearm = new THREE.Group();
const leftLeg = new THREE.Group();
const rightLeg = new THREE.Group();
const leftShin = new THREE.Group();
const rightShin = new THREE.Group();

scene.add(avatar);
avatar.add(body);
body.add(head, leftArm, rightArm, leftLeg, rightLeg);
leftArm.add(leftForearm);
rightArm.add(rightForearm);
leftLeg.add(leftShin);
rightLeg.add(rightShin);

Object.assign(rig, {
  avatar, body, head, leftArm, rightArm, leftForearm, rightForearm,
  leftLeg, rightLeg, leftShin, rightShin
});

function outlinedMesh(geometry, material, outlineScale = 1.035) {
  const wrapper = new THREE.Group();
  const outline = new THREE.Mesh(geometry, mats.outline);
  const mesh = new THREE.Mesh(geometry, material);
  outline.scale.setScalar(outlineScale);
  outline.renderOrder = 0;
  mesh.renderOrder = 1;
  wrapper.add(outline, mesh);
  wrapper.main = mesh;
  return wrapper;
}

function addPart(parent, geometry, material, options = {}) {
  const part = outlinedMesh(geometry, material, options.outlineScale || 1.035);
  applyTransform(part, options);
  parent.add(part);
  return part;
}

function addPlain(parent, geometry, material, options = {}) {
  const mesh = new THREE.Mesh(geometry, material);
  applyTransform(mesh, options);
  parent.add(mesh);
  return mesh;
}

function applyTransform(object, options) {
  if (options.position) object.position.set(...options.position);
  if (options.scale) object.scale.set(...options.scale);
  if (options.rotation) object.rotation.set(...options.rotation);
}

function capsule(radius, length, segments = 10, radial = 24) {
  return new THREE.CapsuleGeometry(radius, length, segments, radial);
}

function markFemale(part) {
  rig.femaleOnly.push(part);
  return part;
}

function markMale(part) {
  rig.maleOnly.push(part);
  return part;
}

function makeHeartGeometry() {
  const shape = new THREE.Shape();
  shape.moveTo(0, -0.22);
  shape.bezierCurveTo(-0.48, -0.62, -0.9, -0.16, -0.68, 0.28);
  shape.bezierCurveTo(-0.5, 0.64, -0.12, 0.54, 0, 0.26);
  shape.bezierCurveTo(0.12, 0.54, 0.5, 0.64, 0.68, 0.28);
  shape.bezierCurveTo(0.9, -0.16, 0.48, -0.62, 0, -0.22);
  return new THREE.ExtrudeGeometry(shape, {
    depth: 0.045,
    bevelEnabled: true,
    bevelThickness: 0.008,
    bevelSize: 0.012,
    bevelSegments: 2
  });
}

function buildStage() {
  rig.floor = addPlain(
    scene,
    new THREE.CircleGeometry(2.4, 96),
    mats.floor,
    { position: [0.72, -1.88, 0], rotation: [-Math.PI / 2, 0, 0], scale: [1.28, 0.52, 1] }
  );

  rig.orbit = addPlain(
    scene,
    new THREE.TorusGeometry(1.55, 0.006, 10, 160),
    mats.glow,
    { position: [0.72, 0.24, -0.48], rotation: [0, 0, -0.14], scale: [1, 1.28, 1] }
  );
  rig.orbit.material.opacity = 0.2;

  const particlesGeometry = new THREE.BufferGeometry();
  const count = 220;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    positions[i * 3] = (Math.random() - 0.5) * 9.6;
    positions[i * 3 + 1] = -1.4 + Math.random() * 4.8;
    positions[i * 3 + 2] = -3.8 + Math.random() * 2.8;
  }
  particlesGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  rig.particles = new THREE.Points(particlesGeometry, mats.particle);
  scene.add(rig.particles);
}

function buildCharacter() {
  body.position.set(0, 0, 0);
  head.position.set(0, 1.32, 0.03);

  buildBody();
  buildArms();
  buildLegs();
  buildHead();
  buildHair();
  buildEyesAndFace();
  buildAccessories();
  buildHeart();
}

function buildBody() {
  rig.neck = addPart(body, new THREE.CylinderGeometry(0.115, 0.13, 0.25, 24), mats.skin, {
    position: [0, 0.94, 0],
    outlineScale: 1.04
  });
  rig.innerTop = addPart(body, capsule(0.25, 0.92, 12, 30), mats.inner, {
    position: [0, 0.36, 0],
    scale: [0.82, 1, 0.56],
    outlineScale: 1.035
  });
  rig.jacketLeft = addPart(body, new THREE.BoxGeometry(0.2, 0.88, 0.07), mats.jacket, {
    position: [-0.16, 0.38, 0.25],
    rotation: [0.04, 0.08, 0.08],
    outlineScale: 1.035
  });
  rig.jacketRight = addPart(body, new THREE.BoxGeometry(0.2, 0.88, 0.07), mats.jacket, {
    position: [0.16, 0.38, 0.25],
    rotation: [0.04, -0.08, -0.08],
    outlineScale: 1.035
  });
  rig.hoodBack = addPart(body, new THREE.TorusGeometry(0.34, 0.055, 12, 44, Math.PI), mats.inner, {
    position: [0, 0.92, -0.1],
    rotation: [Math.PI * 0.55, 0, 0],
    scale: [1.05, 0.72, 0.7],
    outlineScale: 1.04
  });
  rig.belt = addPart(body, new THREE.TorusGeometry(0.33, 0.018, 10, 64), mats.dark, {
    position: [0, -0.15, 0.01],
    rotation: [Math.PI / 2, 0, 0],
    scale: [1.18, 0.66, 1],
    outlineScale: 1.03
  });
  rig.buckle = addPart(body, new THREE.TorusGeometry(0.055, 0.008, 8, 24), mats.metal, {
    position: [0.02, -0.15, 0.34],
    rotation: [0, 0, 0.2],
    scale: [1.2, 0.86, 1]
  });
  rig.chestGlow = addPlain(body, new THREE.BoxGeometry(0.44, 0.044, 0.02), mats.glow, {
    position: [0.02, 0.57, 0.34],
    rotation: [0, 0, -0.09]
  });
  rig.shortPanel = markFemale(addPart(body, new THREE.CylinderGeometry(0.46, 0.54, 0.32, 7), mats.dark, {
    position: [0, -0.45, 0],
    scale: [1, 1, 0.58],
    outlineScale: 1.032
  }));
  rig.pleat = markFemale(addPart(body, new THREE.BoxGeometry(0.18, 0.38, 0.04), mats.inner, {
    position: [-0.08, -0.46, 0.34],
    rotation: [0, 0, -0.06],
    outlineScale: 1.025
  }));
  rig.maleWaist = markMale(addPart(body, new THREE.CylinderGeometry(0.36, 0.41, 0.34, 10), mats.dark, {
    position: [0, -0.45, 0],
    scale: [1, 1, 0.6],
    outlineScale: 1.032
  }));

  const panelGeo = new THREE.PlaneGeometry(0.18, 1.22);
  rig.panelLeft = addPlain(body, panelGeo, mats.panel, {
    position: [-0.42, -0.28, 0.1],
    rotation: [0.05, 0.14, 0.06]
  });
  rig.panelRight = addPlain(body, panelGeo, mats.panel, {
    position: [0.42, -0.28, 0.1],
    rotation: [0.05, -0.14, -0.06]
  });
  rig.backPanel = addPlain(body, new THREE.PlaneGeometry(0.28, 1.36), mats.panel, {
    position: [0.38, -0.36, -0.24],
    rotation: [0.05, -0.28, -0.08]
  });
  rig.coatPanels.push(rig.panelLeft, rig.panelRight, rig.backPanel);
}

function buildArms() {
  leftArm.position.set(-0.46, 0.78, 0);
  rightArm.position.set(0.46, 0.78, 0);
  leftForearm.position.set(0, -0.66, 0);
  rightForearm.position.set(0, -0.66, 0);

  rig.leftSleeve = addPart(leftArm, capsule(0.082, 0.58, 10, 22), mats.jacket, {
    position: [0, -0.34, 0],
    scale: [1.1, 1, 0.78],
    outlineScale: 1.045
  });
  rig.rightSleeve = addPart(rightArm, capsule(0.082, 0.58, 10, 22), mats.jacket, {
    position: [0, -0.34, 0],
    scale: [1.1, 1, 0.78],
    outlineScale: 1.045
  });
  rig.leftCuff = addPart(leftForearm, capsule(0.072, 0.52, 10, 20), mats.inner, {
    position: [0, -0.28, 0],
    scale: [1.25, 1.05, 0.82],
    outlineScale: 1.04
  });
  rig.rightCuff = addPart(rightForearm, capsule(0.072, 0.52, 10, 20), mats.inner, {
    position: [0, -0.28, 0],
    scale: [1.25, 1.05, 0.82],
    outlineScale: 1.04
  });
  rig.leftHand = addPart(leftForearm, new THREE.SphereGeometry(0.086, 22, 14), mats.skin, {
    position: [0, -0.58, 0.02],
    scale: [0.8, 1.05, 0.58],
    outlineScale: 1.045
  });
  rig.rightHand = addPart(rightForearm, new THREE.SphereGeometry(0.086, 22, 14), mats.skin, {
    position: [0, -0.58, 0.02],
    scale: [0.8, 1.05, 0.58],
    outlineScale: 1.045
  });
}

function buildLegs() {
  leftLeg.position.set(-0.17, -0.58, 0);
  rightLeg.position.set(0.17, -0.58, 0);
  leftShin.position.set(0, -0.86, 0);
  rightShin.position.set(0, -0.86, 0);

  rig.leftThighSkin = markFemale(addPart(leftLeg, capsule(0.066, 0.76, 10, 20), mats.skin, {
    position: [0, -0.39, 0],
    scale: [0.9, 1, 0.76],
    outlineScale: 1.045
  }));
  rig.rightThighSkin = markFemale(addPart(rightLeg, capsule(0.066, 0.76, 10, 20), mats.skin, {
    position: [0, -0.39, 0],
    scale: [0.9, 1, 0.76],
    outlineScale: 1.045
  }));
  rig.leftPant = markMale(addPart(leftLeg, capsule(0.074, 0.86, 10, 22), mats.dark, {
    position: [0, -0.43, 0],
    scale: [0.88, 1, 0.72],
    outlineScale: 1.045
  }));
  rig.rightPant = markMale(addPart(rightLeg, capsule(0.074, 0.86, 10, 22), mats.dark, {
    position: [0, -0.43, 0],
    scale: [0.88, 1, 0.72],
    outlineScale: 1.045
  }));
  rig.leftShinMesh = addPart(leftShin, capsule(0.068, 0.78, 10, 22), mats.outfit, {
    position: [0, -0.4, 0],
    scale: [0.84, 1, 0.7],
    outlineScale: 1.045
  });
  rig.rightShinMesh = addPart(rightShin, capsule(0.068, 0.78, 10, 22), mats.outfit, {
    position: [0, -0.4, 0],
    scale: [0.84, 1, 0.7],
    outlineScale: 1.045
  });
  rig.leftBoot = addPart(leftShin, new THREE.BoxGeometry(0.22, 0.13, 0.34), mats.boot, {
    position: [0.015, -0.84, 0.09],
    rotation: [0.05, 0, 0.02],
    outlineScale: 1.045
  });
  rig.rightBoot = addPart(rightShin, new THREE.BoxGeometry(0.22, 0.13, 0.34), mats.boot, {
    position: [-0.015, -0.84, 0.09],
    rotation: [0.05, 0, -0.02],
    outlineScale: 1.045
  });
  rig.leftBootGlow = addPlain(leftShin, new THREE.BoxGeometry(0.04, 0.012, 0.022), mats.glow, {
    position: [0.06, -0.78, 0.27],
    rotation: [0.05, 0, 0.1]
  });
  rig.rightBootGlow = addPlain(rightShin, new THREE.BoxGeometry(0.04, 0.012, 0.022), mats.glow, {
    position: [-0.06, -0.78, 0.27],
    rotation: [0.05, 0, -0.1]
  });
}

function buildHead() {
  rig.headMesh = addPart(head, new THREE.SphereGeometry(0.29, 38, 26), mats.skin, {
    position: [0, 0, 0],
    scale: [0.86, 1.02, 0.72],
    outlineScale: 1.035
  });
  rig.earLeft = addPart(head, new THREE.SphereGeometry(0.044, 16, 10), mats.skinShade, {
    position: [-0.25, -0.02, 0.005],
    scale: [0.6, 1.1, 0.38],
    outlineScale: 1.04
  });
  rig.earRight = addPart(head, new THREE.SphereGeometry(0.044, 16, 10), mats.skinShade, {
    position: [0.25, -0.02, 0.005],
    scale: [0.6, 1.1, 0.38],
    outlineScale: 1.04
  });
}

function buildHair() {
  rig.hairCap = addPart(head, new THREE.SphereGeometry(0.31, 36, 18, 0, Math.PI * 2, 0, Math.PI * 0.62), mats.hair, {
    position: [0, 0.07, -0.02],
    scale: [0.95, 0.88, 0.82],
    outlineScale: 1.035
  });
  rig.backHairLong = markFemale(addPart(head, capsule(0.16, 0.7, 10, 22), mats.hair, {
    position: [0, -0.27, -0.19],
    scale: [1.42, 1.1, 0.5],
    outlineScale: 1.035
  }));
  rig.backHairShort = markMale(addPart(head, capsule(0.13, 0.28, 8, 20), mats.hair, {
    position: [0, -0.13, -0.2],
    scale: [1.36, 0.72, 0.5],
    outlineScale: 1.035
  }));

  const bangGeo = new THREE.ConeGeometry(0.06, 0.29, 7);
  const bangs = [
    [0, 0.13, 0.29, 0.12, 0, Math.PI, 1.15, 1.05, 0.68, mats.hairAlt],
    [-0.12, 0.12, 0.28, 0.14, 0.12, Math.PI + 0.22, 0.86, 0.96, 0.62, mats.hair],
    [0.13, 0.12, 0.27, 0.1, -0.14, Math.PI - 0.24, 0.92, 0.92, 0.62, mats.hair],
    [-0.22, 0.06, 0.2, -0.1, 0.38, Math.PI + 0.5, 0.72, 0.86, 0.52, mats.hair],
    [0.23, 0.05, 0.18, -0.08, -0.4, Math.PI - 0.48, 0.72, 0.84, 0.52, mats.hair]
  ];
  rig.bangs = bangs.map(([x, y, z, rx, ry, rz, sx, sy, sz, mat]) => (
    addPart(head, bangGeo, mat, {
      position: [x, y, z],
      rotation: [rx, ry, rz],
      scale: [sx, sy, sz],
      outlineScale: 1.035
    })
  ));

  const sideGeo = capsule(0.047, 0.56, 8, 16);
  rig.sideLockLeft = addPart(head, sideGeo, mats.hair, {
    position: [-0.31, -0.16, 0.1],
    rotation: [0.1, 0.12, -0.08],
    scale: [0.8, 1, 0.62],
    outlineScale: 1.04
  });
  rig.sideLockRight = addPart(head, sideGeo, mats.hair, {
    position: [0.31, -0.16, 0.1],
    rotation: [0.1, -0.12, 0.08],
    scale: [0.8, 1, 0.62],
    outlineScale: 1.04
  });
  rig.hairStrands.push(rig.sideLockLeft, rig.sideLockRight, ...rig.bangs);

  for (let i = 0; i < 7; i += 1) {
    const spike = markMale(addPart(head, new THREE.ConeGeometry(0.055, 0.28, 6), i % 2 ? mats.hairAlt : mats.hair, {
      position: [(-0.24 + i * 0.08), 0.24 + Math.sin(i) * 0.03, -0.02 + (i % 3) * 0.04],
      rotation: [0.1 + i * 0.04, 0.1 - i * 0.04, Math.PI + (-0.5 + i * 0.16)],
      scale: [0.75, 0.88 + (i % 2) * 0.22, 0.6],
      outlineScale: 1.035
    }));
    rig.hairStrands.push(spike);
  }
}

function buildEyesAndFace() {
  const eyeWhiteGeo = new THREE.CircleGeometry(0.058, 32);
  const pupilGeo = new THREE.CircleGeometry(0.031, 32);
  const highlightGeo = new THREE.CircleGeometry(0.011, 16);
  const cheekGeo = new THREE.CircleGeometry(0.032, 20);

  rig.eyeLeft = new THREE.Group();
  rig.eyeRight = new THREE.Group();
  rig.eyeLeft.position.set(-0.096, 0.005, 0.235);
  rig.eyeRight.position.set(0.096, 0.005, 0.235);
  rig.eyeLeft.scale.set(0.86, 1.38, 1);
  rig.eyeRight.scale.set(0.86, 1.38, 1);
  head.add(rig.eyeLeft, rig.eyeRight);

  for (const eye of [rig.eyeLeft, rig.eyeRight]) {
    addPlain(eye, eyeWhiteGeo, mats.white);
    eye.pupil = addPlain(eye, pupilGeo, mats.eye, { position: [0, -0.004, 0.006] });
    eye.highlight = addPlain(eye, highlightGeo, mats.white, { position: [-0.018, 0.024, 0.012] });
  }

  rig.cheekLeft = addPlain(head, cheekGeo, mats.cheek, {
    position: [-0.17, -0.1, 0.238],
    scale: [1.6, 0.58, 1]
  });
  rig.cheekRight = addPlain(head, cheekGeo, mats.cheek, {
    position: [0.17, -0.1, 0.238],
    scale: [1.6, 0.58, 1]
  });
  rig.mouth = addPlain(head, new THREE.TorusGeometry(0.034, 0.004, 8, 28, Math.PI), mats.dark, {
    position: [0, -0.145, 0.242],
    rotation: [0, 0, Math.PI],
    scale: [1.15, 0.58, 1]
  });
}

function buildAccessories() {
  const ornament = new THREE.Group();
  head.add(ornament);
  ornament.position.set(0.23, 0.11, 0.13);
  ornament.rotation.set(0.12, -0.18, -0.1);
  rig.ornament = ornament;

  addPart(ornament, new THREE.TorusGeometry(0.05, 0.006, 8, 28), mats.metal, {
    position: [0, 0, 0.02],
    scale: [1.1, 1.1, 1]
  });
  addPlain(ornament, new THREE.BoxGeometry(0.075, 0.11, 0.012), mats.panel, {
    position: [0.035, -0.08, 0.03],
    rotation: [0, 0, -0.12]
  });
  addPlain(ornament, new THREE.BoxGeometry(0.018, 0.07, 0.014), mats.glow, {
    position: [0.035, -0.08, 0.04]
  });

  rig.chestPendant = addPart(body, new THREE.OctahedronGeometry(0.045, 0), mats.accent, {
    position: [0.02, 0.24, 0.35],
    rotation: [0.2, 0.2, 0.1],
    outlineScale: 1.025
  });
  rig.legCharm = markFemale(addPart(leftLeg, new THREE.TorusGeometry(0.08, 0.006, 8, 34), mats.metal, {
    position: [-0.005, -0.08, 0.08],
    rotation: [Math.PI / 2, 0, 0],
    scale: [1.1, 0.7, 1]
  }));
}

function buildHeart() {
  rig.heart = outlinedMesh(makeHeartGeometry(), new THREE.MeshToonMaterial({ color: 0xff6f9a }), 1.045);
  rig.heart.position.set(0, 1.68, 0.72);
  rig.heart.scale.setScalar(0.001);
  rig.heart.visible = false;
  avatar.add(rig.heart);
}

function easeOutCubic(x) {
  return 1 - Math.pow(1 - x, 3);
}

function easeInOut(x) {
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

function setVisible(parts, visible) {
  parts.forEach((part) => { part.visible = visible; });
}

function setPersona(id) {
  state.activePersona = id;
  const persona = personas[id];
  mats.hair.color.setHex(persona.hair);
  mats.hairAlt.color.setHex(persona.hairAlt);
  mats.jacket.color.setHex(persona.jacket);
  mats.outfit.color.setHex(persona.outfit);
  mats.inner.color.setHex(persona.inner);
  mats.accent.color.setHex(persona.accent);
  mats.eye.color.setHex(persona.eye);
  mats.cheek.color.setHex(persona.cheek);
  mats.panel.color.setHex(persona.panel);
  mats.glow.color.setHex(persona.accent);
  rig.heart.main.material.color.setHex(id === 'female' ? 0xff6f9a : 0x8dffc0);
  rimLight.color.setHex(persona.accent);
  fillLight.color.setHex(id === 'female' ? 0xffa4ba : 0x9cc8ff);
  setVisible(rig.femaleOnly, id === 'female');
  setVisible(rig.maleOnly, id === 'male');
  rig.sideLockLeft.visible = id === 'female';
  rig.sideLockRight.visible = id === 'female';
  rig.backHairLong.visible = id === 'female';
  rig.backHairShort.visible = id === 'male';
  nameEl.textContent = persona.name;
  lineEl.textContent = persona.actionLines[state.action] || persona.idleLine;
  Object.entries(personaButtons).forEach(([key, button]) => {
    button.classList.toggle('active', key === id);
  });
  resize();
}

function setAction(action) {
  state.action = action;
  state.actionStarted = performance.now() * 0.001;
  actionButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.action === action);
  });
  lineEl.textContent = personas[state.activePersona].actionLines[action] || personas[state.activePersona].idleLine;
  if (action === 'voice') {
    requestVoice();
  }
}

function finishActionIfNeeded(elapsed, duration) {
  if (elapsed >= duration && state.action !== 'idle') {
    if (state.action === 'turn') {
      state.dragYaw += Math.PI * 2;
    }
    setAction('idle');
  }
}

function applyPersonaShape(persona) {
  rig.jacketLeft.position.x = -0.2 * persona.shoulder;
  rig.jacketRight.position.x = 0.2 * persona.shoulder;
  leftArm.position.x = -0.48 * persona.shoulder;
  rightArm.position.x = 0.48 * persona.shoulder;
  leftLeg.position.x = -persona.stance;
  rightLeg.position.x = persona.stance;
  rig.innerTop.scale.x = 0.82 * persona.shoulder;
  rig.innerTop.scale.z = persona.id === 'male_companion' ? 0.62 : 0.58;
  rig.shortPanel.scale.x = persona.hip;
  rig.maleWaist.scale.x = persona.hip;
  rig.panelLeft.scale.y = persona.id === 'male_companion' ? 1.12 : 0.92;
  rig.panelRight.scale.y = persona.id === 'male_companion' ? 1.12 : 0.92;
}

function updateBasePose(t) {
  const persona = personas[state.activePersona];
  applyPersonaShape(persona);

  const breath = Math.sin(t * 2.1) * 0.018;
  const sway = Math.sin(t * 0.76) * 0.022;
  const pointerLag = Math.max(0, 1 - (t - state.lastPointerMovedAt) / 3);

  body.position.y = breath * 0.45;
  body.rotation.z = sway * 0.45;
  body.scale.set(1 + breath * 0.18, 1 + breath, 1);
  head.rotation.x = -state.pointerY * 0.13 * pointerLag + Math.sin(t * 1.08) * 0.014;
  head.rotation.y = state.pointerX * 0.22 * pointerLag;
  head.rotation.z = -sway * 0.7;

  leftArm.rotation.set(0.04, 0.06, 0.34 + sway * 0.2);
  rightArm.rotation.set(0.04, -0.06, -0.34 + sway * 0.2);
  leftForearm.rotation.set(0.03, 0, 0.1);
  rightForearm.rotation.set(0.03, 0, -0.1);
  leftLeg.rotation.set(0.03, 0, 0.035 - sway * 0.12);
  rightLeg.rotation.set(0.03, 0, -0.035 - sway * 0.12);
  leftShin.rotation.set(-0.04, 0, -0.015);
  rightShin.rotation.set(-0.04, 0, 0.015);

  rig.hairStrands.forEach((strand, i) => {
    strand.rotation.z += Math.sin(t * 1.3 + i * 0.6) * 0.0008;
  });
  rig.panelLeft.rotation.z = 0.06 + Math.sin(t * 1.1) * 0.02;
  rig.panelRight.rotation.z = -0.06 - Math.sin(t * 1.07) * 0.02;
  rig.backPanel.rotation.z = -0.08 + Math.sin(t * 0.9) * 0.015;

  const blinkPhase = t % 4.2;
  const blink = blinkPhase > 4.05 ? 0.1 : 1;
  rig.eyeLeft.scale.y = 1.38 * blink;
  rig.eyeRight.scale.y = 1.38 * blink;
  rig.eyeLeft.pupil.position.x = state.pointerX * 0.014 * pointerLag;
  rig.eyeRight.pupil.position.x = state.pointerX * 0.014 * pointerLag;
  rig.eyeLeft.pupil.position.y = -0.004 - state.pointerY * 0.01 * pointerLag;
  rig.eyeRight.pupil.position.y = -0.004 - state.pointerY * 0.01 * pointerLag;
  rig.mouth.scale.set(1.15 + (state.speaking ? Math.sin(t * 14) * 0.18 : 0), 0.58, 1);

  rig.heart.visible = false;
  rig.heart.scale.setScalar(0.001);
}

function updateActionPose(t) {
  const elapsed = t - state.actionStarted;

  if (state.action === 'wave') {
    const duration = 2.4;
    const p = Math.min(elapsed / duration, 1);
    const envelope = Math.sin(p * Math.PI);
    rightArm.rotation.z = -0.4 - envelope * 1.42;
    rightArm.rotation.x = -0.2 - envelope * 0.36;
    rightForearm.rotation.z = -0.34 + Math.sin(elapsed * 14) * 0.5 * envelope;
    head.rotation.z -= 0.045 * envelope;
    finishActionIfNeeded(elapsed, duration);
  }

  if (state.action === 'nod') {
    const duration = 1.55;
    const p = Math.min(elapsed / duration, 1);
    const envelope = Math.sin(p * Math.PI);
    head.rotation.x += Math.sin(p * Math.PI * 4) * 0.15 * envelope;
    leftArm.rotation.z += 0.1 * envelope;
    rightArm.rotation.z -= 0.1 * envelope;
    finishActionIfNeeded(elapsed, duration);
  }

  if (state.action === 'turn') {
    const duration = 2.15;
    const p = Math.min(elapsed / duration, 1);
    avatar.rotation.y = state.dragYaw + easeInOut(p) * Math.PI * 2;
    body.position.y += Math.sin(p * Math.PI * 2) * 0.035;
    finishActionIfNeeded(elapsed, duration);
    return;
  }

  if (state.action === 'heart') {
    const duration = 2.25;
    const p = Math.min(elapsed / duration, 1);
    const envelope = Math.sin(p * Math.PI);
    leftArm.rotation.z = 0.74 * envelope + 0.3 * (1 - envelope);
    rightArm.rotation.z = -0.74 * envelope - 0.3 * (1 - envelope);
    leftForearm.rotation.z = -0.72 * envelope;
    rightForearm.rotation.z = 0.72 * envelope;
    head.rotation.z += Math.sin(p * Math.PI * 2) * 0.04 * envelope;
    rig.heart.visible = true;
    rig.heart.position.y = 1.58 + easeOutCubic(p) * 0.42;
    rig.heart.scale.setScalar(0.24 * envelope + 0.001);
    finishActionIfNeeded(elapsed, duration);
  }

  if (state.action === 'voice') {
    const duration = state.speaking ? 4.2 : 2.1;
    const p = Math.min(elapsed / duration, 1);
    const envelope = Math.sin(p * Math.PI);
    rightArm.rotation.z = -0.82 * envelope - 0.32 * (1 - envelope);
    rightArm.rotation.x = -0.18 * envelope;
    rightForearm.rotation.z = -0.45 * envelope;
    leftArm.rotation.z = 0.22 + envelope * 0.14;
    rig.chestGlow.scale.x = 1 + Math.sin(t * 10) * 0.08 * (state.speaking ? 1 : envelope);
    if (!state.speaking) finishActionIfNeeded(elapsed, duration);
  }
}

function resize() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  const mobile = width < 720;
  camera.position.z = mobile ? 8.45 : 7.1;
  camera.position.y = mobile ? 0.38 : 0.24;
  avatar.position.set(mobile ? 0 : 0.76, mobile ? 0.34 : 0.3, 0);
  avatar.scale.setScalar(personas[state.activePersona].scale * (mobile ? 0.78 : 0.96));
  camera.updateProjectionMatrix();
}

function animate(time) {
  const t = time * 0.001;
  updateBasePose(t);
  updateActionPose(t);

  if (state.action !== 'turn') {
    const viewYaw = state.dragYaw + state.pointerX * 0.04;
    avatar.rotation.y += (viewYaw - avatar.rotation.y) * 0.08;
  }

  rig.floor.rotation.z = t * 0.12;
  rig.orbit.rotation.z = t * 0.08;
  rig.particles.rotation.y = t * 0.026;
  rig.particles.rotation.x = Math.sin(t * 0.22) * 0.04;

  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}

function updatePointer(event) {
  const x = event.clientX / window.innerWidth - 0.5;
  const y = event.clientY / window.innerHeight - 0.5;
  state.pointerX = Math.max(-1, Math.min(1, x * 2));
  state.pointerY = Math.max(-1, Math.min(1, y * 2));
  state.lastPointerMovedAt = performance.now() * 0.001;
}

function stopCurrentAudio() {
  if (state.currentAudio) {
    try { state.currentAudio.pause(); } catch (error) {}
    state.currentAudio = null;
  }
  state.speaking = false;
}

function requestVoice() {
  const persona = personas[state.activePersona];
  if (!voiceEnabledInPage) {
    lineEl.textContent = '启动本地后端后，我就可以出声。';
    serverStateEl.textContent = 'voice offline';
    return;
  }
  stopCurrentAudio();
  serverStateEl.textContent = 'voice loading';
  state.speaking = true;
  fetch(`${voiceApiBase}/api/voice/speak`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: persona.voiceLine,
      persona: persona.id,
      relationship: 'lover',
      mood: state.activePersona === 'female' ? 'happy' : 'calm'
    })
  }).then((response) => {
    const type = response.headers.get('content-type') || '';
    if (!response.ok || !type.includes('audio')) {
      throw new Error(`voice response ${response.status}`);
    }
    return response.blob();
  }).then((blob) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    state.currentAudio = audio;
    audio.onended = audio.onerror = () => {
      URL.revokeObjectURL(url);
      state.currentAudio = null;
      state.speaking = false;
      serverStateEl.textContent = 'voice online';
    };
    serverStateEl.textContent = 'speaking';
    audio.play().catch(() => {
      URL.revokeObjectURL(url);
      state.currentAudio = null;
      state.speaking = false;
      serverStateEl.textContent = 'tap blocked';
    });
  }).catch(() => {
    state.speaking = false;
    state.voiceError = '语音请求失败';
    serverStateEl.textContent = 'voice error';
    lineEl.textContent = '声音服务暂时没有接上，先检查 8766 后端。';
  });
}

function checkVoiceStatus() {
  if (!voiceEnabledInPage) {
    serverStateEl.textContent = 'offline wallpaper';
    return;
  }
  fetch(`${voiceApiBase}/api/voice/status`)
    .then((response) => response.ok ? response.json() : null)
    .then((status) => {
      if (!status) return;
      state.voiceReady = !!status.enabled;
      serverStateEl.textContent = status.enabled ? 'voice online' : 'voice standby';
      if (status.cast && status.cast.voice) {
        serverStateEl.title = status.cast.voice;
      }
    })
    .catch(() => {
      state.voiceReady = false;
      serverStateEl.textContent = 'voice offline';
    });
}

canvas.addEventListener('pointerdown', (event) => {
  state.isDragging = true;
  state.dragStartX = event.clientX;
  state.dragStartYaw = state.dragYaw;
  canvas.setPointerCapture(event.pointerId);
  updatePointer(event);
});

canvas.addEventListener('pointermove', (event) => {
  updatePointer(event);
  if (!state.isDragging) return;
  const deltaX = event.clientX - state.dragStartX;
  state.dragYaw = state.dragStartYaw + deltaX * 0.008;
});

canvas.addEventListener('pointerup', (event) => {
  state.isDragging = false;
  canvas.releasePointerCapture(event.pointerId);
});

canvas.addEventListener('pointercancel', () => {
  state.isDragging = false;
});

canvas.addEventListener('click', () => {
  if (state.action === 'idle') {
    setAction('wave');
  }
});

window.addEventListener('pointermove', updatePointer);
window.addEventListener('resize', resize);

personaButtons.female.addEventListener('click', () => setPersona('female'));
personaButtons.male.addEventListener('click', () => setPersona('male'));
actionButtons.forEach((button) => {
  button.addEventListener('click', () => setAction(button.dataset.action));
});

buildStage();
buildCharacter();
setPersona(state.activePersona);
setAction('idle');
checkVoiceStatus();
resize();
requestAnimationFrame(animate);
