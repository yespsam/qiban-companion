import test from 'node:test';
import assert from 'node:assert/strict';

import {
  CONVERSATION_TTL_MS,
  conversationStorageKey,
  loadConversation,
  saveConversation
} from '../shared/conversation-store.mjs';

function memoryStorage() {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value)
  };
}

test('conversation records are isolated by persona and scene', () => {
  const storage = memoryStorage();
  const now = 100_000;
  assert.equal(saveConversation(storage, 'female', 'daily', [
    { role: 'user', content: '你好' },
    { role: 'assistant', content: '我在。' }
  ], now), true);
  assert.equal(loadConversation(storage, 'male', 'daily', now), null);
  assert.equal(loadConversation(storage, 'female', 'comfort', now), null);
  assert.equal(loadConversation(storage, 'female', 'daily', now).history.length, 2);
});

test('conversation records are sanitized, capped, and expire', () => {
  const storage = memoryStorage();
  const now = 200_000;
  const history = Array.from({ length: 20 }, (_, index) => ({
    role: index % 2 ? 'assistant' : 'user',
    content: ` turn ${index} `
  }));
  saveConversation(storage, 'female', 'daily', history, now);
  const loaded = loadConversation(storage, 'female', 'daily', now);
  assert.equal(loaded.history.length, 12);
  assert.equal(loaded.history[0].content, 'turn 8');
  assert.equal(
    loadConversation(storage, 'female', 'daily', now + CONVERSATION_TTL_MS + 1),
    null
  );
  assert.equal(conversationStorageKey('male', '../bad'), 'qiban-conversation-v1:male:bad');
});
