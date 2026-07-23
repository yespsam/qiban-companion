export const CONVERSATION_STORE_VERSION = 1;
export const CONVERSATION_TTL_MS = 14 * 24 * 60 * 60 * 1000;
const conversationPrefix = 'qiban-conversation-v1';

function cleanTurn(turn) {
  const role = turn?.role === 'assistant' ? 'assistant' : turn?.role === 'user' ? 'user' : '';
  const content = String(turn?.content || turn?.text || '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 240);
  return role && content ? { role, content } : null;
}

export function conversationStorageKey(persona, scene) {
  const safePersona = persona === 'male' ? 'male' : 'female';
  const safeScene = String(scene || 'daily').replace(/[^a-z0-9_-]/gi, '').slice(0, 32) || 'daily';
  return `${conversationPrefix}:${safePersona}:${safeScene}`;
}

export function normalizeConversationRecord(value, now = Date.now()) {
  if (!value || typeof value !== 'object') return null;
  if (value.version !== CONVERSATION_STORE_VERSION) return null;
  if (!Number.isFinite(value.updatedAt) || now - value.updatedAt > CONVERSATION_TTL_MS) return null;
  const history = Array.isArray(value.history)
    ? value.history.map(cleanTurn).filter(Boolean).slice(-12)
    : [];
  return history.length ? { version: CONVERSATION_STORE_VERSION, updatedAt: value.updatedAt, history } : null;
}

export function loadConversation(storage, persona, scene, now = Date.now()) {
  if (!storage) return null;
  try {
    const raw = storage.getItem(conversationStorageKey(persona, scene));
    return raw ? normalizeConversationRecord(JSON.parse(raw), now) : null;
  } catch (error) {
    return null;
  }
}

export function saveConversation(storage, persona, scene, history, now = Date.now()) {
  if (!storage) return false;
  const cleanHistory = Array.isArray(history)
    ? history.map(cleanTurn).filter(Boolean).slice(-12)
    : [];
  if (!cleanHistory.length) return false;
  try {
    storage.setItem(conversationStorageKey(persona, scene), JSON.stringify({
      version: CONVERSATION_STORE_VERSION,
      updatedAt: now,
      history: cleanHistory
    }));
    return true;
  } catch (error) {
    return false;
  }
}
