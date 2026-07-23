export function isLocalHostname(hostname) {
  const value = String(hostname || '');
  return ['localhost', '127.0.0.1', '0.0.0.0', ''].includes(value) || value.endsWith('.local');
}

export function resolveApiBaseUrl({
  params,
  protocol,
  hostname,
  origin,
  storedPort = ''
}) {
  const explicit = params.get('api');
  if (explicit) return explicit.replace(/\/+$/, '');

  const local = isLocalHostname(hostname);
  const explicitPort = params.get('apiPort') || params.get('port');
  if (!explicitPort && protocol !== 'file:' && !local) {
    return String(origin || '').replace(/\/+$/, '');
  }

  const apiPort = explicitPort || (local || protocol === 'file:' ? storedPort : '') || '8766';
  if (apiPort === 'same') return String(origin || '').replace(/\/+$/, '');
  const apiProtocol = protocol === 'file:' ? 'http:' : protocol;
  const apiHost = params.get('apiHost') || hostname || '127.0.0.1';
  return `${apiProtocol}//${apiHost}:${apiPort}`;
}
