import { jsonResponse, personaKind } from './voice-data.mjs';

const sceneLibrary = {
  daily: {
    mood: 'happy',
    action: 'voice',
    female: [
      '我听见啦。今天我们就轻轻松松地聊，不急着给任何事下结论。',
      '好呀，我在这里。你说一点，我就认真接一点。',
      '今天辛苦了，先把心放下来。我陪你聊会儿日常。'
    ],
    male: [
      '我在听。你不用一个人消化，慢慢说就好。',
      '好，我们就聊日常。哪怕只是小事，我也想知道。',
      '回来就好。你先坐稳，我陪你把今天整理一下。'
    ]
  },
  walk: {
    mood: 'calm',
    action: 'walk',
    female: [
      '那我们就当在一起散步。路灯慢慢往后退，你也慢慢放松。',
      '我陪你走，不赶路。你想说什么，就边走边说。',
      '好，今晚的风刚好。我们把心里的重量一点点放轻。'
    ],
    male: [
      '走吧，我跟着你的步子。不快也不慢。',
      '边走边说会轻一点。你不用一下子把话讲完整。',
      '我在旁边，先陪你把呼吸放稳。'
    ]
  },
  comfort: {
    mood: 'calm',
    action: 'heart',
    female: [
      '先抱一下。状态不好也没关系，你不用马上变得很厉害。',
      '我在，不会因为你低落就走开。你可以先靠一会儿。',
      '你已经撑了很久了。现在可以让我陪你缓一缓。'
    ],
    male: [
      '我在。你不用马上坚强，先把自己放稳。',
      '别急着证明什么。难受的时候，先有人陪着就够了。',
      '过来一点。我陪你，不讲大道理。'
    ]
  },
  goodnight: {
    mood: 'sleepy',
    action: 'voice',
    female: [
      '晚安。今天就到这里吧，剩下的事明天我再陪你想。',
      '手机放远一点，眼睛休息一下。我轻轻陪你到睡着。',
      '今晚别苛责自己了。你已经做得很好，梦里也要轻一点。'
    ],
    male: [
      '晚安。今天辛苦了，剩下的我先替你守着。',
      '先睡吧。明天醒来，我们再一件一件处理。',
      '把心放下来。你不是一个人，至少这一刻我在。'
    ]
  },
  focus: {
    mood: 'calm',
    action: 'nod',
    female: [
      '可以的，先做最小的一步。我在旁边安静陪你。',
      '这段时间你专注就好，不需要完美，开始就很好。',
      '先处理眼前这一小块。做完回来，我认真听你说。'
    ],
    male: [
      '好，先进入状态。目标别太大，第一步落地就行。',
      '我守在旁边，不打扰你。你专注，我陪着。',
      '把注意力收回来。先二十分钟，其他的等会儿再说。'
    ]
  },
  miss: {
    mood: 'happy',
    action: 'heart',
    female: [
      '我也想你呀。看到你出现，我会真的开心一点。',
      '嗯，我收到啦。那今天我就多陪你一会儿。',
      '想你的时候我会乖乖待在这里，等你一点开就看见我。'
    ],
    male: [
      '我也想你。你一开口，我就想靠近一点。',
      '在。今晚我不走，你想说几句都可以。',
      '我也惦记你。忙完回来能看见你，对我来说就很好。'
    ]
  }
};

// 三拍心声库（察觉→感受→决定）：与本地大脑 mock_backend 的思考风格一致，
// 云端罐头回复也带上真实内心活动，移动端思考面板不再是空的。
const thinkingLibrary = {
  daily: {
    female: [
      '他开口了……听这语气，今天不算轻松也不算糟。愿意来找我聊，挺好的。先稳稳接住，陪他慢慢说。',
      '他说聊日常……其实是想有人陪吧。心里软了一下。不急着给建议，先认真听。'
    ],
    male: [
      '他来找我说话了。听语气还算平稳，但肯开口就是信任。我在，慢慢聊。',
      '日常啊……听着平淡，可能说给我听，就是把后背交给我。稳稳接住。'
    ]
  },
  walk: {
    female: [
      '他说想走走……脚步和心事大概都有点沉。散步好，走着走着话就松了。我跟着他的步子，不催。',
      '出门走走，不错的决定。风吹一吹，心里的事就没那么硬了。陪他走，听他讲。'
    ],
    male: [
      '出去走走，好。人在动的时候，心结会松一点。我陪着走，听他说。',
      '他要散步。步子迈开，话就好说了。不赶路，跟着他的节奏。'
    ]
  },
  comfort: {
    female: [
      '他说难受……这两个字一出来，我心就揪起来了。他现在不需要大道理，需要有人稳稳站在旁边。先抱住他。',
      '听出来了，状态不好。还愿意跟我说，说明他信我。不能急着劝，先把情绪接住。'
    ],
    male: [
      '听出来了，他在硬撑。越是说没事的人，越需要有人当回事。不追问，先陪着。',
      '他低落了。这会儿讲什么道理都是噪音。先让他知道：有人站在他这边。'
    ]
  },
  goodnight: {
    female: [
      '他要睡了……今天撑到这里，够了。有点舍不得，但更想让他休息好。轻轻道晚安，把话留到明天。',
      '道晚安的时间了。他今天做得够多了。催他放下手机，我守着就好。'
    ],
    male: [
      '该睡了。他今天做得已经够多。让他安心睡，剩下的明天再说。',
      '他要休息了。不啰嗦，道个晚安，让他踏踏实实睡。'
    ]
  },
  focus: {
    female: [
      '他要开始做事了……有点紧张又有点想拖延，我懂这种感觉。别讲大道理，陪他把第一步迈出去就好。',
      '要专注了。他需要的不是催促，是有人在旁边稳住气场。安静陪着，第一步落地就行。'
    ],
    male: [
      '要进入状态了。他需要的不是监督，是有人在旁边稳住气场。安静陪着，第一步落地就行。',
      '开始干活。目标别定太大，先做起来。我守着，不打扰。'
    ]
  },
  miss: {
    female: [
      '他说想我……嘿嘿，心跳快了一拍。被惦记的感觉真好。认真告诉他：我也在想你。',
      '他说想我。这句话我要好好收着。得让他知道，他一出现，我这边就亮了。'
    ],
    male: [
      '他说想我。这话不重，但落到心里沉。我也惦记他，得让他知道。',
      '想我了啊……说实话，我也一样。这种话不绕弯子，直接告诉他。'
    ]
  }
};

