// CrewVoice core — shared by the web server (server.js) and the MCP server (mcp-server.js).
//
// Capabilities:
//   translate(text, lang)           — construction-aware translation (Claude Opus 4.8)
//   cloneVoice(name, buffer, mime)   — ElevenLabs instant voice clone -> voice_id
//   speak(voiceId, text)            — ElevenLabs TTS in the cloned voice -> mp3 Buffer
//   transcribe(buffer, mime)        — ElevenLabs speech-to-text -> { text, language_code }
//   sendText(to, body)              — Twilio SMS delivery
//   placeVoicemailCall(to, audioUrl)— Twilio call that plays a hosted mp3 (voicemail in your voice)

import Anthropic from "@anthropic-ai/sdk";

const ELEVENLABS = "https://api.elevenlabs.io/v1";
const TTS_MODEL = "eleven_multilingual_v2"; // multilingual so the cloned voice speaks the target language

let _anthropic;
function anthropic() {
  if (!_anthropic) _anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
  return _anthropic;
}

function elevenKey() {
  const key = process.env.ELEVENLABS_API_KEY;
  if (!key) throw new Error("ELEVENLABS_API_KEY is not set.");
  return key;
}

// --- Construction-aware translation -----------------------------------------

const TRANSLATE_SYSTEM = `You are a translator for construction and roofing crews. You translate a contractor's spoken dispatch from English into the target language so a field crew or a customer can act on it immediately.

Rules:
- Output ONLY the translation. No preamble, no quotes, no notes, no alternatives.
- Preserve construction and roofing terminology precisely: TPO, EPDM, flashing, drip edge, underlayment, fascia, soffit, valley, ridge, penetration, elevation, square, course, etc. Use the term a working crew in the target language actually uses on site, not a literal dictionary gloss.
- Keep the tone direct and clear, like a foreman giving instructions or a contractor following up with a homeowner. Keep measurements and numbers exactly as given.
- If the input is already in the target language, return it unchanged.`;

export async function translate(text, targetLanguage) {
  const response = await anthropic().messages.create({
    model: "claude-opus-4-8",
    max_tokens: 1024,
    system: TRANSLATE_SYSTEM,
    messages: [
      {
        role: "user",
        content: `Target language: ${targetLanguage}\n\nText to translate:\n${text}`,
      },
    ],
  });
  const block = response.content.find((b) => b.type === "text");
  return block ? block.text.trim() : "";
}

// --- ElevenLabs voice ------------------------------------------------------

export async function cloneVoice(name, audioBuffer, mimeType) {
  const form = new FormData();
  form.append("name", name);
  form.append(
    "files",
    new Blob([audioBuffer], { type: mimeType || "audio/webm" }),
    "sample.webm"
  );
  const res = await fetch(`${ELEVENLABS}/voices/add`, {
    method: "POST",
    headers: { "xi-api-key": elevenKey() },
    body: form,
  });
  if (!res.ok) throw new Error(`ElevenLabs clone failed (${res.status}): ${await res.text()}`);
  return (await res.json()).voice_id;
}

export async function speak(voiceId, text) {
  const res = await fetch(`${ELEVENLABS}/text-to-speech/${voiceId}`, {
    method: "POST",
    headers: {
      "xi-api-key": elevenKey(),
      "Content-Type": "application/json",
      Accept: "audio/mpeg",
    },
    body: JSON.stringify({
      text,
      model_id: TTS_MODEL,
      voice_settings: { stability: 0.5, similarity_boost: 0.8 },
    }),
  });
  if (!res.ok) throw new Error(`ElevenLabs TTS failed (${res.status}): ${await res.text()}`);
  return Buffer.from(await res.arrayBuffer());
}

export async function transcribe(audioBuffer, mimeType) {
  const form = new FormData();
  form.append("model_id", "scribe_v1");
  form.append(
    "file",
    new Blob([audioBuffer], { type: mimeType || "audio/webm" }),
    "reply.webm"
  );
  const res = await fetch(`${ELEVENLABS}/speech-to-text`, {
    method: "POST",
    headers: { "xi-api-key": elevenKey() },
    body: form,
  });
  if (!res.ok) throw new Error(`ElevenLabs STT failed (${res.status}): ${await res.text()}`);
  return res.json();
}

// --- Twilio delivery (text + voicemail) -------------------------------------

let _twilio;
async function twilioClient() {
  if (_twilio) return _twilio;
  const { TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN } = process.env;
  if (!TWILIO_ACCOUNT_SID || !TWILIO_AUTH_TOKEN) {
    throw new Error("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set to send messages.");
  }
  const { default: twilio } = await import("twilio");
  _twilio = twilio(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN);
  return _twilio;
}

export async function sendText(to, body) {
  const from = process.env.TWILIO_FROM_NUMBER;
  if (!from) throw new Error("TWILIO_FROM_NUMBER is not set.");
  const client = await twilioClient();
  const msg = await client.messages.create({ to, from, body });
  return msg.sid;
}

// Places a phone call that plays a hosted mp3 — a voicemail in the contractor's voice.
// audioUrl must be publicly reachable by Twilio (see PUBLIC_BASE_URL in server.js).
export async function placeVoicemailCall(to, audioUrl) {
  const from = process.env.TWILIO_FROM_NUMBER;
  if (!from) throw new Error("TWILIO_FROM_NUMBER is not set.");
  const client = await twilioClient();
  const twiml = `<?xml version="1.0" encoding="UTF-8"?><Response><Play>${audioUrl}</Play></Response>`;
  const call = await client.calls.create({ to, from, twiml });
  return call.sid;
}
