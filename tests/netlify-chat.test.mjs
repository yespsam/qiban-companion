import test from 'node:test';
import assert from 'node:assert/strict';

import { buildLLMMessages, cleanHistory, handler } from '../netlify/functions/chat.mjs';

test('cleanHistory keeps only safe recent user and assistant turns', () => {
  const input = [
    { role: 'system', content: 'ignore me' },
    ...Array.from({ length: 11 }, (_, index) => ({
      role: index % 2 ? 'assistant' : 'user',
      content: `第 ${index + 1} 条 <内容>`
    }))
  ];

  const history = cleanHistory(input);
  assert.equal(history.length, 10);
  assert.equal(history[0].content, '第 2 条 内容');
  assert.equal(history.at(-1).content, '第 11 条 内容');
  assert.ok(history.every((message) => ['user', 'assistant'].includes(message.role)));
});

test('buildLLMMessages places prior conversation before the latest message', () => {
  const messages = buildLLMMessages('那就去昨天那家吧', 'male', [
    { role: 'user', content: '明天去吃火锅还是日料？' },
    { role: 'assistant', content: '我更想和你去昨天提到的日料店。' }
  ]);

  assert.deepEqual(messages.slice(1), [
    { role: 'user', content: '明天去吃火锅还是日料？' },
    { role: 'assistant', content: '我更想和你去昨天提到的日料店。' },
    { role: 'user', content: '那就去昨天那家吧' }
  ]);
  assert.match(messages[0].content, /结合前文/);
});

test('handler forwards sanitized history to the cloud model request', async (t) => {
  const originalFetch = globalThis.fetch;
  let forwardedMessages = [];
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (_url, options) => {
    forwardedMessages = JSON.parse(options.body).messages;
    return {
      ok: true,
      json: async () => ({
        choices: [{
          message: {
            content: JSON.stringify({
              thinking: '他承接了刚才的选择，我要记住前文。',
              reply: '好，那就去刚才说的那家日料店。',
              mood: 'happy',
              action: 'nod'
            })
          }
        }]
      })
    };
  };

  const response = await handler({
    httpMethod: 'POST',
    body: JSON.stringify({
      text: '那就去那家吧',
      persona_short: 'male',
      llm_key: 'sk-test-key',
      history: [
        { role: 'user', content: '明天去火锅还是日料？' },
        { role: 'assistant', content: '我想去你昨天提到的日料店。' }
      ]
    })
  });
  const body = JSON.parse(response.body);

  assert.equal(body.mode, 'cloud_llm');
  assert.equal(body.llm.context_turns, 2);
  assert.deepEqual(forwardedMessages.slice(1), [
    { role: 'user', content: '明天去火锅还是日料？' },
    { role: 'assistant', content: '我想去你昨天提到的日料店。' },
    { role: 'user', content: '那就去那家吧' }
  ]);
});
