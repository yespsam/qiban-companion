import { jsonResponse, voiceStatusBody } from './voice-data.mjs';

export const handler = async () => jsonResponse(voiceStatusBody());
