import * as THREE from './vendor/three.module.js';
import { GLTFLoader } from './vendor/GLTFLoader.js';

const canvas = document.getElementById('scene');
const nameEl = document.getElementById('name');
const lineEl = document.getElementById('line');
const serverStateEl = document.getElementById('server-state');
const dockEl = document.querySelector('.dock');
const menuButton = document.getElementById('menu-btn');
const dialogButton = document.getElementById('dialog-btn');
const voiceButton = document.getElementById('voice-btn');
const builderButton = document.getElementById('builder-btn');
const voicePanel = document.getElementById('voice-panel');
const builderPanel = document.getElementById('builder-panel');
const personaButtons = {
  female: document.getElementById('female-btn'),
  male: document.getElementById('male-btn')
};
const actionButtons = [...document.querySelectorAll('[data-action]')];

const params = new URLSearchParams(window.location.search);

function storedValue(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function storeValue(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
  }
}

function enabledParam(name, fallback = false) {
  const raw = params.get(name);
  if (raw === null) return fallback;
  return ['1', 'true', 'yes', 'on'].includes(raw.toLowerCase());
}

function normalizeVoiceArchetype(value) {
  const raw = (value || '').trim();
  return raw === 'default' || raw === 'auto' ? '' : raw;
}

function voiceChoiceKey(personaId) {
  return `qiban-voice-archetype-${personaId}`;
}

function skinChoiceKey(personaId) {
  return `qiban-skin-v026-${personaId}`;
}

function motionChoiceKey() {
  return 'qiban-motion-style-v026';
}

function hasStoredVoiceChoice(personaId) {
  return params.has('archetype') || storedValue(voiceChoiceKey(personaId)) !== null;
}

function storedVoiceArchetype(personaId) {
  return normalizeVoiceArchetype(params.get('archetype') || storedValue(voiceChoiceKey(personaId)));
}

function resolveApiBase() {
  const explicit = params.get('api');
  if (explicit) return explicit.replace(/\/+$/, '');
  const storedPort = storedValue('qiban-api-port');
  const hasExplicitPort = params.has('apiPort') || params.has('port') || !!storedPort;
  const hostname = window.location.hostname || '';
  const isLocalHost = ['localhost', '127.0.0.1', '0.0.0.0', ''].includes(hostname) || hostname.endsWith('.local');
  if (!hasExplicitPort && window.location.protocol !== 'file:' && !isLocalHost) {
    return window.location.origin.replace(/\/+$/, '');
  }
  const apiPort = params.get('apiPort') || params.get('port') || storedPort || '8766';
  if (apiPort === 'same') return window.location.origin.replace(/\/+$/, '');
  const protocol = window.location.protocol === 'file:' ? 'http:' : window.location.protocol;
  const host = params.get('apiHost') || hostname || '127.0.0.1';
  return `${protocol}//${host}:${apiPort}`;
}

const voiceApiEnabledInPage = enabledParam('voice', true);
const browserVoiceFallbackEnabled = enabledParam('browserVoice', false);
const dialogEnabledInPage = enabledParam('dialog', storedValue('qiban-dialog') === '1');
const voiceApiBase = resolveApiBase();
const forcedIdlePoseTime = Number.isFinite(Number(params.get('poseTime'))) ? Number(params.get('poseTime')) : null;
const stageEnabled = enabledParam('stage', false);
const controlsOpenInPage = enabledParam('controls', false);

const modelAssetVersion = 'v0.2.8-model-load';
const modelUrl = (path) => `${path}?v=${modelAssetVersion}`;

const modelAssets = {
  female: {
    model: modelUrl('./assets/models/xiao-qi.glb'),
    animations: {
      walk: modelUrl('./assets/models/xiao-qi-walk.glb'),
      run: modelUrl('./assets/models/xiao-qi-run.glb')
    }
  },
  male: {
    model: modelUrl('./assets/models/qi-an.glb'),
    animations: {
      walk: modelUrl('./assets/models/qi-an-walk.glb'),
      run: modelUrl('./assets/models/qi-an-run.glb')
    }
  }
};

const runtimeModelActions = new Set([]);
const loopingModelActions = new Set([]);
const gltfLoader = new GLTFLoader();

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 3));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.12;
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
      walk: '我陪你走一会儿。',
      run: '现在开始加速。',
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
    idlePoseTime: 0.18,
    modelScaleDesktop: 0.78,
    modelScaleMobile: 0.9,
    modelYDesktop: -0.14,
    modelYMobile: -0.12,
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
      walk: '我陪你走一段。',
      run: '需要冲刺时，我跟得上。',
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
    idlePoseTime: 0.9,
    modelScaleDesktop: 0.74,
    modelScaleMobile: 0.82,
    modelYDesktop: -0.26,
    modelYMobile: -0.22,
    shoulder: 1.04,
    hip: 0.76,
    stance: 0.14,
    legSkin: false,
    longHair: false
  }
};

const skinPresets = {
  female: [
    {
      id: 'qiban',
      name: '栖白',
      line: '白色外套和青绿光点，是最接近我的日常样子。',
      accent: 0x07c160,
      accentCss: '#07c160',
      warmCss: '#ff9ab4',
      tint: 0xffffff,
      tintStrength: 0,
      emissive: 0.02,
      exposure: 1.12,
      accessories: { halo: false, ribbons: true, cape: false, orbit: false, badge: true }
    },
    {
      id: 'sakura',
      name: '樱糖',
      line: '今天换成软一点的粉色，陪你轻松一点。',
      accent: 0xff7eb6,
      accentCss: '#ff7eb6',
      warmCss: '#ffe16b',
      tint: 0xffd6ea,
      tintStrength: 0.18,
      emissive: 0.05,
      exposure: 1.16,
      accessories: { halo: true, ribbons: true, cape: false, orbit: false, badge: true }
    },
    {
      id: 'aurora',
      name: '极光',
      line: '极光模式启动，我会更醒目地站在你身边。',
      accent: 0x66e8ff,
      accentCss: '#66e8ff',
      warmCss: '#a884ff',
      tint: 0xb8f4ff,
      tintStrength: 0.2,
      emissive: 0.08,
      exposure: 1.2,
      accessories: { halo: true, ribbons: false, cape: false, orbit: true, badge: true }
    }
  ],
  male: [
    {
      id: 'qiban',
      name: '栖白',
      line: '白色外套和青绿眼睛，是我默认守在这里的样子。',
      accent: 0x7dda96,
      accentCss: '#7dda96',
      warmCss: '#9cc8ff',
      tint: 0xffffff,
      tintStrength: 0,
      emissive: 0.02,
      exposure: 1.1,
      accessories: { halo: false, ribbons: false, cape: false, orbit: false, badge: true }
    },
    {
      id: 'night',
      name: '夜航',
      line: '夜航形态适合安静陪伴，动作会更沉稳。',
      accent: 0x5bd8ff,
      accentCss: '#5bd8ff',
      warmCss: '#8c7bff',
      tint: 0x9fd7ff,
      tintStrength: 0.16,
      emissive: 0.06,
      exposure: 1.12,
      accessories: { halo: false, ribbons: false, cape: false, orbit: true, badge: true }
    },
    {
      id: 'ember',
      name: '曜黑',
      line: '曜黑形态会更有存在感，适合需要一点力量的时候。',
      accent: 0xffc457,
      accentCss: '#ffc457',
      warmCss: '#ff6a7a',
      tint: 0xffdf9c,
      tintStrength: 0.18,
      emissive: 0.07,
      exposure: 1.15,
      accessories: { halo: true, ribbons: false, cape: false, orbit: false, badge: true }
    }
  ]
};

const motionProfiles = {
  gentle: {
    name: '温柔',
    breath: 0.82,
    sway: 0.72,
    speed: 0.9,
    action: 0.92,
    gaze: 0.7,
    actions: ['voice', 'nod', 'heart', 'wave']
  },
  lively: {
    name: '元气',
    breath: 1.16,
    sway: 1.24,
    speed: 1.12,
    action: 1.08,
    gaze: 1,
    actions: ['wave', 'heart', 'run', 'voice']
  },
  steady: {
    name: '稳重',
    breath: 0.7,
    sway: 0.58,
    speed: 0.82,
    action: 0.86,
    gaze: 0.52,
    actions: ['nod', 'voice', 'walk', 'heart']
  }
};

const builderSteps = [
  { id: 'persona', name: '角色' },
  { id: 'skin', name: '皮肤' },
  { id: 'motion', name: '动作' },
  { id: 'voice', name: '声音' }
];

const defaultSkinIds = {
  female: 'sakura',
  male: 'night'
};

function storedSkinId(personaId) {
  const presets = skinPresets[personaId] || skinPresets.female;
  const requested = params.get('skin') || storedValue(skinChoiceKey(personaId));
  const fallback = defaultSkinIds[personaId] || presets[0].id;
  return presets.some((skin) => skin.id === requested) ? requested : fallback;
}

