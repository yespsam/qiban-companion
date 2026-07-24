import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { NodeIO } from '@gltf-transform/core';
import { prune } from '@gltf-transform/functions';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const input = resolve(
  root,
  'meshy_output/20260724_160215_qiban-female-exact-head_019f9325/'
    + 'xiao-qi-head-v1/model.glb'
);
const output = resolve(
  root,
  'desktop-wallpaper/assets/models/xiao-qi-head-v1.glb'
);
const mobileOutput = resolve(
  root,
  'desktop-wallpaper/assets/models/xiao-qi-head-v1-mobile.glb'
);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);

function runCli(args) {
  const command = resolve(root, 'node_modules/.bin/gltf-transform');
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' });
  if (result.status !== 0) {
    throw new Error(`gltf-transform ${args[0]} failed with status ${result.status}.`);
  }
}

const temp = await mkdtemp(join(tmpdir(), 'qiban-head-'));
const cleaned = join(temp, 'cleaned.glb');
const desktopTextured = join(temp, 'desktop-textured.glb');
const mobileResized = join(temp, 'mobile-resized.glb');
const mobileTextured = join(temp, 'mobile-textured.glb');

try {
  const document = await io.read(input);
  document.getRoot().listMaterials().forEach((material) => {
    material.setEmissiveTexture(null);
    material.setEmissiveFactor([0, 0, 0]);
    material.setNormalTexture(null);
    material.setMetallicRoughnessTexture(null);
    material.setMetallicFactor(0.02);
    material.setRoughnessFactor(0.72);
  });
  await document.transform(prune());
  await io.write(cleaned, document);

  runCli(['webp', cleaned, desktopTextured, '--quality', '94', '--effort', '5']);
  runCli(['draco', desktopTextured, output, '--decode-speed', '7']);
  runCli(['resize', cleaned, mobileResized, '--width', '2048', '--height', '2048']);
  runCli(['webp', mobileResized, mobileTextured, '--quality', '92', '--effort', '5']);
  runCli(['draco', mobileTextured, mobileOutput, '--decode-speed', '7']);
  console.log(output);
  console.log(mobileOutput);
} finally {
  await rm(temp, { recursive: true, force: true });
}