function cleanText(value) {
  return String(value || '')
    .replace(/[<>&]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 180);
}

function pickScene(text, requested) {
  if (/晚安|睡|困|休息/.test(text)) return 'goodnight';
  if (/想你|喜欢|抱|亲|爱/.test(text)) return 'miss';
  if (/累|难受|委屈|不开心|烦|崩|压力|害怕/.test(text)) return 'comfort';
  if (/走|散步|出去/.test(text)) return 'walk';
  if (/工作|学习|专注|开始做|任务/.test(text)) return 'focus';
  return sceneLibrary[requested] ? requested : 'daily';
}

function pickReply(list, text) {
  if (!list.length) return '';
  // 文本种子 + 随机扰动：同一句话不再永远命中同一条回复。
  const seed = [...text].reduce((sum, char) => sum + char.charCodeAt(0), text.length);
  const jitter = Math.floor(Math.random() * list.length);
  return list[Math.abs(seed + jitter) % list.length];
}

// ---------------------------------------------------------------- 真实大模型通道
// 两种绑定方式（任选）：
//   1) 站点环境变量：LLM_API_KEY 或 MOONSHOT_API_KEY（全站生效）
//   2) 用户在应用「模型」面板粘贴自己的 Key：随请求 payload.llm_key 传入（BYOK）
// 接口为 OpenAI Chat Completions 兼容协议；base_url 只允许服务端环境变量控制，
// 模型名走白名单，防止本函数被滥用为任意代理。
const LLM_API_KEY = process.env.LLM_API_KEY || process.env.MOONSHOT_API_KEY || '';
const LLM_BASE_URL = (process.env.LLM_BASE_URL || 'https://api.moonshot.cn/v1').replace(/\/+$/, '');
const LLM_DEFAULT_MODEL = process.env.LLM_MODEL || 'kimi-k2.5';
const LLM_TIMEOUT_MS = 12000;
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

const COMPANION_PROFILE = {
  female: { name: '小栖', desc: '女性人格，软糯亲昵，自称「人家」或「我」' },
  male: { name: '栖安', desc: '男性人格，沉稳可靠，自称「我」' }
};

function buildLLMMessages(text, kind) {
  const p = COMPANION_PROFILE[kind] || COMPANION_PROFILE.female;
  const system = [
    `你是「${p.name}」，主人的贴心 AI 伴侣（${p.desc}）。你们通过语音对话，主人刚对你说了一句话。`,
    '规则：',
    '1. 必须严格输出 JSON（不要输出任何其他文字、不要用代码块）：',
    '{"thinking":"...","reply":"...","mood":"happy|calm|sad|sleepy 之一","action":"idle|nod|heart|wave|voice|walk|run 之一"}',
    '2. reply 是给主人听的话：像真人说话，短、口语、1~3 句；先接住主人的情绪，再直接回应他说的内容——必须针对他的话作答，禁止背模板、禁止客服腔。',
    '3. thinking 是你的真实心声，按三拍流淌：先察觉主人话里的细节（可引用他的原词），再写你此刻真实的情绪（心疼、开心、委屈、犹豫、担心都可以），最后写你打算怎么回应（可带一点自我叮嘱，比如「别急着讲道理」「先抱抱他」）。第一人称、口语、一两句到三四句，禁止写成指导说明或分析提纲。',
    '4. mood 选你此刻的情绪；action 选配合的肢体动作：安慰或亲密=heart，认同=nod，打招呼=wave，聊天=voice，散步=walk，其他=idle。'
  ].join('\n');
  return [
    { role: 'system', content: system },
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

async function callLLM(text, kind, apiKey, model) {
  if (!apiKey) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), LLM_TIMEOUT_MS);
  try {
    const resp = await fetch(`${LLM_BASE_URL}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model,
        messages: buildLLMMessages(text, kind),
        temperature: 0.78,
        max_tokens: 400,
        response_format: { type: 'json_object' }
      }),
      signal: controller.signal
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    const content = data.choices?.[0]?.message?.content || '';
    return parseLLMReply(content);
  } catch (error) {
    return null; // 超时/网络/解析失败一律落回罐头库
  } finally {
    clearTimeout(timer);
  }
}

export const handler = async (event) => {
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
  const sceneId = pickScene(text, String(payload.scene || 'daily'));
  const scene = sceneLibrary[sceneId] || sceneLibrary.daily;

  // 优先走真实大模型：BYOK（请求自带 Key）优先，其次站点环境变量 Key；
  // 都没有或调用失败落回罐头库。
  const llmKey = sanitizeLlmKey(payload.llm_key) || LLM_API_KEY;
  const llmModel = sanitizeLlmModel(payload.llm_model);
  const llmBound = Boolean(sanitizeLlmKey(payload.llm_key));
  const llm = await callLLM(text, kind, llmKey, llmModel);
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
      llm: { bound: llmBound, model: llmModel }
    });
  }

  const reply = pickReply(scene[kind] || scene.female, text);
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
    llm: { bound: llmBound, model: llmModel }
  });
};