function storedMotionStyle() {
  const requested = params.get('motion') || storedValue(motionChoiceKey());
  return motionProfiles[requested] ? requested : 'lively';
}

function currentSkin() {
  const presets = skinPresets[state.activePersona] || skinPresets.female;
  return presets.find((skin) => skin.id === state.activeSkin) || presets[0];
}

function currentMotionProfile() {
  return motionProfiles[state.motionStyle] || motionProfiles.gentle;
}

const fallbackVoiceResources = {
  female: [
    { id: 'default', archetype: '', name: '随身份', voice: 'zh-CN-XiaoxiaoNeural', rate: '+0%', pitch: '+0Hz' },
    { id: 'loli', archetype: 'loli', name: '萝莉音', voice: 'zh-CN-XiaoyiNeural', rate: '+12%', pitch: '+18Hz' },
    { id: 'yujie', archetype: 'yujie', name: '御姐音', voice: 'zh-CN-XiaoxiaoNeural', rate: '-8%', pitch: '-8Hz' },
    { id: 'funny', archetype: 'funny', name: '搞笑女', voice: 'zh-CN-XiaoyiNeural', rate: '+16%', pitch: '+10Hz' }
  ],
  male: [
    { id: 'default', archetype: '', name: '随身份', voice: 'zh-CN-YunxiNeural', rate: '+0%', pitch: '+0Hz' },
    { id: 'shonen', archetype: 'shonen', name: '少年音', voice: 'zh-CN-YunxiaNeural', rate: '+8%', pitch: '+12Hz' },
    { id: 'uncle', archetype: 'uncle', name: '大叔音', voice: 'zh-CN-YunjianNeural', rate: '-10%', pitch: '-8Hz' },
    { id: 'funny', archetype: 'funny', name: '搞笑男', voice: 'zh-CN-YunyangNeural', rate: '+16%', pitch: '+8Hz' }
  ]
};

const state = {
  activePersona: (params.get('persona') || storedValue('qiban-persona')) === 'male' ? 'male' : 'female',
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
  dialogEnabled: dialogEnabledInPage,
  activeVoiceArchetype: '',
  activeSkin: '',
  motionStyle: 'gentle',
  voiceResources: [],
  dockOpen: false,
  builderOpen: false,
  builderStep: 'persona',
  builderTimers: [],
  voicePanelOpen: false,
  interactionCount: 0,
  voiceLoading: false,
  speaking: false,
  awaitingPlayback: false,
  voiceRequestId: 0,
  currentAudio: null,
  currentAudioUrl: null,
  prefetchedVoiceBlob: null,
  prefetchedVoiceKey: '',
  voicePrefetchPromise: null
};
state.activeVoiceArchetype = storedVoiceArchetype(state.activePersona);
state.activeSkin = storedSkinId(state.activePersona);
state.motionStyle = storedMotionStyle();
state.voiceResources = fallbackVoiceResources[state.activePersona];

const modelState = {
  loaded: {},
  loading: {},
  active: null,
  layer: null,
  baseX: 0,
  baseY: 0.22,
  baseScale: 1,
  lastTime: 0
};

const rig = {
  femaleOnly: [],
  maleOnly: [],
  hairStrands: [],
  coatPanels: [],
  trimPieces: [],
  cosmetics: {}
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

const ambient = new THREE.AmbientLight(0xffffff, 0.82);
scene.add(ambient);

const hemiLight = new THREE.HemisphereLight(0xf4fff5, 0x17211d, 1.16);
scene.add(hemiLight);

const keyLight = new THREE.DirectionalLight(0xf8ffe9, 3.15);
keyLight.position.set(-3.2, 4.4, 4.4);
scene.add(keyLight);

const fillLight = new THREE.PointLight(0xffa4ba, 1.36, 8);
fillLight.position.set(3.1, 1.8, 2.8);
scene.add(fillLight);

const rimLight = new THREE.PointLight(personas.female.accent, 2.65, 9);
rimLight.position.set(2.8, -0.4, 3.2);
scene.add(rimLight);

const avatar = new THREE.Group();
const modelLayer = new THREE.Group();
const cosmeticLayer = new THREE.Group();
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
scene.add(modelLayer);
modelLayer.visible = false;
cosmeticLayer.name = 'qiban-cosmetics';
avatar.visible = false;
avatar.add(body);
body.add(head, leftArm, rightArm, leftLeg, rightLeg);
leftArm.add(leftForearm);
rightArm.add(rightForearm);
leftLeg.add(leftShin);
rightLeg.add(rightShin);

Object.assign(rig, {
  avatar, modelLayer, body, head, leftArm, rightArm, leftForearm, rightForearm,
  leftLeg, rightLeg, leftShin, rightShin
});
modelState.layer = modelLayer;
modelState.cosmeticLayer = cosmeticLayer;

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
  if (!stageEnabled) return;

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
  buildModelCosmetics();
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
  scene.add(rig.heart);
}

function makeCosmeticMaterial(opacity = 0.72) {
  return new THREE.MeshBasicMaterial({
    color: 0xffffff,
    transparent: true,
    opacity,
    side: THREE.DoubleSide,
    depthWrite: false
  });
}

function addCosmetic(geometry, opacity, options = {}) {
  const mesh = new THREE.Mesh(geometry, makeCosmeticMaterial(opacity));
  applyTransform(mesh, options);
  mesh.renderOrder = 3;
  cosmeticLayer.add(mesh);
  return mesh;
}

function buildModelCosmetics() {
  cosmeticLayer.clear();
  rig.cosmetics.halo = addCosmetic(new THREE.TorusGeometry(0.16, 0.006, 12, 96), 0.68, {
    position: [0, 0.92, -0.03],
    rotation: [Math.PI / 2, 0, 0],
    scale: [1, 0.7, 1]
  });
  rig.cosmetics.orbit = addCosmetic(new THREE.TorusGeometry(0.24, 0.0035, 8, 120), 0.2, {
    position: [0, 0.2, -0.05],
    rotation: [Math.PI / 2.7, 0, 0],
    scale: [1.08, 0.7, 1]
  });
  rig.cosmetics.badge = addCosmetic(new THREE.OctahedronGeometry(0.045, 0), 0.92, {
    position: [0.02, 0.25, 0.13],
    rotation: [0.15, 0.3, 0.1],
    scale: [1, 1.15, 1]
  });
  rig.cosmetics.capeLeft = addCosmetic(new THREE.PlaneGeometry(0.13, 0.34), 0.12, {
    position: [-0.2, 0.08, -0.08],
    rotation: [0.06, 0.2, 0.1]
  });
  rig.cosmetics.capeRight = addCosmetic(new THREE.PlaneGeometry(0.13, 0.34), 0.12, {
    position: [0.2, 0.08, -0.08],
    rotation: [0.06, -0.2, -0.1]
  });
  rig.cosmetics.ribbonLeft = addCosmetic(new THREE.ConeGeometry(0.045, 0.16, 4), 0.82, {
    position: [-0.25, 0.2, 0.12],
    rotation: [0.18, 0.1, 0.8],
    scale: [1.2, 0.72, 1]
  });
  rig.cosmetics.ribbonRight = addCosmetic(new THREE.ConeGeometry(0.045, 0.16, 4), 0.82, {
    position: [0.25, 0.2, 0.12],
    rotation: [0.18, -0.1, -0.8],
    scale: [1.2, 0.72, 1]
  });
  updateCosmeticLayer();
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
  storeValue('qiban-persona', id);
  clearVoicePrefetch();
  state.activeVoiceArchetype = storedVoiceArchetype(id);
  state.activeSkin = storedSkinId(id);
  state.voiceResources = fallbackVoiceResources[id];
  state.voicePanelOpen = false;
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
  applyPersonaSkin(false);
  updateDialogControls();
  updateVoiceControls();
  renderBuilderPanel();
  loadModel(id);
  activateLoadedModel(id);
  loadVoiceResources();
  resize();
}

function applyPersonaSkin(updateLine = true) {
  const skin = currentSkin();
  document.documentElement.style.setProperty('--accent', skin.accentCss || colorToCss(skin.accent));
  document.documentElement.style.setProperty('--warm', skin.warmCss || '#ff9ab4');
  renderer.toneMappingExposure = skin.exposure || 1.12;
  mats.accent.color.setHex(skin.accent);
  mats.glow.color.setHex(skin.accent);
  mats.panel.color.setHex(skin.accent);
  if (rig.heart && rig.heart.main) {
    rig.heart.main.material.color.setHex(skin.accent);
  }
  rimLight.color.setHex(skin.accent);
  fillLight.color.setHex(skin.accent);
  if (updateLine) {
    lineEl.textContent = skin.line || personas[state.activePersona].idleLine;
  }
  updateCosmeticLayer();
  const activeEntry = modelState.loaded[state.activePersona];
  if (activeEntry && modelState.active === activeEntry) {
    applyModelSkin(activeEntry);
  }
}

