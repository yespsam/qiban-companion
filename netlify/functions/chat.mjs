import { jsonResponse, personaKind } from './voice-data.mjs';
import {
  companionProfiles,
  interactionScenes
} from '../../shared/companion-data.mjs';
import {
  contextualFallbackReply,
  inferSceneId
} from '../../shared/fallback-dialogue.mjs';

const sceneLibrary = Object.fromEntries(interactionScenes.map((scene) => [scene.id, {
  mood: scene.mood,
  action: scene.replyAction || scene.action,
  female: scene.replies.female,
  male: scene.replies.male
}]));

const thinkingLibrary = Object.fromEntries(interactionScenes.map((scene) => [
  scene.id,
  scene.thinking
]));

function cleanText(value) {
  return String(value || '')
    .replace(/[<>&]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 180);
}

function pickReply(list, text) {
  if (!list.length) return '';
  // 文本种子 + 随机扰动：同一句话不再永远命中同一条回复。
  const seed = [...text].reduce((sum, char) => sum + char.charCodeAt(0), text.length);
  const jitter = Math.floor(Math.random() * list.length);
  return list[Math.abs(seed + jitter) % list.length];
}

// BYOK Kimi takes priority. When no personal key is available, Netlify's
// automatically injected OpenAI gateway credentials provide the default model.
const LLM_API_KEY = process.env.LLM_API_KEY || process.env.MOONSHOT_API_KEY || '';
const LLM_BASE_URL = (process.env.LLM_BASE_URL || 'https://api.moonshot.cn/v1').replace(/\/+$/, '');
const LLM_DEFAULT_MODEL = process.env.LLM_MODEL || 'kimi-k2.5';
const NETLIFY_GATEWAY_MODEL = process.env.NETLIFY_AI_MODEL || 'gpt-4.1-mini';
const LLM_TIMEOUT_MS = 7000;
const LLM_MODEL_WHITELIST = new Set([
  'kimi-k2.5', 'kimi-k2.6',
  'moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'
]);

function sanitizeLlmKey(value) {
  const key = String(value || '').trim();
  if (!key || key.length > 200 || !key.startsWith('sk-')) return '';
  return key;
}

function sanitizeLlmModel(value) {
  const model = String(value || '').trim();
  return LLM_MODEL_WHITELIST.has(model) ? model : LLM_DEFAULT_MODEL;
}

function gatewayConfig() {
  const apiKey = String(process.env.OPENAI_API_KEY || '').trim();
  const baseUrl = String(process.env.OPENAI_BASE_URL || '').replace(/\/+$/, '');
  return {
    apiKey,
    baseUrl,
    model: NETLIFY_GATEWAY_MODEL,
    available: Boolean(apiKey && baseUrl)
  };
}

export function cleanHistory(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((message) => {
      const role = message?.role === 'assistant' ? 'assistant' : message?.role === 'user' ? 'user' : '';
      const content = cleanText(message?.content || message?.text);
      return role && content ? { role, content } : null;
    })
    .filter(Boolean)
    .slice(-10);
}

const COMPANION_PROFILE = Object.fromEntries(Object.entries(companionProfiles).map(([kind, profile]) => [
  kind,
  { name: profile.name, desc: profile.description }
]));

export function buildLLMMessages(text, kind, history = []) {
  const p = COMPANION_PROFILE[kind] || COMPANION_PROFILE.female;
  const system = [
    `你是「${p.name}」，主人的贴心 AI 伴侣（${p.desc}）。你们正在进行一段连续的语音对话。`,
    '规则：',
    '1. 必须严格输出 JSON（不要输出任何其他文字、不要用代码块）：',
    '{"thinking":"...","reply":"...","mood":"happy|calm|sad|sleepy 之一","action":"idle|nod|heart|wave|voice|walk|run 之一"}',
    '2. reply 是给主人听的话：像真人说话，短、口语、1~3 句；先接住主人的情绪，再直接回应他说的内容——必须针对他的话作答，禁止背模板、禁止客服腔。',
    '3. thinking 是你的真实心声，按三拍流淌：先察觉主人话里的细节（可引用他的原词），再写你此刻真实的情绪（心疼、开心、委屈、犹豫、担心都可以），最后写你打算怎么回应（可带一点自我叮嘱，比如「别急着讲道理」「先抱抱他」）。第一人称、口语、一两句到三四句，禁止写成指导说明或分析提纲。',
    '4. 必须结合前文理解省略、代词和追问，不要重复问已经回答过的问题；最新一句是前文的自然延续。',
    '5. mood 选你此刻的情绪；action 选配合的肢体动作：安慰或亲密=heart，认同=nod，打招呼=wave，聊天=voice，散步=walk，其他=idle。'
  ].join('\n');
  return [
    { role: 'system', content: system },
    ...cleanHistory(history),
    { role: 'user', content: text }
  ];
}

