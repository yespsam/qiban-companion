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

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0x000000, 0);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
camera.position.set(0, 0.15, 7.4);

const personas = {
  female: {
    name: '小栖',
    idleLine: '我在桌面旁边，等你随时叫我。',
    actionLines: {
      idle: '我在桌面旁边，等你随时叫我。',
      wave: '看到你啦，我一直在。',
      nod: '嗯，我听着。',
      turn: '换个角度，也还是陪着你。',
      heart: '收到，我会认真回应你。'
    },
    hair: 0x2d2338,
    hairLight: 0x70518d,
    outfit: 0x173d35,
    accent: 0x07c160,
    eyes: 0x34b6ff,
    cheek: 0xff9ab4,
    twinTails: true,
    skirt: true,
    scale: 1
  },
  male: {
    name: '栖安',
    idleLine: '我在这里，先把心放稳。',
    actionLines: {
      idle: '我在这里，先把心放稳。',
      wave: '我看见你了，先慢慢来。',
      nod: '我明白，我们一步一步处理。',
      turn: '我换个位置，继续守着你。',
      heart: '放心，我会把你的话放在心上。'
    },
    hair: 0x1c2430,
    hairLight: 0x4f6f86,
    outfit: 0x253a48,
    accent: 0x6fb58a,
    eyes: 0x8bd7ff,
    cheek: 0xf2a58f,
    twinTails: false,
    skirt: false,
    scale: 1.04
  }
};

const state = {
  activePersona: 'female',
  action: 'idle',
  actionStarted: 0,
  dragYaw: 0,
  pointerX: 0,
  pointerY: 0,
  isDragging: false,
  dragStartX: 0,
  dragStartYaw: 0,
  lastPointerMovedAt: 0
};

const rig = {};

const mats = {
  skin: new THREE.MeshToonMaterial({ color: 0xffd8c8 }),
  skinSoft: new THREE.MeshToonMaterial({ color: 0xffc9c0 }),
  hair: new THREE.MeshToonMaterial({ color: personas.female.hair }),
  hairLight: new THREE.MeshToonMaterial({ color: personas.female.hairLight }),
  outfit: new THREE.MeshToonMaterial({ color: personas.female.outfit }),
  accent: new THREE.MeshToonMaterial({ color: personas.female.accent }),
  white: new THREE.MeshBasicMaterial({ color: 0xfff6ef }),
  dark: new THREE.MeshBasicMaterial({ color: 0x1a1014 }),
  cheek: new THREE.MeshBasicMaterial({ color: personas.female.cheek, transparent: true, opacity: 0.48 }),
  heart: new THREE.MeshToonMaterial({ color: 0xff6f9a }),
  floor: new THREE.MeshBasicMaterial({ color: 0x07110d, transparent: true, opacity: 0.34 }),
  particle: new THREE.PointsMaterial({ color: 0xc8ead7, size: 0.026, transparent: true, opacity: 0.58 }),
  outline: new THREE.MeshBasicMaterial({ color: 0x140d12, side: THREE.BackSide })
};

const ambient = new THREE.AmbientLight(0xffffff, 1.25);
scene.add(ambient);

const keyLight = new THREE.DirectionalLight(0xf8ffe9, 3.6);
keyLight.position.set(-3.4, 4.2, 4);
scene.add(keyLight);

const fillLight = new THREE.PointLight(0xffa4ba, 1.8, 8);
fillLight.position.set(3.1, 1.8, 2.8);
scene.add(fillLight);

const rimLight = new THREE.PointLight(personas.female.accent, 3, 9);
rimLight.position.set(2.8, -0.6, 3.4);
scene.add(rimLight);

const avatar = new THREE.Group();
scene.add(avatar);

const body = new THREE.Group();
const head = new THREE.Group();
const leftArm = new THREE.Group();
const rightArm = new THREE.Group();
const leftForearm = new THREE.Group();
const rightForearm = new THREE.Group();
const leftLeg = new THREE.Group();
const rightLeg = new THREE.Group();
const twinTailLeft = new THREE.Group();
const twinTailRight = new THREE.Group();

avatar.add(body);
body.add(head, leftArm, rightArm, leftLeg, rightLeg);
head.add(twinTailLeft, twinTailRight);

