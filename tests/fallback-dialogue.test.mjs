import test from 'node:test';
import assert from 'node:assert/strict';

import {
  contextualFallbackReply,
  inferSceneId
} from '../shared/fallback-dialogue.mjs';

test('fallback answers basic availability questions directly', () => {
  assert.match(contextualFallbackReply({
    text: '现在可以正常对话吗？',
    kind: 'female',
    scene: 'daily'
  }), /可以.*收到/);
});

test('fallback recalls the previous user turn', () => {
  assert.equal(contextualFallbackReply({
    text: '我刚才问了什么？',
    kind: 'female',
    scene: 'daily',
    history: [
      { role: 'assistant', content: '你好呀。' },
      { role: 'user', content: '今天一起去散步吗？' },
      { role: 'assistant', content: '好呀。' }
    ]
  }), '你刚才说的是“今天一起去散步吗？”。我记得，我们可以从这里接着聊。');
});

test('fallback scene inference follows the current message', () => {
  assert.equal(inferSceneId('今天工作先做哪一步？', 'daily'), 'focus');
  assert.equal(inferSceneId('我有点累', 'daily'), 'comfort');
});