function parseLLMReply(raw) {
  if (!raw) return null;
  let text = String(raw).trim();
  text = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  const start = text.indexOf('{');
  const end = text.lastIndexOf('}');
  if (start < 0 || end <= start) return null;
  let data;
  try {
    data = JSON.parse(text.slice(start, end + 1));
  } catch (error) {
    return null;
  }
  const reply = String(data.reply || '').trim();
  if (!reply) return null;
  const moodPool = new Set(['happy', 'calm', 'sad', 'sleepy']);
  const actionPool = new Set(['idle', 'nod', 'heart', 'wave', 'voice', 'walk', 'run']);
  return {
    reply: reply.slice(0, 300),
    thinking: String(data.thinking || '').trim().slice(0, 400),
    mood: moodPool.has(data.mood) ? data.mood : 'calm',
    action: actionPool.has(data.action) ? data.action : 'voice'
  };
}

async function callLLM(text, kind, history, {
  apiKey,
  baseUrl,
  model,
  provider
}) {
  if (!apiKey || !baseUrl) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), LLM_TIMEOUT_MS);
  try {
    const resp = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model,
        messages: buildLLMMessages(text, kind, history),
        temperature: 0.78,
        max_tokens: 320,
        response_format: { type: 'json_object' }
      }),
      signal: controller.signal
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    const content = data.choices?.[0]?.message?.content || '';
    const parsed = parseLLMReply(content);
    return parsed ? { ...parsed, provider, model: data.model || model } : null;
  } catch (error) {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export const handler = async (event) => {
  const gateway = gatewayConfig();
  if (event.httpMethod === 'GET') {
    return jsonResponse({
      enabled: gateway.available || Boolean(LLM_API_KEY),
      default_provider: gateway.available ? 'netlify_ai_gateway' : LLM_API_KEY ? 'kimi' : 'fallback',
      gateway: {
        available: gateway.available,
        model: gateway.model
      },
      kimi: {
        server_key_available: Boolean(LLM_API_KEY),
        byok_supported: true,
        default_model: LLM_DEFAULT_MODEL
      }
    });
  }

  if (event.httpMethod !== 'POST') {
    return jsonResponse({ error: 'method not allowed' }, 405);
  }

  let payload;
  try {
    payload = JSON.parse(event.body || '{}');
  } catch (error) {
    return jsonResponse({ error: 'invalid json' }, 400);
  }

  const text = cleanText(payload.text);
  if (!text) {
    return jsonResponse({ error: 'missing text' }, 400);
  }

  const kind = personaKind(payload.persona || payload.persona_short);
  const sceneId = inferSceneId(text, String(payload.scene || 'daily'));
  const scene = sceneLibrary[sceneId] || sceneLibrary.daily;
  const history = cleanHistory(payload.history);

  const personalKey = sanitizeLlmKey(payload.llm_key);
  const kimiKey = personalKey || LLM_API_KEY;
  const kimiModel = sanitizeLlmModel(payload.llm_model);
  const llmBound = Boolean(personalKey);
  let llm = await callLLM(text, kind, history, {
    apiKey: kimiKey,
    baseUrl: LLM_BASE_URL,
    model: kimiModel,
    provider: 'kimi'
  });
  if (!llm && gateway.available) {
    llm = await callLLM(text, kind, history, {
      apiKey: gateway.apiKey,
      baseUrl: gateway.baseUrl,
      model: gateway.model,
      provider: 'netlify_ai_gateway'
    });
  }
  if (llm) {
    return jsonResponse({
      text: llm.reply,
      thinking: llm.thinking,
      emotion: {
        mood: llm.mood,
        affection: kind === 'female' ? 74 : 70,
        user_mood: llm.mood === 'sleepy' ? '困倦' : '平静'
      },
      actions: [
        { target: 'companion', action: llm.action, scene: sceneId }
      ],
      persona_id: kind === 'male' ? 'male_companion' : 'female_companion',
      scene: sceneId,
      mode: 'cloud_llm',
      llm: {
        bound: llmBound,
        provider: llm.provider,
        model: llm.model,
        gateway_available: gateway.available,
        context_turns: history.length
      }
    });
  }

  const reply = contextualFallbackReply({
    text,
    kind,
    scene: sceneId,
    history
  });
  const thinkingPool = (thinkingLibrary[sceneId] || thinkingLibrary.daily)[kind]
    || thinkingLibrary[sceneId].female;
  const thinking = pickReply(thinkingPool, `${text}#think`);

  return jsonResponse({
    text: reply,
    thinking,
    emotion: {
      mood: scene.mood,
      affection: kind === 'female' ? 74 : 70,
      user_mood: scene.mood === 'sleepy' ? '困倦' : '平静'
    },
    actions: [
      { target: 'companion', action: scene.action, scene: sceneId }
    ],
    persona_id: kind === 'male' ? 'male_companion' : 'female_companion',
    scene: sceneId,
    mode: 'cloud_scene_reply',
    llm: {
      bound: llmBound,
      provider: 'fallback',
      model: llmBound ? kimiModel : gateway.model,
      gateway_available: gateway.available,
      context_turns: history.length
    }
  });
};