rig.avatar = avatar;
rig.body = body;
rig.head = head;
rig.leftArm = leftArm;
rig.rightArm = rightArm;
rig.leftForearm = leftForearm;
rig.rightForearm = rightForearm;
rig.leftLeg = leftLeg;
rig.rightLeg = rightLeg;
rig.twinTailLeft = twinTailLeft;
rig.twinTailRight = twinTailRight;

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
  const mesh = outlinedMesh(geometry, material, options.outlineScale || 1.035);
  if (options.position) mesh.position.set(...options.position);
  if (options.scale) mesh.scale.set(...options.scale);
  if (options.rotation) mesh.rotation.set(...options.rotation);
  parent.add(mesh);
  return mesh;
}

function addPlain(parent, geometry, material, options = {}) {
  const mesh = new THREE.Mesh(geometry, material);
  if (options.position) mesh.position.set(...options.position);
  if (options.scale) mesh.scale.set(...options.scale);
  if (options.rotation) mesh.rotation.set(...options.rotation);
  parent.add(mesh);
  return mesh;
}

function makeCapsule(radius, length, segments = 10, radial = 22) {
  return new THREE.CapsuleGeometry(radius, length, segments, radial);
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
  const floor = addPlain(
    avatar,
    new THREE.CircleGeometry(1.72, 80),
    mats.floor,
    { position: [0, -1.26, 0], rotation: [-Math.PI / 2, 0, 0], scale: [1.18, 0.62, 1] }
  );
  rig.floor = floor;

  const particlesGeometry = new THREE.BufferGeometry();
  const count = 180;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    positions[i * 3] = (Math.random() - 0.5) * 9;
    positions[i * 3 + 1] = -1.2 + Math.random() * 4.2;
    positions[i * 3 + 2] = -3.6 + Math.random() * 2.4;
  }
  particlesGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  rig.particles = new THREE.Points(particlesGeometry, mats.particle);
  scene.add(rig.particles);
}

