import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { NodeIO } from '@gltf-transform/core';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const character = process.argv[2] || 'male';
const v2Root = 'meshy_output/20260724_025638_qiban-v2-detailed-characters_019f9056';
const builds = {
  female: {
    base: `${v2Root}/xiao-qi-v2/rigged.glb`,
    output: 'desktop-wallpaper/assets/models/xiao-qi-v2.glb',
    mobileOutput: 'desktop-wallpaper/assets/models/xiao-qi-v2-mobile.glb',
    animations: {
      idle: `${v2Root}/xiao-qi-v2/idle.glb`,
      nod: `${v2Root}/xiao-qi-v2/nod.glb`,
      heart: `${v2Root}/xiao-qi-v2/heart.glb`,
      wave: `${v2Root}/xiao-qi-v2/wave.glb`,
      voice: `${v2Root}/xiao-qi-v2/voice.glb`,
      walk: `${v2Root}/xiao-qi-v2/walk.glb`,
      run: `${v2Root}/xiao-qi-v2/run.glb`
    }
  },
  male: {
    base: `${v2Root}/qi-an-v2/rigged.glb`,
    output: 'desktop-wallpaper/assets/models/qi-an-v2.glb',
    mobileOutput: 'desktop-wallpaper/assets/models/qi-an-v2-mobile.glb',
    animations: {
      idle: `${v2Root}/qi-an-v2/idle.glb`,
      nod: `${v2Root}/qi-an-v2/nod.glb`,
      heart: `${v2Root}/qi-an-v2/heart.glb`,
      wave: `${v2Root}/qi-an-v2/wave.glb`,
      voice: `${v2Root}/qi-an-v2/voice.glb`,
      walk: `${v2Root}/qi-an-v2/walk.glb`,
      run: `${v2Root}/qi-an-v2/run.glb`
    }
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

  sourceAnimation.listChannels().forEach((channel) => {
    const target = channel.getTargetNode();
    const sampler = channel.getSampler();
    const output = sampler?.getOutput();
    if (target?.getName() !== 'Hips' || channel.getTargetPath() !== 'translation' || !output) return;
    const values = output.getArray();
    const targetHips = nodeMap.get('Hips');
    if (!values || values.length < 3 || !targetHips) return;
    const anchored = new values.constructor(values);
    const rest = targetHips.getTranslation();
    const sourceY = anchored[1];
    for (let index = 0; index < anchored.length; index += 3) {
      anchored[index] = rest[0];
      anchored[index + 1] = rest[1] + anchored[index + 1] - sourceY;
      anchored[index + 2] = rest[2];
    }
    output.setArray(anchored);
  });

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
  const desktopTextured = join(temp, 'desktop-textured.glb');
  const mobileResized = join(temp, 'mobile-resized.glb');
  const mobileTextured = join(temp, 'mobile-textured.glb');
  const output = resolve(root, config.output);
  const mobileOutput = resolve(root, config.mobileOutput);

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
    runCli(['webp', merged, desktopTextured, '--quality', '94', '--effort', '5']);
    runCli(['draco', desktopTextured, output, '--decode-speed', '7']);
    runCli(['resize', merged, mobileResized, '--width', '2048', '--height', '2048']);
    runCli(['webp', mobileResized, mobileTextured, '--quality', '92', '--effort', '5']);
    runCli(['draco', mobileTextured, mobileOutput, '--decode-speed', '7']);
    console.log(`Built ${config.output}`);
    console.log(`Built ${config.mobileOutput}`);
  } finally {
    await rm(temp, { recursive: true, force: true });
  }
}

await main();