function setSkin(id, preview = true) {
  const presets = skinPresets[state.activePersona] || skinPresets.female;
  const selected = presets.find((skin) => skin.id === id) || presets[0];
  state.activeSkin = selected.id;
  storeValue(skinChoiceKey(state.activePersona), selected.id);
  applyPersonaSkin(true);
  renderBuilderPanel();
  if (preview) setAction('turn');
}

function setMotionStyle(id, preview = true) {
  state.motionStyle = motionProfiles[id] ? id : 'gentle';
  storeValue(motionChoiceKey(), state.motionStyle);
  renderBuilderPanel();
  if (preview) setAction(state.motionStyle === 'lively' ? 'wave' : state.motionStyle === 'steady' ? 'nod' : 'heart');
}

function setBuilderOpen(open) {
  if (open && !state.dockOpen) setDockOpen(true);
  state.builderOpen = open;
  if (builderPanel) builderPanel.hidden = !open;
  if (builderButton) {
    builderButton.classList.toggle('active', open);
    builderButton.setAttribute('aria-expanded', open ? 'true' : 'false');
  }
  if (open && state.voicePanelOpen) setVoicePanelOpen(false);
  renderBuilderPanel();
}

function setBuilderStep(stepId) {
  if (!builderSteps.some((step) => step.id === stepId)) return;
  state.builderStep = stepId;
  renderBuilderPanel();
}

function clearBuilderTimers() {
  state.builderTimers.forEach((timer) => window.clearTimeout(timer));
  state.builderTimers = [];
}

function queueBuilderAction(delay, action) {
  state.builderTimers.push(window.setTimeout(() => setAction(action), delay));
}

function runBuilderPreview() {
  clearBuilderTimers();
  applyPersonaSkin(true);
  setAction('turn');
  queueBuilderAction(900, currentMotionProfile().actions[0] || 'wave');
  queueBuilderAction(2600, currentMotionProfile().actions[1] || 'heart');
  if (state.dialogEnabled) {
    queueBuilderAction(4300, 'voice');
  }
}

function builderOption(label, active, onClick, swatch = '') {
  const option = document.createElement('button');
  option.className = 'builder-option';
  option.type = 'button';
  option.classList.toggle('active', !!active);
  if (swatch) {
    const color = document.createElement('span');
    color.className = 'builder-swatch';
    color.style.background = swatch;
    option.appendChild(color);
  }
  const text = document.createElement('span');
  text.textContent = label;
  option.appendChild(text);
  option.addEventListener('click', onClick);
  return option;
}

function renderBuilderPanel() {
  if (!builderPanel) return;
  builderPanel.hidden = !state.builderOpen;
  if (!state.builderOpen) return;
  builderPanel.textContent = '';

  const tabs = document.createElement('div');
  tabs.className = 'builder-steps';
  builderSteps.forEach((step, index) => {
    const tab = document.createElement('button');
    tab.className = 'builder-step';
    tab.type = 'button';
    tab.classList.toggle('active', step.id === state.builderStep);
    tab.textContent = `${index + 1} ${step.name}`;
    tab.addEventListener('click', () => setBuilderStep(step.id));
    tabs.appendChild(tab);
  });
  builderPanel.appendChild(tabs);

  const options = document.createElement('div');
  options.className = 'builder-options';

  if (state.builderStep === 'persona') {
    options.appendChild(builderOption('小栖', state.activePersona === 'female', () => {
      setPersona('female');
      setBuilderStep('skin');
    }, '#ff7eb6'));
    options.appendChild(builderOption('栖安', state.activePersona === 'male', () => {
      setPersona('male');
      setBuilderStep('skin');
    }, '#7dda96'));
  }

  if (state.builderStep === 'skin') {
    (skinPresets[state.activePersona] || []).forEach((skin) => {
      options.appendChild(builderOption(skin.name, state.activeSkin === skin.id, () => {
        setSkin(skin.id);
      }, skin.accentCss || colorToCss(skin.accent)));
    });
  }

  if (state.builderStep === 'motion') {
    Object.entries(motionProfiles).forEach(([id, profile]) => {
      options.appendChild(builderOption(profile.name, state.motionStyle === id, () => {
        setMotionStyle(id);
      }));
    });
    ['wave', 'nod', 'heart', 'walk', 'run'].forEach((action) => {
      const label = personas[state.activePersona].actionLines[action] ? actionButtons.find((button) => button.dataset.action === action)?.textContent || action : action;
      options.appendChild(builderOption(label, state.action === action, () => setAction(action)));
    });
  }

  if (state.builderStep === 'voice') {
    state.voiceResources.forEach((item) => {
      options.appendChild(builderOption(item.name || item.id, (item.archetype || '') === (state.activeVoiceArchetype || ''), () => {
        selectVoiceResource(item.archetype || '');
        setBuilderOpen(true);
        setBuilderStep('voice');
      }));
    });
  }

  builderPanel.appendChild(options);

  const footer = document.createElement('div');
  footer.className = 'builder-footer';
  const currentIndex = builderSteps.findIndex((step) => step.id === state.builderStep);
  const previous = document.createElement('button');
  previous.className = 'builder-command';
  previous.type = 'button';
  previous.textContent = '上一步';
  previous.disabled = currentIndex <= 0;
  previous.addEventListener('click', () => setBuilderStep(builderSteps[Math.max(0, currentIndex - 1)].id));
  footer.appendChild(previous);

  const next = document.createElement('button');
  next.className = 'builder-command primary';
  next.type = 'button';
  next.textContent = currentIndex >= builderSteps.length - 1 ? '生成' : '下一步';
  next.addEventListener('click', () => {
    if (currentIndex >= builderSteps.length - 1) {
      runBuilderPreview();
      setBuilderOpen(false);
      return;
    }
    setBuilderStep(builderSteps[currentIndex + 1].id);
  });
  footer.appendChild(next);
  builderPanel.appendChild(footer);
}

function setAction(action) {
  if (runtimeModelActions.has(action)) {
    ensureModelAnimations(state.activePersona, [action]);
  }
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

function normalizeLoadedModel(root) {
  const box = new THREE.Box3().setFromObject(root);
  const size = box.getSize(new THREE.Vector3());
  if (!size.y) return;
  const targetHeight = 1.08;
  const scale = targetHeight / size.y;
  const center = box.getCenter(new THREE.Vector3());
  root.scale.setScalar(scale);
  root.position.set(-center.x * scale, -box.min.y * scale - 1.65, -center.z * scale);
}

function tuneTexture(texture, colorSpace = null) {
  if (!texture) return;
  texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 16);
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  if (colorSpace) texture.colorSpace = colorSpace;
  texture.needsUpdate = true;
}

function enhanceLoadedMaterial(material) {
  if (!material.userData.qibanBaseColor && material.color) {
    material.userData.qibanBaseColor = material.color.clone();
  }
  if (!material.userData.qibanBaseEmissive && material.emissive) {
    material.userData.qibanBaseEmissive = material.emissive.clone();
  }
  tuneTexture(material.map, THREE.SRGBColorSpace);
  tuneTexture(material.emissiveMap, THREE.SRGBColorSpace);
  tuneTexture(material.normalMap);
  tuneTexture(material.roughnessMap);
  tuneTexture(material.metalnessMap);
  if ('emissiveIntensity' in material) {
    material.emissiveIntensity = Math.min(material.emissiveIntensity || 1, 0.12);
  }
  if ('roughness' in material) {
    material.roughness = Math.max(0.38, Math.min(material.roughness || 0.62, 0.68));
  }
  if ('metalness' in material) {
    material.metalness = Math.min(material.metalness || 0, 0.08);
  }
  material.needsUpdate = true;
}

function colorToCss(hex) {
  return `#${hex.toString(16).padStart(6, '0')}`;
}

function applyModelSkin(entry) {
  if (!entry) return;
  const skin = currentSkin();
  const tintColor = new THREE.Color(skin.tint);
  const emissiveColor = new THREE.Color(skin.accent);
  entry.root.traverse((object) => {
    if (!object.isMesh && !object.isSkinnedMesh) return;
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.filter(Boolean).forEach((material) => {
      if (material.color) {
        const base = material.userData.qibanBaseColor || material.color;
        material.color.copy(base).lerp(tintColor, skin.tintStrength);
      }
      if (material.emissive) {
        material.emissive.copy(emissiveColor).multiplyScalar(skin.emissive);
      }
      if ('roughness' in material) {
        material.roughness = Math.max(0.34, Math.min(0.7, material.roughness || 0.58));
      }
      material.needsUpdate = true;
    });
  });
}

function setCosmeticVisible(name, visible) {
  if (rig.cosmetics[name]) rig.cosmetics[name].visible = visible;
}