function buildCharacter() {
  body.position.set(0, -0.03, 0);
  head.position.set(0, 0.72, 0.02);

  rig.neck = addPart(body, new THREE.CylinderGeometry(0.12, 0.13, 0.25, 20), mats.skin, {
    position: [0, 0.38, 0],
    outlineScale: 1.04
  });
  rig.torso = addPart(body, makeCapsule(0.28, 0.56, 12, 28), mats.outfit, {
    position: [0, -0.12, 0],
    scale: [1.04, 1.08, 0.74],
    outlineScale: 1.04
  });
  rig.chestRibbon = addPart(body, new THREE.BoxGeometry(0.42, 0.08, 0.05), mats.accent, {
    position: [0, 0.16, 0.24],
    rotation: [0, 0, 0.12],
    outlineScale: 1.03
  });
  rig.skirt = addPart(body, new THREE.CylinderGeometry(0.58, 0.74, 0.38, 6), mats.outfit, {
    position: [0, -0.68, 0],
    scale: [1, 1, 0.74],
    outlineScale: 1.035
  });
  rig.jacketHem = addPart(body, new THREE.CylinderGeometry(0.44, 0.52, 0.26, 8), mats.outfit, {
    position: [0, -0.62, 0],
    scale: [1, 1, 0.72],
    outlineScale: 1.035
  });

  leftArm.position.set(-0.46, 0.18, 0);
  rightArm.position.set(0.46, 0.18, 0);
  leftForearm.position.set(0, -0.5, 0);
  rightForearm.position.set(0, -0.5, 0);
  leftArm.add(leftForearm);
  rightArm.add(rightForearm);

  rig.leftUpperArm = addPart(leftArm, makeCapsule(0.07, 0.42, 8, 18), mats.outfit, {
    position: [0, -0.24, 0],
    outlineScale: 1.05
  });
  rig.rightUpperArm = addPart(rightArm, makeCapsule(0.07, 0.42, 8, 18), mats.outfit, {
    position: [0, -0.24, 0],
    outlineScale: 1.05
  });
  rig.leftLowerArm = addPart(leftForearm, makeCapsule(0.06, 0.38, 8, 18), mats.skin, {
    position: [0, -0.18, 0],
    outlineScale: 1.05
  });
  rig.rightLowerArm = addPart(rightForearm, makeCapsule(0.06, 0.38, 8, 18), mats.skin, {
    position: [0, -0.18, 0],
    outlineScale: 1.05
  });
  rig.leftHand = addPart(leftForearm, new THREE.SphereGeometry(0.085, 18, 14), mats.skin, {
    position: [0, -0.42, 0],
    outlineScale: 1.05
  });
  rig.rightHand = addPart(rightForearm, new THREE.SphereGeometry(0.085, 18, 14), mats.skin, {
    position: [0, -0.42, 0],
    outlineScale: 1.05
  });

  leftLeg.position.set(-0.18, -0.9, 0);
  rightLeg.position.set(0.18, -0.9, 0);
  rig.leftLegMesh = addPart(leftLeg, makeCapsule(0.075, 0.44, 8, 18), mats.outfit, {
    position: [0, -0.22, 0],
    outlineScale: 1.05
  });
  rig.rightLegMesh = addPart(rightLeg, makeCapsule(0.075, 0.44, 8, 18), mats.outfit, {
    position: [0, -0.22, 0],
    outlineScale: 1.05
  });
  rig.leftFoot = addPart(leftLeg, new THREE.BoxGeometry(0.24, 0.09, 0.28), mats.dark, {
    position: [0.01, -0.48, 0.08],
    rotation: [0.08, 0, 0],
    outlineScale: 1.04
  });
  rig.rightFoot = addPart(rightLeg, new THREE.BoxGeometry(0.24, 0.09, 0.28), mats.dark, {
    position: [-0.01, -0.48, 0.08],
    rotation: [0.08, 0, 0],
    outlineScale: 1.04
  });

  rig.headMesh = addPart(head, new THREE.SphereGeometry(0.46, 36, 24), mats.skin, {
    scale: [0.96, 1.08, 0.9],
    outlineScale: 1.035
  });
  rig.earLeft = addPart(head, new THREE.SphereGeometry(0.07, 14, 10), mats.skinSoft, {
    position: [-0.42, -0.02, 0.02],
    scale: [0.7, 1.1, 0.42],
    outlineScale: 1.04
  });
  rig.earRight = addPart(head, new THREE.SphereGeometry(0.07, 14, 10), mats.skinSoft, {
    position: [0.42, -0.02, 0.02],
    scale: [0.7, 1.1, 0.42],
    outlineScale: 1.04
  });
  rig.hairCap = addPart(head, new THREE.SphereGeometry(0.49, 36, 18, 0, Math.PI * 2, 0, Math.PI * 0.64), mats.hair, {
    position: [0, 0.08, -0.02],
    scale: [1.06, 0.98, 0.98],
    outlineScale: 1.035
  });
  rig.backHair = addPart(head, makeCapsule(0.24, 0.42, 10, 20), mats.hair, {
    position: [0, -0.2, -0.31],
    scale: [1.38, 1.04, 0.7],
    outlineScale: 1.035
  });

  const bangGeo = new THREE.ConeGeometry(0.115, 0.42, 7);
  rig.bangCenter = addPart(head, bangGeo, mats.hairLight, {
    position: [0, 0.17, 0.35],
    rotation: [0.18, 0, Math.PI],
    scale: [1, 1.08, 0.72]
  });
  rig.bangLeft = addPart(head, bangGeo, mats.hair, {
    position: [-0.18, 0.14, 0.32],
    rotation: [0.12, 0.15, Math.PI + 0.28],
    scale: [0.9, 0.94, 0.68]
  });
  rig.bangRight = addPart(head, bangGeo, mats.hair, {
    position: [0.18, 0.14, 0.32],
    rotation: [0.12, -0.15, Math.PI - 0.28],
    scale: [0.9, 0.94, 0.68]
  });

  buildEyes();
  buildTwinTails();
  buildHeart();
}

function buildEyes() {
  const eyeWhiteGeo = new THREE.CircleGeometry(0.105, 32);
  const pupilGeo = new THREE.CircleGeometry(0.052, 32);
  const highlightGeo = new THREE.CircleGeometry(0.018, 16);
  const cheekGeo = new THREE.CircleGeometry(0.052, 20);

  rig.eyeLeft = new THREE.Group();
  rig.eyeRight = new THREE.Group();
  rig.eyeLeft.position.set(-0.18, 0.02, 0.42);
  rig.eyeRight.position.set(0.18, 0.02, 0.42);
  rig.eyeLeft.scale.set(0.82, 1.34, 1);
  rig.eyeRight.scale.set(0.82, 1.34, 1);
  head.add(rig.eyeLeft, rig.eyeRight);

  for (const eye of [rig.eyeLeft, rig.eyeRight]) {
    addPlain(eye, eyeWhiteGeo, mats.white);
    const pupil = addPlain(eye, pupilGeo, mats.accent, { position: [0, -0.004, 0.006] });
    const highlight = addPlain(eye, highlightGeo, mats.white, { position: [-0.025, 0.034, 0.012] });
    eye.pupil = pupil;
    eye.highlight = highlight;
  }

  rig.cheekLeft = addPlain(head, cheekGeo, mats.cheek, {
    position: [-0.28, -0.12, 0.423],
    scale: [1.5, 0.62, 1]
  });
  rig.cheekRight = addPlain(head, cheekGeo, mats.cheek, {
    position: [0.28, -0.12, 0.423],
    scale: [1.5, 0.62, 1]
  });
  rig.mouth = addPlain(head, new THREE.TorusGeometry(0.064, 0.006, 8, 28, Math.PI), mats.dark, {
    position: [0, -0.18, 0.43],
    rotation: [0, 0, Math.PI],
    scale: [1.15, 0.62, 1]
  });
}

