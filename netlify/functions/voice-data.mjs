export const voiceResources = {
  female: [
    { id: 'default', archetype: '', name: '随身份', voice: 'zh-CN-XiaoxiaoNeural', rate: '+0%', pitch: '+0Hz' },
    { id: 'loli', archetype: 'loli', name: '萝莉音', voice: 'zh-CN-XiaoyiNeural', rate: '+12%', pitch: '+18Hz' },
    { id: 'yujie', archetype: 'yujie', name: '御姐音', voice: 'zh-CN-XiaoxiaoNeural', rate: '-8%', pitch: '-8Hz' },
    { id: 'funny', archetype: 'funny', name: '搞笑女', voice: 'zh-CN-XiaoyiNeural', rate: '+16%', pitch: '+10Hz' }
  ],
  male: [
    { id: 'default', archetype: '', name: '随身份', voice: 'zh-CN-YunxiNeural', rate: '+0%', pitch: '+0Hz' },
    { id: 'shonen', archetype: 'shonen', name: '少年音', voice: 'zh-CN-YunxiaNeural', rate: '+8%', pitch: '+12Hz' },
    { id: 'uncle', archetype: 'uncle', name: '大叔音', voice: 'zh-CN-YunjianNeural', rate: '-10%', pitch: '-8Hz' },
    { id: 'funny', archetype: 'funny', name: '搞笑男', voice: 'zh-CN-YunyangNeural', rate: '+16%', pitch: '+8Hz' }
  ]
};

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

export function personaKind(value) {
  const raw = String(value || '').toLowerCase();
  if (raw.includes('female') || raw.includes('xiao') || raw.includes('小栖') || raw.includes('女')) return 'female';
  if (raw.includes('male') || raw.includes('qi-an') || raw.includes('男')) return 'male';
  return 'female';
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
