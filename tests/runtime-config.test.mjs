import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveApiBaseUrl } from '../shared/runtime-config.mjs';

function params(value = '') {
  return new URLSearchParams(value);
}

test('production ignores stale local API ports', () => {
  assert.equal(resolveApiBaseUrl({
    params: params(),
    protocol: 'https:',
    hostname: 'qiban-companion.netlify.app',
    origin: 'https://qiban-companion.netlify.app',
    storedPort: '9999'
  }), 'https://qiban-companion.netlify.app');
});

test('local runtime can still use its saved API port', () => {
  assert.equal(resolveApiBaseUrl({
    params: params(),
    protocol: 'http:',
    hostname: '127.0.0.1',
    origin: 'http://127.0.0.1:8921',
    storedPort: '8766'
  }), 'http://127.0.0.1:8766');
});

test('explicit API settings take precedence', () => {
  assert.equal(resolveApiBaseUrl({
    params: params('api=https://api.example.com/base/'),
    protocol: 'https:',
    hostname: 'qiban.example.com',
    origin: 'https://qiban.example.com',
    storedPort: '9999'
  }), 'https://api.example.com/base');
});