function buildTwinTails() {
  twinTailLeft.position.set(-0.47, -0.12, -0.08);
  twinTailRight.position.set(0.47, -0.12, -0.08);
  addPart(twinTailLeft, makeCapsule(0.15, 0.62, 10, 20), mats.hair, {
    position: [0, -0.28, 0],
    rotation: [0.15, 0.05, -0.22],
    scale: [0.82, 1, 0.72]
  });
  addPart(twinTailRight, makeCapsule(0.15, 0.62, 10, 20), mats.hair, {
    position: [0, -0.28, 0],
    rotation: [0.15, -0.05, 0.22],
    scale: [0.82, 1, 0.72]
  });
  rig.tailTipLeft = addPart(twinTailLeft, new THREE.SphereGeometry(0.13, 18, 12), mats.hairLight, {
    position: [-0.04, -0.62, 0.02],
    scale: [0.85, 1.2, 0.72]
  });
  rig.tailTipRight = addPart(twinTailRight, new THREE.SphereGeometry(0.13, 18, 12), mats.hairLight, {
    position: [0.04, -0.62, 0.02],
    scale: [0.85, 1.2, 0.72]
  });
}

function buildHeart() {
  const heart = outlinedMesh(makeHeartGeometry(), mats.heart, 1.045);
  heart.position.set(0, 1.58, 0.72);
  heart.scale.setScalar(0.001);
  heart.visible = false;
  avatar.add(heart);
  rig.heart = heart;
}

function easeOutCubic(x) {
  return 1 - Math.pow(1 - x, 3);
}

