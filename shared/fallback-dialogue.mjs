import {
  companionProfiles,
  interactionScenes,
  sceneById
} from './companion-data.mjs';

function cleanText(value, limit = 180) {
  return String(value || '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, limit);
}

function stablePick(values, seedText) {
  if (!Array.isArray(values) || !values.length) return '';
  const seed = [...seedText].reduce((sum, char) => sum + char.charCodeAt(0), seedText.length);
  return values[Math.abs(seed) % values.length] || '';
}

function previousUserText(history) {
  if (!Array.isArray(history)) return '';
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index]?.role !== 'user') continue;
    const content = cleanText(history[index]?.content || history[index]?.text, 120);
    if (content) return content;
  }
  return '';
}

export function inferSceneId(text, requested = 'daily') {
  const value = cleanText(text);
  if (/晚安|睡|困|休息/.test(value)) return 'goodnight';
  if (/想你|喜欢|抱|亲|爱/.test(value)) return 'miss';
  if (/累|难受|委屈|不开心|烦|崩|压力|害怕/.test(value)) return 'comfort';
  if (/走|散步|出去/.test(value)) return 'walk';
  if (/工作|学习|专注|开始做|任务|哪一步/.test(value)) return 'focus';
  return interactionScenes.some((scene) => scene.id === requested) ? requested : 'daily';
}

export function contextualFallbackReply({
  text,
  kind = 'female',
  scene = 'daily',
  history = []
}) {
  const value = cleanText(text);
  const personaKind = kind === 'male' ? 'male' : 'female';
  const profile = companionProfiles[personaKind];
  const previous = previousUserText(history);

  if (/刚才.*(?:说|问)|(?:说|问).*什么|还记得.*(?:说|问)/.test(value)) {
    return previous
      ? `你刚才说的是“${previous}”。我记得，我们可以从这里接着聊。`
      : '这是我们这段对话的第一句，我还没有更早的内容可以回想。';
  }

  if (/你是谁|你叫什么|名字是什么/.test(value)) {
    return `我是${profile.name}。你打开这里的时候，我会陪你说话。`;
  }

  if (/在吗|听得见|能听见|能不能.*(?:聊|对话)|可以.*(?:聊|对话)|正常.*(?:聊|对话)/.test(value)) {
    return '可以，我听见你了。这条消息已经收到，我们可以接着聊。';
  }

  if (/^(你好|嗨|哈喽|早上好|晚上好)[呀啊。！!，, ]*$/.test(value)) {
    return personaKind === 'male'
      ? '你好，我在。今天想从哪里开始聊？'
      : '你好呀，我在这里。今天想先聊什么？';
  }

  const resolvedScene = sceneById(inferSceneId(value, scene));
  const replies = resolvedScene.replies[personaKind] || resolvedScene.replies.female || [];
  return stablePick(replies, `${value}:${personaKind}:${resolvedScene.id}`)
    || resolvedScene.opening[personaKind]
    || resolvedScene.opening.female;
}