function updateCosmeticLayer() {
  const skin = currentSkin();
  const features = skin.accessories || {};
  const accent = new THREE.Color(skin.accent);
  cosmeticLayer.visible = true;
  cosmeticLayer.children.forEach((child) => {
    if (child.material && child.material.color) {
      child.material.color.copy(accent);
      child.material.needsUpdate = true;
    }
  });
  setCosmeticVisible('halo', !!features.halo);
  setCosmeticVisible('orbit', !!features.orbit);
  setCosmeticVisible('badge', !!features.badge);
  setCosmeticVisible('capeLeft', !!features.cape);
  setCosmeticVisible('capeRight', !!features.cape);
  setCosmeticVisible('ribbonLeft', !!features.ribbons);
  setCosmeticVisible('ribbonRight', !!features.ribbons);
}

function updateCosmeticMotion(t) {
  const skin = currentSkin();
  const profile = currentMotionProfile();
  if (rig.cosmetics.halo) {
    rig.cosmetics.halo.rotation.z = t * 0.42 * profile.speed;
    rig.cosmetics.halo.position.y = 0.92 + Math.sin(t * 1.8) * 0.01 * profile.breath;
  }
  if (rig.cosmetics.orbit) {
    rig.cosmetics.orbit.rotation.z = t * 0.34 * profile.speed;
    rig.cosmetics.orbit.material.opacity = (skin.accessories.orbit ? 0.2 : 0) + Math.sin(t * 2.4) * 0.025;
  }
  if (rig.cosmetics.badge) {
    rig.cosmetics.badge.rotation.y = t * 1.2;
    rig.cosmetics.badge.scale.setScalar(1 + Math.sin(t * 3) * 0.04);
  }
  if (rig.cosmetics.capeLeft && rig.cosmetics.capeRight) {
    rig.cosmetics.capeLeft.rotation.z = 0.1 + Math.sin(t * 1.3) * 0.025;
    rig.cosmetics.capeRight.rotation.z = -0.1 - Math.sin(t * 1.25) * 0.025;
  }
}

function collectModelBones(root) {
  const bones = {};
  root.traverse((object) => {
    if (object.isBone) {
      bones[object.name] = object;
      object.userData.restPosition = object.position.clone();
      object.userData.restRotation = object.rotation.clone();
      object.userData.restScale = object.scale.clone();
    }
    if (object.isMesh || object.isSkinnedMesh) {
      object.frustumCulled = false;
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.filter(Boolean).forEach((material) => {
        material.side = THREE.DoubleSide;
        enhanceLoadedMaterial(material);
      });
    }
  });
  return bones;
}

function activateLoadedModel(id) {
  const entry = modelState.loaded[id];
  if (!entry) {
    if (!modelState.active) {
      modelLayer.visible = false;
      avatar.visible = true;
    }
    return;
  }

  modelState.active = entry;

  if (entry.root.parent !== modelLayer) {
    modelLayer.clear();
    modelLayer.add(entry.root);
    modelLayer.add(cosmeticLayer);
  }
  applyModelSkin(entry);
  updateCosmeticLayer();
  modelLayer.visible = true;
  avatar.visible = false;
  if (!entry.actions.walk && entry.animationRequests.walk !== 'failed') {
    ensureModelAnimations(id, ['walk']);
  }
}

function loadModel(id) {
  const asset = modelAssets[id];
  if (!asset || !asset.model || modelState.loaded[id] || modelState.loading[id]) return;
  modelState.loading[id] = true;
  gltfLoader.load(asset.model, (gltf) => {
    const root = gltf.scene;
    normalizeLoadedModel(root);
    const entry = {
      root,
      bones: collectModelBones(root),
      clips: gltf.animations || [],
      animationClips: {},
      animationRequests: {},
      actions: {},
      mixer: new THREE.AnimationMixer(root),
      activeAnimation: '',
      activeAction: null
    };
    modelState.loaded[id] = entry;
    modelState.loading[id] = false;
    if (state.activePersona === id) {
      activateLoadedModel(id);
      resize();
    }
  }, undefined, () => {
    modelState.loading[id] = false;
    if (state.activePersona === id && !modelState.active) {
      modelLayer.visible = false;
      avatar.visible = true;
      serverStateEl.textContent = '模型未接';
      serverStateEl.title = '3D 模型加载失败，已临时回退到内置人物。';
    }
  });
}

function preloadModels() {
  loadModel(state.activePersona);
}

function ensureModelAnimations(id, names = null) {
  const entry = modelState.loaded[id];
  const asset = modelAssets[id];
  if (!entry || !asset) return;
  const requested = names ? new Set(names) : null;
  Object.entries(asset.animations || {}).forEach(([name, url]) => {
    if (!runtimeModelActions.has(name)) return;
    if (requested && !requested.has(name)) return;
    if (entry.actions[name] || entry.animationRequests[name]) return;
    loadModelAnimation(entry, name, url);
  });
}

function loadModelAnimation(entry, name, url) {
  entry.animationRequests[name] = 'loading';
  fetch(url, { method: 'HEAD' })
    .then((response) => {
      if (!response.ok) throw new Error('animation not found');
      gltfLoader.load(url, (gltf) => {
        const clip = (gltf.animations || []).find((item) => item.duration > 0) || gltf.animations[0];
        if (!clip || !Number.isFinite(clip.duration) || clip.duration <= 0) {
          entry.animationRequests[name] = 'failed';
          return;
        }
        entry.animationClips[name] = clip;
        const action = entry.mixer.clipAction(clip, entry.root);
        const shouldLoop = loopingModelActions.has(name);
        action.setLoop(shouldLoop ? THREE.LoopRepeat : THREE.LoopOnce, shouldLoop ? Infinity : 1);
        action.clampWhenFinished = !shouldLoop;
        entry.actions[name] = action;
        entry.animationRequests[name] = 'loaded';
        if (modelState.active === entry && name === 'walk') {
          activateLoadedModel(state.activePersona);
          resize();
        }
      });
    })
    .catch(() => {
      entry.animationRequests[name] = 'failed';
    });
}

function playModelAnimation(entry, name) {
  const selected = entry.actions[name];
  if (!selected) return false;
  if (entry.activeAnimation === name) return true;
  const previous = entry.activeAction;
  const profile = currentMotionProfile();
  const fade = Math.max(0.16, Math.min(0.38, 0.26 / profile.speed));
  if (previous && previous !== selected) {
    previous.paused = false;
    previous.fadeOut(fade);
  }
  const shouldLoop = loopingModelActions.has(name);
  selected.setLoop(shouldLoop ? THREE.LoopRepeat : THREE.LoopOnce, shouldLoop ? Infinity : 1);
  selected.clampWhenFinished = !shouldLoop;
  selected.enabled = true;
  selected.setEffectiveWeight(1);
  selected.reset().fadeIn(fade).play();
  selected.paused = false;
  entry.activeAction = selected;
  entry.activeAnimation = name;
  return true;
}

function poseModelAnimation(entry, name, time) {
  const action = entry.actions[name];
  if (!action) return false;
  Object.values(entry.actions).forEach((item) => {
    if (item !== action) {
      item.paused = false;
      item.stop();
    }
  });
  if (entry.activeAnimation !== `pose:${name}`) {
    action.reset().play();
    entry.activeAnimation = `pose:${name}`;
  }
  entry.activeAction = action;
  action.paused = false;
  entry.mixer.setTime(Math.max(0, Math.min(time, action.getClip().duration - 0.001)));
  action.paused = true;
  return true;
}

function stopModelAnimation(entry) {
  if (!entry.activeAnimation) return;
  Object.values(entry.actions).forEach((action) => {
    action.paused = false;
    action.stop();
  });
  entry.activeAction = null;
  entry.activeAnimation = '';
}

function resetModelBone(entry, name) {
  const bone = entry.bones[name];
  if (!bone) return;
  if (bone.userData.restPosition) bone.position.copy(bone.userData.restPosition);
  if (bone.userData.restRotation) bone.rotation.copy(bone.userData.restRotation);
  if (bone.userData.restScale) bone.scale.copy(bone.userData.restScale);
}

function resetModelBones(entry) {
  Object.keys(entry.bones).forEach((name) => {
    resetModelBone(entry, name);
  });
}

function resetModelBonesByName(entry, names) {
  names.forEach((name) => resetModelBone(entry, name));
}

function addBoneRotation(entry, name, x = 0, y = 0, z = 0) {
  const bone = entry.bones[name];
  if (!bone) return;
  bone.rotation.x += x;
  bone.rotation.y += y;
  bone.rotation.z += z;
}

function addBonePosition(entry, name, x = 0, y = 0, z = 0) {
  const bone = entry.bones[name];
  if (!bone) return;
  bone.position.x += x;
  bone.position.y += y;
  bone.position.z += z;
}

function clamp01(value) {
  return Math.max(0, Math.min(1, value));
}

function actionEnvelope(elapsed, duration, edge = 0.22) {
  const p = clamp01(elapsed / duration);
  const attack = clamp01(p / edge);
  const release = clamp01((1 - p) / edge);
  return Math.min(easeOutCubic(attack), easeOutCubic(release));
}