function easeInOut(x) {
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

function setPersona(id) {
  state.activePersona = id;
  const persona = personas[id];
  mats.hair.color.setHex(persona.hair);
  mats.hairLight.color.setHex(persona.hairLight);
  mats.outfit.color.setHex(persona.outfit);
  mats.accent.color.setHex(persona.accent);
  mats.cheek.color.setHex(persona.cheek);
  rimLight.color.setHex(persona.accent);
  fillLight.color.setHex(id === 'female' ? 0xffa4ba : 0x9cc8ff);
  rig.twinTailLeft.visible = persona.twinTails;
  rig.twinTailRight.visible = persona.twinTails;
  rig.skirt.visible = persona.skirt;
  rig.jacketHem.visible = !persona.skirt;
  rig.bangCenter.scale.set(id === 'female' ? 1 : 0.78, id === 'female' ? 1.08 : 0.82, 0.72);
  rig.backHair.scale.set(id === 'female' ? 1.38 : 1.18, id === 'female' ? 1.04 : 0.62, 0.7);
  avatar.scale.setScalar(persona.scale);
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
}

function finishActionIfNeeded(elapsed, duration) {
  if (elapsed >= duration && state.action !== 'idle') {
    if (state.action === 'turn') {
      state.dragYaw += Math.PI * 2;
    }
    setAction('idle');
  }
}

function updateBasePose(t) {
  const breath = Math.sin(t * 2.1) * 0.025;
  const sway = Math.sin(t * 0.78) * 0.035;
  const pointerLag = Math.max(0, 1 - (t - state.lastPointerMovedAt) / 3);

  body.position.y = -0.03 + breath * 0.45;
  body.rotation.z = sway * 0.5;
  body.scale.set(1 + breath * 0.35, 1 + breath, 1);
  head.rotation.x = -state.pointerY * 0.16 * pointerLag + Math.sin(t * 1.1) * 0.018;
  head.rotation.y = state.pointerX * 0.26 * pointerLag;
  head.rotation.z = -sway * 0.62;

  leftArm.rotation.set(0.02, 0.08, 0.32 + sway * 0.25);
  rightArm.rotation.set(0.02, -0.08, -0.32 + sway * 0.25);
  leftForearm.rotation.set(0.02, 0, 0.12);
  rightForearm.rotation.set(0.02, 0, -0.12);
  leftLeg.rotation.set(0, 0, 0.05 - sway * 0.16);
  rightLeg.rotation.set(0, 0, -0.05 - sway * 0.16);

  twinTailLeft.rotation.z = -0.08 + Math.sin(t * 1.5) * 0.055;
  twinTailRight.rotation.z = 0.08 + Math.sin(t * 1.5 + 0.5) * 0.055;

  const blinkPhase = t % 4.4;
  const blink = blinkPhase > 4.24 ? 0.08 : 1;
  rig.eyeLeft.scale.y = 1.34 * blink;
  rig.eyeRight.scale.y = 1.34 * blink;
  rig.eyeLeft.pupil.position.x = state.pointerX * 0.018 * pointerLag;
  rig.eyeRight.pupil.position.x = state.pointerX * 0.018 * pointerLag;
  rig.eyeLeft.pupil.position.y = -0.004 - state.pointerY * 0.012 * pointerLag;
  rig.eyeRight.pupil.position.y = -0.004 - state.pointerY * 0.012 * pointerLag;
  rig.mouth.scale.set(1.15, 0.62, 1);

  rig.heart.visible = false;
  rig.heart.scale.setScalar(0.001);
}

function updateActionPose(t) {
  const elapsed = t - state.actionStarted;

  if (state.action === 'wave') {
    const duration = 2.4;
    const p = Math.min(elapsed / duration, 1);
    const envelope = Math.sin(p * Math.PI);
    rightArm.rotation.z = -0.42 - envelope * 1.48;
    rightArm.rotation.x = -0.16 - envelope * 0.35;
    rightForearm.rotation.z = -0.34 + Math.sin(elapsed * 14) * 0.56 * envelope;
    head.rotation.z -= 0.06 * envelope;
    rig.mouth.scale.x = 1.15 + envelope * 0.28;
    finishActionIfNeeded(elapsed, duration);
  }

  if (state.action === 'nod') {
    const duration = 1.55;
    const p = Math.min(elapsed / duration, 1);
    const envelope = Math.sin(p * Math.PI);
    head.rotation.x += Math.sin(p * Math.PI * 4) * 0.18 * envelope;
    leftArm.rotation.z += 0.12 * envelope;
    rightArm.rotation.z -= 0.12 * envelope;
    finishActionIfNeeded(elapsed, duration);
  }

  if (state.action === 'turn') {
    const duration = 2.15;
    const p = Math.min(elapsed / duration, 1);
    avatar.rotation.y = state.dragYaw + easeInOut(p) * Math.PI * 2;
    body.position.y += Math.sin(p * Math.PI * 2) * 0.05;
    finishActionIfNeeded(elapsed, duration);
    return;
  }

  if (state.action === 'heart') {
    const duration = 2.25;
    const p = Math.min(elapsed / duration, 1);
    const envelope = Math.sin(p * Math.PI);
    leftArm.rotation.z = 1.08 * envelope + 0.28 * (1 - envelope);
    rightArm.rotation.z = -1.08 * envelope - 0.28 * (1 - envelope);
    leftForearm.rotation.z = -0.9 * envelope;
    rightForearm.rotation.z = 0.9 * envelope;
    head.rotation.z += Math.sin(p * Math.PI * 2) * 0.055 * envelope;
    rig.heart.visible = true;
    rig.heart.position.y = 1.46 + easeOutCubic(p) * 0.42;
    rig.heart.scale.setScalar(0.31 * envelope + 0.001);
    finishActionIfNeeded(elapsed, duration);
  }
}

function resize() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  const mobile = width < 720;
  camera.position.z = mobile ? 7.6 : 6.2;
  camera.position.y = mobile ? 0.16 : 0.08;
  avatar.position.set(mobile ? 0 : 0.72, mobile ? -0.16 : -0.18, 0);
  avatar.scale.setScalar(personas[state.activePersona].scale * (mobile ? 0.92 : 1.16));
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

  rig.floor.rotation.z = t * 0.16;
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

const shouldCheckVoice = new URLSearchParams(window.location.search).get('voice') === '1';
if (shouldCheckVoice) {
  fetch('http://127.0.0.1:8766/api/voice/status')
    .then((response) => response.ok ? response.json() : null)
    .then((status) => {
      if (!status) return;
      serverStateEl.textContent = status.enabled ? 'voice online' : 'voice standby';
    })
    .catch(() => {
      serverStateEl.textContent = 'offline wallpaper';
    });
} else {
  serverStateEl.textContent = 'offline wallpaper';
}

buildStage();
buildCharacter();
setPersona(state.activePersona);
setAction('idle');
resize();
requestAnimationFrame(animate);
