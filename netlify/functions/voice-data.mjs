import {
  personaKind,
  voiceResources
} from '../../shared/companion-data.mjs';

export { personaKind, voiceResources };

export function jsonResponse(body, statusCode = 200) {
  return {
    statusCode,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store'
    },
    body: JSON.stringify(body)
  };
}

export function resolveVoice(persona, archetype) {
  const kind = personaKind(persona);
  const resources = voiceResources[kind];
  const key = archetype === 'default' ? '' : String(archetype || '');
  return resources.find((item) => item.archetype === key) || resources[0];
}

export function voiceStatusBody() {
  return {
    enabled: true,
    voice_enabled: true,
    pipeline_ready: true,
    tts_engine: 'edge_tts_netlify',
    active_archetype: '',
    voice_profile: 'cloud_neural',
    cast: {
      provider: 'edge_tts',
      engine: 'edge_tts',
      voice: 'zh-CN-XiaoxiaoNeural',
      name: '随身份'
    },
    stt_model_size: '',
    error: ''
  };
}