function smoothStep01(value) {
  const t = clamp01(value);
  return t * t * (3 - 2 * t);
}

function cycleBalance(value) {
  return Math.sin(value) * (0.86 + Math.abs(Math.sin(value * 0.5)) * 0.14);
}

function resetModelForProceduralPose(entry) {
  stopModelAnimation(entry);
  resetModelBones(entry);
}

function applyModelNaturalBase(entry, t, breath, sway, pointerLag, weight = 1, includeArms = true) {
  const profile = currentMotionProfile();
  addBonePosition(entry, 'Hips', 0, breath * 0.018 * weight, 0);
  addBoneRotation(entry, 'Hips', breath * 0.018 * weight, 0, sway * 0.18 * weight);
  addBoneRotation(entry, 'Spine', 0.018 + breath * 0.32 * weight, 0, sway * 0.28 * weight);
  addBoneRotation(entry, 'Spine01', 0.012 + breath * 0.24 * weight, 0, sway * 0.18 * weight);
  addBoneRotation(entry, 'Spine02', 0.006 + breath * 0.14 * weight, 0, sway * 0.12 * weight);
  addBoneRotation(entry, 'neck', -state.pointerY * 0.035 * pointerLag * weight, state.pointerX * 0.06 * pointerLag * weight, -sway * 0.12 * weight);
  addBoneRotation(entry, 'Head',
    -state.pointerY * 0.08 * pointerLag * weight + Math.sin(t * 1.08 * profile.speed) * 0.01,
    state.pointerX * 0.17 * pointerLag * weight,
    -sway * 0.32 * weight
  );
  if (includeArms) {
    addBoneRotation(entry, 'LeftShoulder', 0, 0, -1.34 + sway * 0.08 * weight);
    addBoneRotation(entry, 'RightShoulder', 0, 0, 1.34 + sway * 0.08 * weight);
    addBoneRotation(entry, 'LeftArm', 1.16, 0.08, -0.28 + sway * 0.04 * weight);
    addBoneRotation(entry, 'RightArm', 1.16, -0.08, 0.28 + sway * 0.04 * weight);
    addBoneRotation(entry, 'LeftForeArm', 0.12, 0, -0.1);
    addBoneRotation(entry, 'RightForeArm', 0.12, 0, 0.1);
  }
}

function applyModelLocomotionPose(entry, elapsed, isRun, profile, duration) {
  const intensity = (isRun ? 1.04 : 0.82) * profile.action;
  const cadence = (isRun ? 6.6 : 4.2) * profile.speed;
  const stride = (isRun ? 0.4 : 0.24) * intensity;
  const knee = (isRun ? 0.48 : 0.3) * intensity;
  const armSwing = (isRun ? 0.22 : 0.14) * intensity;
  const phase = elapsed * cadence;
  const left = cycleBalance(phase);
  const right = -left;
  const bob = Math.abs(Math.sin(phase));
  const heel = Math.cos(phase);
  const fade = smoothStep01(actionEnvelope(elapsed, duration, 0.22));

  addBonePosition(entry, 'Hips', 0, bob * (isRun ? 0.026 : 0.014) * fade, 0);
  addBoneRotation(entry, 'Hips', -0.018 * fade, 0, -left * 0.026 * fade);
  addBoneRotation(entry, 'Spine', 0.026 * fade, 0, left * 0.032 * fade);
  addBoneRotation(entry, 'Spine01', 0.016 * fade, 0, left * 0.022 * fade);
  addBoneRotation(entry, 'Spine02', 0.01 * fade, 0, left * 0.012 * fade);
  addBoneRotation(entry, 'Head', bob * 0.012 * fade, -left * 0.012 * fade, -left * 0.012 * fade);

  addBoneRotation(entry, 'LeftUpLeg', left * stride * fade, 0, 0.022 * fade);
  addBoneRotation(entry, 'RightUpLeg', right * stride * fade, 0, -0.022 * fade);
  addBoneRotation(entry, 'LeftLeg', Math.max(0, -left) * knee * fade, 0, 0);
  addBoneRotation(entry, 'RightLeg', Math.max(0, -right) * knee * fade, 0, 0);
  addBoneRotation(entry, 'LeftFoot', (-left * 0.075 + Math.max(0, heel) * 0.055) * fade, 0, 0);
  addBoneRotation(entry, 'RightFoot', (-right * 0.075 + Math.max(0, -heel) * 0.055) * fade, 0, 0);
  addBoneRotation(entry, 'LeftToeBase', Math.max(0, -heel) * 0.045 * fade, 0, 0);
  addBoneRotation(entry, 'RightToeBase', Math.max(0, heel) * 0.045 * fade, 0, 0);

  addBoneRotation(entry, 'LeftShoulder', 0, 0, -left * 0.018 * fade);
  addBoneRotation(entry, 'RightShoulder', 0, 0, right * 0.018 * fade);
  addBoneRotation(entry, 'LeftArm', -left * armSwing * fade, 0.018 * fade, right * 0.036 * fade);
  addBoneRotation(entry, 'RightArm', -right * armSwing * fade, -0.018 * fade, left * 0.036 * fade);
  addBoneRotation(entry, 'LeftForeArm', Math.max(0, left) * 0.065 * fade, 0, -0.026 * fade);
  addBoneRotation(entry, 'RightForeArm', Math.max(0, right) * 0.065 * fade, 0, 0.026 * fade);
}

function currentIdlePoseTime() {
  if (forcedIdlePoseTime !== null) return forcedIdlePoseTime;
  return personas[state.activePersona].idlePoseTime || 0;
}

function modelClipDuration(entry, name, fallback) {
  const action = entry.actions[name];
  const duration = action ? action.getClip().duration : 0;
  return Number.isFinite(duration) && duration > 0 ? duration : fallback;
}

function addModelLookOffset(entry, pointerLag, sway, weight = 1) {
  addBoneRotation(entry, 'Head', -state.pointerY * 0.08 * pointerLag * weight, state.pointerX * 0.15 * pointerLag * weight, -sway * 0.18 * weight);
}

function modelFrameScaleMultiplier() {
  const mobile = window.innerWidth < 720;
  if (mobile) {
    return {
      wave: 0.98,
      nod: 1,
      heart: 0.98,
      voice: 0.98
    }[state.action] || 1;
  }
  const actionScale = {
    wave: 0.98,
    nod: 1,
    heart: 0.98,
    voice: 0.98
  }[state.action] || 1;
  return actionScale;
}

function modelFrameXOffset() {
  return 0;
}

function applyModelFrameScale(multiplier, yOffset = 0) {
  const targetScale = modelState.baseScale * multiplier;
  const currentScale = modelLayer.scale.x || targetScale;
  const nextScale = currentScale + (targetScale - currentScale) * 0.16;
  modelLayer.scale.setScalar(nextScale);
  modelLayer.position.x = modelState.baseX + modelFrameXOffset();
  modelLayer.position.y = modelState.baseY - 1.65 * (modelState.baseScale - nextScale) + yOffset;
}

