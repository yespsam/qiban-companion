import { jsonResponse, personaKind, voiceResources } from './voice-data.mjs';

export const handler = async (event) => {
  const params = new URLSearchParams(event.rawQuery || '');
  const kind = personaKind(params.get('persona'));
  return jsonResponse({
    enabled: true,
    pipeline_ready: true,
    tts_engine: 'edge_tts_netlify',
    persona: {
      id: kind === 'male' ? 'male_companion' : 'female_companion',
      gender: kind,
      display_name: kind === 'male' ? '栖安' : '小栖'
    },
    active_archetype: '',
    resources: voiceResources[kind],
    providers: [
      {
        id: 'edge_tts',
        name: 'Edge Neural TTS',
        status: 'ready',
        note: '云端同源函数实时合成 MP3。'
      }
    ]
  });
};
