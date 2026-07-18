import * as THREE from './vendor/three.module.js';

const canvas = document.getElementById('scene');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100);
camera.position.set(0, 0.4, 7);

const loader = new THREE.TextureLoader();
const personas = {
  female: {
    name: '小栖',
    line: '我在桌面旁边，等你随时叫我。',
    image: './assets/xiao-qi-avatar.png',
    color: 0x07c160,
    x: 1.05
  },
  male: {
    name: '栖安',
    line: '我在这里，先把心放稳。',
    image: './assets/qi-an-avatar.png',
    color: 0x6fb58a,
    x: 1.0
  }
};

const ambient = new THREE.AmbientLight(0xffffff, 1.2);
scene.add(ambient);

const keyLight = new THREE.PointLight(0xefffed, 5.2, 14);
keyLight.position.set(-3.4, 3.1, 4.2);
scene.add(keyLight);

const rimLight = new THREE.PointLight(0x92f0bf, 2.1, 10);
rimLight.position.set(3.5, -1.2, 3);
scene.add(rimLight);

const group = new THREE.Group();
scene.add(group);

const portraitGeo = new THREE.PlaneGeometry(3.15, 4.2, 16, 16);
const portraitMat = new THREE.MeshBasicMaterial({
  transparent: true,
  depthWrite: false,
  color: 0xffffff
});
const portrait = new THREE.Mesh(portraitGeo, portraitMat);
portrait.position.set(1.05, 0.05, 0);
group.add(portrait);

const ring = new THREE.Mesh(
  new THREE.TorusGeometry(1.85, 0.01, 12, 150),
  new THREE.MeshBasicMaterial({ color: 0x07c160, transparent: true, opacity: 0.32 })
);
ring.position.set(1.05, 0.05, -0.18);
ring.scale.set(1, 1.26, 1);
group.add(ring);

const fieldGeo = new THREE.BufferGeometry();
const count = 140;
const positions = new Float32Array(count * 3);
for (let i = 0; i < count; i += 1) {
  positions[i * 3] = (Math.random() - 0.5) * 10;
  positions[i * 3 + 1] = (Math.random() - 0.5) * 5.8;
  positions[i * 3 + 2] = -1.5 - Math.random() * 3.2;
}
fieldGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
const field = new THREE.Points(
  fieldGeo,
  new THREE.PointsMaterial({
    color: 0xc8ead7,
    size: 0.018,
    transparent: true,
    opacity: 0.62
  })
);
scene.add(field);

let active = 'female';
let pointerX = 0;
let pointerY = 0;

function setPersona(id) {
  active = id;
  const p = personas[id];
  loader.load(p.image, (texture) => {
    texture.colorSpace = THREE.SRGBColorSpace;
    portraitMat.map = texture;
    portraitMat.needsUpdate = true;
  });
  ring.material.color.setHex(p.color);
  rimLight.color.setHex(p.color);
  portrait.position.x = p.x;
  ring.position.x = p.x;
  document.getElementById('name').textContent = p.name;
  document.getElementById('line').textContent = p.line;
  document.getElementById('female-btn').classList.toggle('active', id === 'female');
  document.getElementById('male-btn').classList.toggle('active', id === 'male');
}

function resize() {
  const width = window.innerWidth;
  const height = window.innerHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.position.z = width < 720 ? 8.4 : 7;
  group.position.x = width < 720 ? -0.58 : 0.72;
  group.position.y = width < 720 ? 1.15 : 0.08;
  group.scale.setScalar(width < 720 ? 0.6 : 1);
  camera.updateProjectionMatrix();
}

function animate(time) {
  const t = time * 0.001;
  const breath = Math.sin(t * 1.3) * 0.035;
  group.rotation.y += (pointerX * 0.09 - group.rotation.y) * 0.05;
  group.rotation.x += (-pointerY * 0.04 - group.rotation.x) * 0.05;
  portrait.scale.set(1 + breath, 1 + breath, 1);
  ring.rotation.z = t * 0.12;
  ring.scale.set(1 + breath * 1.4, 1.26 + breath * 1.4, 1);
  field.rotation.y = t * 0.018;
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}

window.addEventListener('resize', resize);
window.addEventListener('pointermove', (event) => {
  pointerX = (event.clientX / window.innerWidth - 0.5) * 2;
  pointerY = (event.clientY / window.innerHeight - 0.5) * 2;
});

document.getElementById('female-btn').addEventListener('click', () => setPersona('female'));
document.getElementById('male-btn').addEventListener('click', () => setPersona('male'));

fetch('http://127.0.0.1:8766/api/voice/status')
  .then((response) => response.ok ? response.json() : null)
  .then((status) => {
    const label = document.getElementById('server-state');
    if (!status) return;
    label.textContent = status.enabled ? 'voice online' : 'voice standby';
  })
  .catch(() => {
    document.getElementById('server-state').textContent = 'offline wallpaper';
  });

setPersona(active);
resize();
requestAnimationFrame(animate);