function updateModelPose(t, delta = 0) {
  const entry = modelState.active;
  if (!entry) return;

  const elapsed = t - state.actionStarted;
  const profile = currentMotionProfile();
  const breath = Math.sin(t * 2.1 * profile.speed) * 0.018 * profile.breath;
  const sway = Math.sin(t * 0.76 * profile.speed) * 0.03 * profile.sway;
  const pointerLag = Math.max(0, 1 - (t - state.lastPointerMovedAt) / 3);

  applyModelFrameScale(modelFrameScaleMultiplier(), breath * 0.2);
  modelLayer.rotation.y = state.dragYaw + state.pointerX * 0.04 + Math.sin(t * 0.32) * 0.008 * profile.gaze;
  modelLayer.rotation.z = sway * 0.08;

  resetModelForProceduralPose(entry);
  applyModelNaturalBase(entry, t, breath, sway, pointerLag, state.action === 'voice' ? 0.72 : 1, true);

  if (state.action === 'walk' || state.action === 'run') {
    const isRun = state.action === 'run';
    const duration = (isRun ? 3.2 : 4.2) / profile.action;
    const bob = Math.abs(Math.sin(elapsed * (isRun ? 7.4 : 4.7) * profile.speed));
    applyModelFrameScale(1, bob * (isRun ? 0.017 : 0.01) * actionEnvelope(elapsed, duration, 0.18));
    applyModelLocomotionPose(entry, elapsed, isRun, profile, duration);
    finishActionIfNeeded(elapsed, duration);
    return;
  }

  if (state.action === 'wave') {
    const duration = 2.7 / profile.action;
    const p = Math.min(elapsed / duration, 1);
    const envelope = smoothStep01(actionEnvelope(elapsed, duration, 0.24));
    const raise = smoothStep01(clamp01(p * 1.45));
    const flutter = Math.sin(elapsed * 6.8 * profile.speed) * 0.095 * envelope;
    addBoneRotation(entry, 'Hips', 0, 0, 0.018 * envelope);
    addBoneRotation(entry, 'Spine', 0.012 * envelope, 0, -0.026 * envelope);
    addBoneRotation(entry, 'Spine01', 0.014 * envelope, 0, -0.036 * envelope);
    addBoneRotation(entry, 'Spine02', 0.008 * envelope, 0, -0.02 * envelope);
    addBoneRotation(entry, 'RightShoulder', 0, 0.022 * raise, -0.24 * raise);
    addBoneRotation(entry, 'RightArm', -1.72 * raise, -0.025 * raise, -0.78 * raise);
    addBoneRotation(entry, 'RightForeArm', -0.34 * raise, 0.02 * raise, -0.34 * raise + flutter);
    addBoneRotation(entry, 'RightHand', 0, 0, flutter * 0.48);
    addBoneRotation(entry, 'LeftArm', 0.024 * envelope, 0.02 * envelope, 0.045 * envelope);
    addBoneRotation(entry, 'Head', -0.008 * envelope, 0, 0.028 * envelope);
    finishActionIfNeeded(elapsed, duration);
  }

  if (state.action === 'nod') {
    const duration = 1.8 / profile.action;
    const p = Math.min(elapsed / duration, 1);
    const envelope = actionEnvelope(elapsed, duration, 0.22);
    const nod = Math.sin(p * Math.PI * 3.5) * 0.13 * envelope;
    addBoneRotation(entry, 'Spine', -0.012 * envelope, 0, 0);
    addBoneRotation(entry, 'neck', nod * 0.38, 0, 0);
    addBoneRotation(entry, 'Head', nod, 0, 0);
    addBoneRotation(entry, 'LeftArm', 0.02 * envelope, 0, 0.035 * envelope);
    addBoneRotation(entry, 'RightArm', 0.02 * envelope, 0, -0.035 * envelope);
    finishActionIfNeeded(elapsed, duration);
  }

  if (state.action === 'turn') {
    const duration = 2.15 / profile.action;
    const p = Math.min(elapsed / duration, 1);
    modelLayer.rotation.y = state.dragYaw + easeInOut(p) * Math.PI * 2;
    finishActionIfNeeded(elapsed, duration);
  }

  if (state.action === 'heart') {
    const duration = 2.45 / profile.action;
    const p = Math.min(elapsed / duration, 1);
    const envelope = actionEnvelope(elapsed, duration, 0.2);
    const pulse = Math.sin(p * Math.PI * 2) * 0.035 * envelope;
    addBonePosition(entry, 'Hips', 0, 0.012 * envelope, 0);
    addBoneRotation(entry, 'Spine', 0.045 * envelope, 0, pulse);
    addBoneRotation(entry, 'Spine01', 0.035 * envelope, 0, pulse * 0.6);
    addBoneRotation(entry, 'LeftShoulder', 0, 0, 0.1 * envelope);
    addBoneRotation(entry, 'RightShoulder', 0, 0, -0.1 * envelope);
    addBoneRotation(entry, 'LeftArm', -0.22 * envelope, 0.12 * envelope, 0.46 * envelope);
    addBoneRotation(entry, 'RightArm', -0.22 * envelope, -0.12 * envelope, -0.46 * envelope);
    addBoneRotation(entry, 'LeftForeArm', -0.16 * envelope, 0, -0.48 * envelope);
    addBoneRotation(entry, 'RightForeArm', -0.16 * envelope, 0, 0.48 * envelope);
    addBoneRotation(entry, 'Head', -0.018 * envelope, 0, -pulse);
    rig.heart.visible = true;
    rig.heart.position.y = 1.7 + easeOutCubic(p) * 0.34;
    rig.heart.scale.setScalar(0.2 * envelope + 0.001);
    finishActionIfNeeded(elapsed, duration);
  }

  if (state.action === 'voice') {
    const voiceActive = state.voiceLoading || state.speaking || state.awaitingPlayback;
    const duration = (voiceActive ? 4.2 : 2.1) / profile.action;
    const p = Math.min(elapsed / duration, 1);
    const envelope = voiceActive ? clamp01(p / 0.22) : actionEnvelope(elapsed, duration, 0.24);
    const talk = state.speaking ? Math.sin(t * 8.2) * 0.018 : 0;
    const handBeat = Math.sin(t * 3.6 * profile.speed) * 0.07 * envelope;
    addBoneRotation(entry, 'Hips', 0, 0, 0.012 * envelope);
    addBoneRotation(entry, 'Spine', 0.018 * envelope, 0, -0.02 * envelope);
    addBoneRotation(entry, 'Spine01', 0.014 * envelope, 0, -0.025 * envelope);
    addBoneRotation(entry, 'neck', talk * 0.45, 0, 0);
    addBoneRotation(entry, 'Head', talk, Math.sin(t * 2.2) * 0.018 * envelope, 0.012 * envelope);
    addBoneRotation(entry, 'RightShoulder', 0, 0, -0.06 * envelope);
    addBoneRotation(entry, 'RightArm', -0.16 * envelope + handBeat * 0.35, -0.05 * envelope, -0.28 * envelope);
    addBoneRotation(entry, 'RightForeArm', -0.08 * envelope, 0, -0.22 * envelope + handBeat);
    addBoneRotation(entry, 'LeftArm', 0.04 * envelope, 0.02 * envelope, 0.08 * envelope);
    if (!voiceActive) finishActionIfNeeded(elapsed, duration);
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
  const profile = currentMotionProfile();
  applyPersonaShape(persona);

  const breath = Math.sin(t * 2.1 * profile.speed) * 0.018 * profile.breath;
  const sway = Math.sin(t * 0.76 * profile.speed) * 0.022 * profile.sway;
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

  if (state.action === 'walk' || state.action === 'run') {
    const duration = state.action === 'walk' ? 3.8 : 2.8;
    const speed = state.action === 'walk' ? 6 : 10;
    const stride = state.action === 'walk' ? 0.34 : 0.48;
    const gait = Math.sin(elapsed * speed);
    body.position.y += Math.abs(gait) * (state.action === 'walk' ? 0.018 : 0.032);
    leftArm.rotation.z += gait * 0.3;
    rightArm.rotation.z -= gait * 0.3;
    leftLeg.rotation.x = -gait * stride;
    rightLeg.rotation.x = gait * stride;
    leftShin.rotation.x = Math.max(0, gait) * 0.24;
    rightShin.rotation.x = Math.max(0, -gait) * 0.24;
    finishActionIfNeeded(elapsed, duration);
  }

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
    const voiceActive = state.voiceLoading || state.speaking || state.awaitingPlayback;
    const duration = voiceActive ? 4.2 : 2.1;
    const p = Math.min(elapsed / duration, 1);
    const envelope = Math.sin(p * Math.PI);
    rightArm.rotation.z = -0.82 * envelope - 0.32 * (1 - envelope);
    rightArm.rotation.x = -0.18 * envelope;
    rightForearm.rotation.z = -0.45 * envelope;
    leftArm.rotation.z = 0.22 + envelope * 0.14;
    rig.chestGlow.scale.x = 1 + Math.sin(t * 10) * 0.08 * (state.speaking ? 1 : envelope);
    if (!voiceActive) finishActionIfNeeded(elapsed, duration);
  }
}

function resize() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  const persona = personas[state.activePersona];
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  const mobile = width < 720;
  camera.position.z = mobile ? 7.55 : 6.85;
  camera.position.y = mobile ? 0.3 : 0.22;
  avatar.position.set(0, mobile ? 0.34 : 0.3, 0);
  avatar.scale.setScalar(persona.scale * (mobile ? 0.82 : 1.02));
  modelLayer.position.set(0, mobile ? persona.modelYMobile : persona.modelYDesktop, 0);
  modelState.baseX = modelLayer.position.x;
  modelState.baseY = modelLayer.position.y;
  modelState.baseScale = persona.scale * (mobile ? persona.modelScaleMobile : persona.modelScaleDesktop);
  modelLayer.scale.setScalar(modelState.baseScale);
  rig.heart.position.x = 0;
  camera.updateProjectionMatrix();
}

function animate(time) {
  const t = time * 0.001;
  const delta = modelState.lastTime ? Math.min(t - modelState.lastTime, 0.05) : 0;
  modelState.lastTime = t;
  updateBasePose(t);
  if (!modelState.active) updateActionPose(t);
  updateModelPose(t, delta);

  if (state.action !== 'turn' && !modelState.active) {
    const viewYaw = state.dragYaw + state.pointerX * 0.04;
    avatar.rotation.y += (viewYaw - avatar.rotation.y) * 0.08;
  }

  if (rig.floor) rig.floor.rotation.z = t * 0.12;
  if (rig.orbit) rig.orbit.rotation.z = t * 0.08;
  updateCosmeticMotion(t);
  if (rig.particles) {
    rig.particles.rotation.y = t * 0.026;
    rig.particles.rotation.x = Math.sin(t * 0.22) * 0.04;
  }

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
    if (state.currentAudio.parentNode) {
      state.currentAudio.parentNode.removeChild(state.currentAudio);
    }
    state.currentAudio = null;
  }
  if (state.currentAudioUrl) {
    URL.revokeObjectURL(state.currentAudioUrl);
    state.currentAudioUrl = null;
  }
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
  state.voiceLoading = false;
  state.speaking = false;
  state.awaitingPlayback = false;
}

