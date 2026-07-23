import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { NodeIO } from '@gltf-transform/core';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const character = process.argv[2] || 'male';
const builds = {
  male: {
    // Meshy action clips deform this rig, so runtime procedural motion drives the clean bind pose.
    base: 'meshy_output/20260722_194940_male-qiban-reference-rig-actions_019f8998/rigged.glb',
    output: 'desktop-wallpaper/assets/models/qi-an.glb',
    animations: {}
  }
};

if (!builds[character]) {
  throw new Error(`Unknown character "${character}". Available: ${Object.keys(builds).join(', ')}`);
}

const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);

function cloneAccessor(document, source, buffer, name) {
  const array = source.getArray();
  if (!array) throw new Error(`Animation accessor "${source.getName()}" has no data.`);
  return document
    .createAccessor(name)
    .setType(source.getType())
    .setNormalized(source.getNormalized())
    .setArray(new array.constructor(array))
    .setBuffer(buffer);
}

function copyAnimation(document, sourceDocument, label, nodeMap, buffer) {
  const sourceAnimation = sourceDocument.getRoot().listAnimations()
    .map((animation) => {
      const duration = animation.listSamplers().reduce((max, sampler) => {
        const times = sampler.getInput()?.getArray();
        return times && times.length ? Math.max(max, times[times.length - 1]) : max;
      }, 0);
      return { animation, duration };
    })
    .filter(({ animation, duration }) => animation.listChannels().length > 0 && duration > 0.001)
    .sort((a, b) => b.duration - a.duration)[0]?.animation;
  if (!sourceAnimation) throw new Error(`No animation found for "${label}".`);

  const animation = document.createAnimation(label);
  const samplerMap = new Map();

  sourceAnimation.listSamplers().forEach((sourceSampler, index) => {
    const input = cloneAccessor(document, sourceSampler.getInput(), buffer, `${label}-time-${index}`);
    const output = cloneAccessor(document, sourceSampler.getOutput(), buffer, `${label}-value-${index}`);
    const sampler = document
      .createAnimationSampler(`${label}-sampler-${index}`)
      .setInput(input)
      .setOutput(output)
      .setInterpolation(sourceSampler.getInterpolation());
    samplerMap.set(sourceSampler, sampler);
    animation.addSampler(sampler);
  });

  sourceAnimation.listChannels().forEach((sourceChannel, index) => {
    const sourceTarget = sourceChannel.getTargetNode();
    const target = sourceTarget ? nodeMap.get(sourceTarget.getName()) : null;
    const sampler = samplerMap.get(sourceChannel.getSampler());
    if (!target || !sampler) {
      throw new Error(`Cannot retarget ${label} channel ${index} (${sourceTarget?.getName() || 'unnamed'}).`);
    }
    const channel = document
      .createAnimationChannel(`${label}-channel-${index}`)
      .setTargetNode(target)
      .setTargetPath(sourceChannel.getTargetPath())
      .setSampler(sampler);
    animation.addChannel(channel);
  });
}

function runCli(args) {
  const command = resolve(root, 'node_modules/.bin/gltf-transform');
  const result = spawnSync(command, args, { cwd: root, stdio: 'inherit' });
  if (result.status !== 0) {
    throw new Error(`gltf-transform ${args[0]} failed with status ${result.status}.`);
  }
}

async function main() {
  const config = builds[character];
  const temp = await mkdtemp(join(tmpdir(), `qiban-${character}-`));
  const merged = join(temp, 'merged.glb');
  const textured = join(temp, 'textured.glb');
  const output = resolve(root, config.output);

  try {
    const document = await io.read(resolve(root, config.base));
    document.getRoot().listAnimations().forEach((animation) => animation.dispose());
    const animationBuffer = document.getRoot().listBuffers()[0]
      || document.createBuffer('qiban-animation-buffer');
    const nodeMap = new Map(document.getRoot().listNodes().map((node) => [node.getName(), node]));

    for (const [label, relativePath] of Object.entries(config.animations)) {
      const sourceDocument = await io.read(resolve(root, relativePath));
      copyAnimation(document, sourceDocument, label, nodeMap, animationBuffer);
      console.log(`Merged animation: ${label}`);
    }

    await io.write(merged, document);
    runCli(['webp', merged, textured, '--quality', '90', '--effort', '4']);
    runCli([
      'optimize', textured, output,
      '--compress', 'draco',
      '--texture-compress', 'false',
      '--texture-size', '4096',
      '--simplify', 'false',
      '--flatten', 'false',
      '--join', 'false',
      '--palette', 'false',
      '--resample', 'true'
    ]);
    console.log(`Built ${config.output}`);
  } finally {
    await rm(temp, { recursive: true, force: true });
  }
}

await main();
