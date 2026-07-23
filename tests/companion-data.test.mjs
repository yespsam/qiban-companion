import test from 'node:test';
import assert from 'node:assert/strict';

import {
  SUPPORTED_ACTIONS,
  companionProfiles,
  interactionScenes,
  personaKind,
  voiceResources
} from '../shared/companion-data.mjs';

test('shared companion catalog has complete persona records', () => {
  assert.deepEqual(Object.keys(companionProfiles).sort(), ['female', 'male']);
  assert.equal(personaKind(companionProfiles.female.id), 'female');
  assert.equal(personaKind(companionProfiles.male.id), 'male');
  assert.notEqual(companionProfiles.female.name, companionProfiles.male.name);
});

test('every interaction scene supports both companions', () => {
  const ids = new Set();
  for (const scene of interactionScenes) {
    assert.ok(!ids.has(scene.id), `duplicate scene id: ${scene.id}`);
    ids.add(scene.id);
    assert.ok(SUPPORTED_ACTIONS.includes(scene.action));
    assert.ok(SUPPORTED_ACTIONS.includes(scene.replyAction));
    for (const kind of ['female', 'male']) {
      assert.ok(scene.opening[kind]);
      assert.ok(scene.replies[kind].length >= 2);
      assert.ok(scene.thinking[kind].length >= 2);
    }
  }
});

test('voice archetypes are unique within each companion', () => {
  for (const kind of ['female', 'male']) {
    const ids = voiceResources[kind].map((voice) => voice.id);
    const archetypes = voiceResources[kind].map((voice) => voice.archetype);
    assert.equal(new Set(ids).size, ids.length);
    assert.equal(new Set(archetypes).size, archetypes.length);
    voiceResources[kind].forEach((voice) => assert.match(voice.voice, /^zh-CN-/));
  }
});