function finishSpeaking(status = '对话开') {
  if (state.currentAudio && state.currentAudio.parentNode) {
    state.currentAudio.parentNode.removeChild(state.currentAudio);
  }
  state.currentAudio = null;
  state.currentAudioUrl = null;
  state.voiceLoading = false;
  state.speaking = false;
  state.awaitingPlayback = false;
  state.voiceReady = status !== '语音未接';
  state.voiceError = '';
  serverStateEl.textContent = status;
  serverStateEl.title = '';
  updateDialogControls();
  prefetchVoice();
}

function markVoiceUnavailable(message = '语音未接', detail = '') {
  if (state.currentAudio && state.currentAudio.parentNode) {
    state.currentAudio.parentNode.removeChild(state.currentAudio);
  }
  state.currentAudio = null;
  state.currentAudioUrl = null;
  state.voiceLoading = false;
  state.speaking = false;
  state.awaitingPlayback = false;
  state.voiceReady = false;
  state.voiceError = message;
  serverStateEl.textContent = message;
  serverStateEl.title = detail;
  updateDialogControls();
}

function setDockOpen(open) {
  state.dockOpen = open;
  if (dockEl) dockEl.classList.toggle('open', open);
  if (menuButton) {
    menuButton.setAttribute('aria-expanded', open ? 'true' : 'false');
    menuButton.setAttribute('aria-label', open ? '关闭控制' : '打开控制');
  }
  if (!open && state.voicePanelOpen) {
    setVoicePanelOpen(false);
  }
  if (!open && state.builderOpen) {
    state.builderOpen = false;
    if (builderPanel) builderPanel.hidden = true;
    if (builderButton) {
      builderButton.classList.remove('active');
      builderButton.setAttribute('aria-expanded', 'false');
    }
  }
}

function updateDialogControls() {
  if (!dialogButton) return;
  const needsRealVoice = state.dialogEnabled && !browserVoiceFallbackEnabled && (!voiceApiEnabledInPage || !!state.voiceError);
  const label = !state.dialogEnabled
    ? '对话关'
    : state.voiceLoading
      ? '生成中'
      : state.speaking
      ? '说话中'
      : state.awaitingPlayback
        ? '播放'
      : needsRealVoice
        ? '语音未接'
        : '对话开';
  dialogButton.classList.toggle('active', state.dialogEnabled);
  dialogButton.classList.toggle('warning', needsRealVoice);
  dialogButton.textContent = label;
  dialogButton.setAttribute('aria-pressed', state.dialogEnabled ? 'true' : 'false');
}

function selectedVoiceResource() {
  const archetype = state.activeVoiceArchetype || '';
  return state.voiceResources.find((item) => (item.archetype || '') === archetype)
    || state.voiceResources[0]
    || fallbackVoiceResources[state.activePersona][0];
}

function updateVoiceControls() {
  if (!voiceButton) return;
  const selected = selectedVoiceResource();
  voiceButton.textContent = selected && selected.archetype ? selected.name : '声线';
  voiceButton.classList.toggle('active', !!(selected && selected.archetype));
  voiceButton.setAttribute('aria-expanded', state.voicePanelOpen ? 'true' : 'false');
  voiceButton.title = selected && selected.voice ? `${selected.name} · ${selected.voice}` : '选择声线';
  renderVoicePanel();
  renderBuilderPanel();
}

function renderVoicePanel() {
  if (!voicePanel) return;
  voicePanel.hidden = !state.voicePanelOpen;
  if (!state.voicePanelOpen) return;
  voicePanel.textContent = '';
  state.voiceResources.forEach((item) => {
    const option = document.createElement('button');
    option.className = 'voice-option';
    option.type = 'button';
    option.dataset.voice = item.archetype || 'default';
    option.textContent = item.name || item.id || '声线';
    option.title = item.voice ? `${item.voice} ${item.rate || ''} ${item.pitch || ''}` : '';
    option.classList.toggle('active', (item.archetype || '') === (state.activeVoiceArchetype || ''));
    option.addEventListener('click', () => selectVoiceResource(item.archetype || ''));
    voicePanel.appendChild(option);
  });
}

function setVoicePanelOpen(open) {
  if (open && !state.dockOpen) setDockOpen(true);
  if (open && state.builderOpen) setBuilderOpen(false);
  state.voicePanelOpen = open;
  updateVoiceControls();
}

function loadVoiceResources() {
  state.voiceResources = fallbackVoiceResources[state.activePersona];
  updateVoiceControls();
  if (!voiceApiEnabledInPage) return;
  fetch(`${voiceApiBase}/api/voice/voices?persona=${encodeURIComponent(state.activePersona)}`)
    .then((response) => response.ok ? response.json() : null)
    .then((body) => {
      if (!body || !Array.isArray(body.resources) || body.resources.length === 0) return;
      state.voiceResources = body.resources;
      if (!hasStoredVoiceChoice(state.activePersona)) {
        state.activeVoiceArchetype = normalizeVoiceArchetype(body.active_archetype);
      }
      if (!state.voiceResources.some((item) => (item.archetype || '') === (state.activeVoiceArchetype || ''))) {
        state.activeVoiceArchetype = '';
        storeValue(voiceChoiceKey(state.activePersona), '');
      }
      updateVoiceControls();
      prefetchVoice();
    })
    .catch(() => {
      state.voiceResources = fallbackVoiceResources[state.activePersona];
      updateVoiceControls();
    });
}

function selectVoiceResource(archetype) {
  clearVoicePrefetch();
  state.activeVoiceArchetype = normalizeVoiceArchetype(archetype);
  storeValue(voiceChoiceKey(state.activePersona), state.activeVoiceArchetype);
  setVoicePanelOpen(false);
  if (voiceApiEnabledInPage) {
    fetch(`${voiceApiBase}/api/voice/select`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        persona: state.activePersona,
        archetype: state.activeVoiceArchetype
      })
    }).catch(() => {});
  }
  if (state.dialogEnabled) {
    setAction('voice');
  } else {
    prefetchVoice();
  }
}

function voiceMood() {
  return state.activePersona === 'female' ? 'happy' : 'calm';
}

function voicePayloadFor(persona) {
  return {
    text: persona.voiceLine,
    persona: persona.id,
    relationship: 'lover',
    mood: voiceMood(),
    archetype: state.activeVoiceArchetype
  };
}

function voiceCacheKey(payload) {
  return [
    payload.text,
    payload.persona,
    payload.relationship,
    payload.mood,
    payload.archetype || ''
  ].join('|');
}

function clearVoicePrefetch() {
  state.prefetchedVoiceBlob = null;
  state.prefetchedVoiceKey = '';
  state.voicePrefetchPromise = null;
}

function fetchVoiceBlob(payload) {
  return fetch(`${voiceApiBase}/api/voice/speak`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }).then((response) => {
    const type = response.headers.get('content-type') || '';
    if (!response.ok || !type.includes('audio')) {
      throw new Error(`voice response ${response.status}`);
    }
    return response.blob();
  });
}

function prefetchVoice() {
  if (!state.dialogEnabled || !voiceApiEnabledInPage || state.voiceLoading || state.speaking || state.awaitingPlayback) {
    return;
  }
  const persona = personas[state.activePersona];
  const payload = voicePayloadFor(persona);
  const key = voiceCacheKey(payload);
  if (state.prefetchedVoiceBlob && state.prefetchedVoiceKey === key) return;
  if (state.voicePrefetchPromise) return;
  state.voicePrefetchPromise = fetchVoiceBlob(payload)
    .then((blob) => {
      state.prefetchedVoiceBlob = blob;
      state.prefetchedVoiceKey = key;
    })
    .catch(() => {})
    .finally(() => {
      state.voicePrefetchPromise = null;
    });
}

function playVoiceBlob(blob, requestId) {
  if (!blob || requestId !== state.voiceRequestId) return;
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  audio.preload = 'auto';
  audio.playsInline = true;
  audio.setAttribute('playsinline', '');
  audio.className = 'voice-native-audio';
  document.body.appendChild(audio);
  state.currentAudio = audio;
  state.currentAudioUrl = url;
  audio.onended = () => {
    URL.revokeObjectURL(url);
    if (state.currentAudioUrl === url) state.currentAudioUrl = null;
    finishSpeaking('本地语音');
  };
  audio.onerror = () => {
    URL.revokeObjectURL(url);
    if (state.currentAudioUrl === url) state.currentAudioUrl = null;
    markVoiceUnavailable('播放失败', '真实音频已返回，但浏览器播放器无法播放。');
  };
  state.voiceLoading = false;
  state.speaking = true;
  state.awaitingPlayback = false;
  serverStateEl.textContent = '正在说话';
  serverStateEl.title = '';
  updateDialogControls();
  audio.play().then(() => {
    state.voiceReady = true;
    state.voiceError = '';
    state.voiceLoading = false;
    state.speaking = true;
    state.awaitingPlayback = false;
    serverStateEl.textContent = '正在说话';
    serverStateEl.title = '';
    updateDialogControls();
  }).catch(() => {
    state.voiceLoading = false;
    state.speaking = false;
    state.awaitingPlayback = true;
    state.voiceReady = true;
    state.voiceError = '';
    serverStateEl.textContent = '播放';
    serverStateEl.title = '真实语音已生成，请点“播放”或人物播放。';
    updateDialogControls();
  });
}

