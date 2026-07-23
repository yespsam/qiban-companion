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

test('handler uses Netlify AI Gateway when no personal key is present', async (t) => {
  const originalFetch = globalThis.fetch;
  const originalGatewayKey = process.env.OPENAI_API_KEY;
  const originalGatewayBase = process.env.OPENAI_BASE_URL;
  let requestUrl = '';
  let authorization = '';
  t.after(() => {
    globalThis.fetch = originalFetch;
    if (originalGatewayKey === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = originalGatewayKey;
    if (originalGatewayBase === undefined) delete process.env.OPENAI_BASE_URL;
    else process.env.OPENAI_BASE_URL = originalGatewayBase;
  });
  process.env.OPENAI_API_KEY = 'netlify-gateway-test-key';
  process.env.OPENAI_BASE_URL = 'https://gateway.example.test/v1/';
  globalThis.fetch = async (url, options) => {
    requestUrl = url;
    authorization = options.headers.Authorization;
    return {
      ok: true,
      json: async () => ({
        model: 'gpt-4.1-mini',
        choices: [{
          message: {
            content: JSON.stringify({
              thinking: '他在接着上一句问，我要直接回应。',
              reply: '当然记得，我们刚才在聊周末去哪里。',
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
      text: '那你觉得第二个方案怎么样？',
      persona_short: 'female',
      history: [
        { role: 'user', content: '周末去公园还是看电影？' },
        { role: 'assistant', content: '第二个方案听起来更适合下雨天。' }
      ]
    })
  });
  const body = JSON.parse(response.body);

  assert.equal(requestUrl, 'https://gateway.example.test/v1/chat/completions');
  assert.equal(authorization, 'Bearer netlify-gateway-test-key');
  assert.equal(body.mode, 'cloud_llm');
  assert.equal(body.llm.provider, 'netlify_ai_gateway');
  assert.equal(body.llm.bound, false);
  assert.equal(body.llm.context_turns, 2);
});

test('chat status reports default gateway availability without exposing credentials', async (t) => {
  const originalGatewayKey = process.env.OPENAI_API_KEY;
  const originalGatewayBase = process.env.OPENAI_BASE_URL;
  t.after(() => {
    if (originalGatewayKey === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = originalGatewayKey;
    if (originalGatewayBase === undefined) delete process.env.OPENAI_BASE_URL;
    else process.env.OPENAI_BASE_URL = originalGatewayBase;
  });
  process.env.OPENAI_API_KEY = 'hidden-test-key';
  process.env.OPENAI_BASE_URL = 'https://gateway.example.test/v1';

  const response = await handler({ httpMethod: 'GET' });
  const body = JSON.parse(response.body);

  assert.equal(body.enabled, true);
  assert.equal(body.default_provider, 'netlify_ai_gateway');
  assert.equal(body.gateway.available, true);
  assert.equal(JSON.stringify(body).includes('hidden-test-key'), false);
});

test('handler keeps conversation available when the LLM provider fails', async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () => {
    throw new Error('provider unavailable');
  };

  const response = await handler({
    httpMethod: 'POST',
    body: JSON.stringify({
      text: '今天有点累',
      persona_short: 'female',
      llm_key: 'sk-test-key',
      scene: 'daily'
    })
  });
  const body = JSON.parse(response.body);

  assert.equal(response.statusCode, 200);
  assert.equal(body.mode, 'cloud_scene_reply');
  assert.equal(body.llm.bound, true);
  assert.ok(body.text);
  assert.ok(body.thinking);
});
