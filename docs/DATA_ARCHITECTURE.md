# Qiban data architecture

The production web app is stateless on Netlify. It does not currently use a
server database. Data is divided into the following explicit layers.

## Shared catalog

`shared/companion-data.mjs` is the source of truth for:

- companion identity, names, dialogue lines, and action lines
- interaction scenes, fallback replies, and internal-thought prompts
- voice archetypes and Edge TTS voice IDs
- browser preference key names

Both `desktop-wallpaper/app.js` and the Netlify functions import this catalog.
Do not copy these records into either runtime.

## Browser conversation store

`shared/conversation-store.mjs` owns short conversation history:

- partitioned by companion and scene
- limited to 12 sanitized turns
- retained for 14 days
- stored only in the user's browser
- versioned so incompatible records can be discarded safely

Kimi API keys also stay in browser storage and are sent only with chat
requests. They are not written to Git or the conversation store.

## Netlify runtime

`netlify/functions/chat.mjs` is the single production conversation endpoint.
It tries Kimi first when a valid key is available, then returns a shared
catalog fallback so the input never remains blocked by a provider outage.

`netlify/functions/voice-*.mjs` use the same shared voice catalog.

## Local Python runtime

`ai-companion/project/config/` belongs to the offline pocket-box runtime. It is
not loaded by the Netlify site. Changes intended for both runtimes should be
made in the shared web catalog first, then adapted deliberately to YAML rather
than copied ad hoc.