function speakWithBrowserVoice(text) {
  if (!('speechSynthesis' in window) || !window.SpeechSynthesisUtterance) {
    finishSpeaking('浏览器无语音');
    return false;
  }
  const persona = personas[state.activePersona];
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'zh-CN';
  utterance.rate = state.activePersona === 'female' ? 1.02 : 0.94;
  utterance.pitch = state.activePersona === 'female' ? 1.18 : 0.88;
  utterance.volume = 0.92;
  utterance.onend = () => finishSpeaking('浏览器语音');
  utterance.onerror = () => finishSpeaking('浏览器语音失败');
  state.currentAudio = null;
  state.speaking = true;
  serverStateEl.textContent = '浏览器语音';
  lineEl.textContent = persona.voiceLine;
  window.speechSynthesis.speak(utterance);
  return true;
}

function requestVoice() {
  const persona = personas[state.activePersona];
  const requestId = state.voiceRequestId + 1;
  state.voiceRequestId = requestId;
  lineEl.textContent = persona.voiceLine;
  if (!state.dialogEnabled) {
    stopCurrentAudio();
    serverStateEl.textContent = '对话关';
    state.voiceError = '';
    updateDialogControls();
    return;
  }
  if (!voiceApiEnabledInPage) {
    stopCurrentAudio();
    if (browserVoiceFallbackEnabled) {
      speakWithBrowserVoice(persona.voiceLine);
      return;
    }
    markVoiceUnavailable('语音未接', '真实语音后端未开启：请使用 voice=1 并连接本地 API。');
    return;
  }
  stopCurrentAudio();
  const payload = voicePayloadFor(persona);
  const key = voiceCacheKey(payload);
  const cachedBlob = state.prefetchedVoiceKey === key ? state.prefetchedVoiceBlob : null;
  if (cachedBlob) {
    clearVoicePrefetch();
    playVoiceBlob(cachedBlob, requestId);
    return;
  }
  state.voiceError = '';
  serverStateEl.textContent = '生成中';
  serverStateEl.title = '正在生成真实语音。';
  state.voiceLoading = true;
  state.speaking = false;
  state.awaitingPlayback = false;
  updateDialogControls();
  fetchVoiceBlob(payload).then((blob) => {
    if (requestId !== state.voiceRequestId) return null;
    playVoiceBlob(blob, requestId);
  }).catch(() => {
    if (requestId !== state.voiceRequestId) return;
    stopCurrentAudio();
    if (browserVoiceFallbackEnabled) {
      speakWithBrowserVoice(persona.voiceLine);
      return;
    }
    markVoiceUnavailable('语音未接', `真实语音 API 未连接：${voiceApiBase}`);
  });
}

function playQueuedAudio() {
  if (!state.awaitingPlayback || !state.currentAudio) return false;
  state.awaitingPlayback = false;
  state.speaking = true;
  serverStateEl.textContent = '正在说话';
  serverStateEl.title = '';
  updateDialogControls();
  state.currentAudio.play().then(() => {
    state.voiceReady = true;
    state.voiceError = '';
    state.voiceLoading = false;
    state.speaking = true;
    state.awaitingPlayback = false;
    serverStateEl.textContent = '正在说话';
    serverStateEl.title = '';
    updateDialogControls();
  }).catch(() => {
    state.speaking = false;
    state.awaitingPlayback = true;
    serverStateEl.textContent = '播放';
    serverStateEl.title = '真实语音已生成，请点“播放”或人物播放。';
    updateDialogControls();
  });
  return true;
}

function checkVoiceStatus() {
  updateDialogControls();
  if (!state.dialogEnabled) {
    serverStateEl.textContent = '对话关';
    state.voiceError = '';
    updateDialogControls();
    return;
  }
  if (!voiceApiEnabledInPage) {
    if (browserVoiceFallbackEnabled) {
      serverStateEl.textContent = '浏览器语音';
      updateDialogControls();
      return;
    }
    markVoiceUnavailable('语音未接', '当前页面未开启 voice=1，已禁用浏览器机械声。');
    return;
  }
  fetch(`${voiceApiBase}/api/voice/status`)
    .then((response) => response.ok ? response.json() : null)
    .then((status) => {
      if (!status) return;
      state.voiceReady = !!status.enabled;
      state.voiceError = status.enabled ? '' : '语音未接';
      const voiceBusy = state.voiceLoading || state.speaking || state.awaitingPlayback;
      if (!voiceBusy) {
        serverStateEl.textContent = status.enabled ? '本地语音' : '语音未接';
        serverStateEl.title = '';
      }
      if (!voiceBusy && status.cast && status.cast.voice) {
        serverStateEl.title = status.cast.voice;
      }
      updateDialogControls();
      loadVoiceResources();
      prefetchVoice();
    })
    .catch(() => {
      if (browserVoiceFallbackEnabled) {
        state.voiceReady = false;
        serverStateEl.textContent = '浏览器语音';
        updateDialogControls();
        return;
      }
      markVoiceUnavailable('语音未接', `无法连接真实语音 API：${voiceApiBase}`);
    });
}

function interactWithCompanion() {
  const profileActions = currentMotionProfile().actions || ['wave', 'nod', 'heart', 'voice'];
  const silentActions = modelState.active ? profileActions.filter((action) => action !== 'voice').concat(['turn']) : ['wave', 'nod', 'heart', 'turn'];
  const dialogActions = modelState.active ? profileActions : ['wave', 'nod', 'heart'];
  const actions = state.dialogEnabled ? dialogActions : silentActions;
  const action = actions[state.interactionCount % actions.length];
  state.interactionCount += 1;
  setAction(action);
  if (state.dialogEnabled && action !== 'voice') {
    requestVoice();
  }
}

function toggleDialog() {
  state.dialogEnabled = !state.dialogEnabled;
  storeValue('qiban-dialog', state.dialogEnabled ? '1' : '0');
  if (!state.dialogEnabled) {
    state.voiceRequestId += 1;
    stopCurrentAudio();
  } else {
    setAction('voice');
  }
  checkVoiceStatus();
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
  if (state.dockOpen) setDockOpen(false);
  if (state.builderOpen) setBuilderOpen(false);
  if (playQueuedAudio()) return;
  interactWithCompanion();
});

window.addEventListener('pointermove', updatePointer);
window.addEventListener('resize', resize);
window.addEventListener('keydown', (event) => {
  const key = event.key.toLowerCase();
  if (key === 'd') {
    toggleDialog();
  } else if (key === '1') {
    setPersona('female');
  } else if (key === '2') {
    setPersona('male');
  }
});

if (menuButton) {
  menuButton.addEventListener('click', (event) => {
    event.stopPropagation();
    setDockOpen(!state.dockOpen);
  });
}
if (dockEl) {
  dockEl.addEventListener('click', (event) => event.stopPropagation());
}
personaButtons.female.addEventListener('click', () => setPersona('female'));
personaButtons.male.addEventListener('click', () => setPersona('male'));
if (dialogButton) {
  dialogButton.addEventListener('click', () => {
    if (playQueuedAudio()) return;
    toggleDialog();
  });
}
if (voiceButton) {
  voiceButton.addEventListener('click', (event) => {
    event.stopPropagation();
    setVoicePanelOpen(!state.voicePanelOpen);
  });
}
if (builderButton) {
  builderButton.addEventListener('click', (event) => {
    event.stopPropagation();
    setBuilderOpen(!state.builderOpen);
  });
}
if (voicePanel) {
  voicePanel.addEventListener('click', (event) => event.stopPropagation());
}
if (builderPanel) {
  builderPanel.addEventListener('click', (event) => event.stopPropagation());
}
document.addEventListener('click', () => {
  if (state.voicePanelOpen) setVoicePanelOpen(false);
  if (state.builderOpen) setBuilderOpen(false);
  if (state.dockOpen) setDockOpen(false);
});
actionButtons.forEach((button) => {
  button.addEventListener('click', () => setAction(button.dataset.action));
});

buildStage();
buildCharacter();
preloadModels();
setPersona(state.activePersona);
setAction('idle');
setDockOpen(controlsOpenInPage);
checkVoiceStatus();
resize();
requestAnimationFrame(animate);
