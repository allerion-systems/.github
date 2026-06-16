// CrewVoice web server — clone a voice, dispatch translated voice notes, deliver as text/voicemail.
// Core logic lives in lib.js (shared with the MCP server).

import express from "express";
import multer from "multer";
import dotenv from "dotenv";
import crypto from "crypto";
import {
  translate,
  cloneVoice,
  speak,
  transcribe,
  sendText,
  placeVoicemailCall,
} from "./lib.js";

dotenv.config();

const { ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, PUBLIC_BASE_URL, PORT = 3000 } = process.env;

if (!ANTHROPIC_API_KEY || !ELEVENLABS_API_KEY) {
  console.warn(
    "[CrewVoice] Missing ANTHROPIC_API_KEY and/or ELEVENLABS_API_KEY. " +
      "Copy .env.example to .env and fill them in — the API routes will fail until you do."
  );
}

const app = express();
app.use(express.json({ limit: "1mb" }));
app.use(express.static("public"));
const upload = multer({ limits: { fileSize: 25 * 1024 * 1024 } });

// Short-lived store for generated audio so Twilio can fetch it for voicemail playback.
const audioStore = new Map(); // id -> { buf, expires }
function stashAudio(buf) {
  const id = crypto.randomUUID();
  audioStore.set(id, { buf, expires: Date.now() + 60 * 60 * 1000 }); // 1h
  return id;
}
app.get("/audio/:id", (req, res) => {
  const entry = audioStore.get(req.params.id);
  if (!entry || entry.expires < Date.now()) return res.sendStatus(404);
  res.type("audio/mpeg").send(entry.buf);
});

// Agent 1: clone the contractor's voice from a ~30s sample.
app.post("/api/clone", upload.single("sample"), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: "No voice sample uploaded." });
    const name = req.body.name || `CrewVoice contractor ${Date.now()}`;
    const voiceId = await cloneVoice(name, req.file.buffer, req.file.mimetype);
    res.json({ voiceId });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// Agent 2: dispatch — English in, translated voice note out (in the cloned voice).
app.post("/api/dispatch", async (req, res) => {
  try {
    const { text, targetLanguage, voiceId } = req.body || {};
    if (!text || !targetLanguage || !voiceId) {
      return res.status(400).json({ error: "text, targetLanguage and voiceId are required." });
    }
    const translation = await translate(text, targetLanguage);
    const audio = await speak(voiceId, translation);
    res.json({ translation, audio: audio.toString("base64"), mimeType: "audio/mpeg" });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// Delivery: translate, then send to a recipient's phone as a text or a voicemail.
app.post("/api/send", async (req, res) => {
  try {
    const { text, targetLanguage, voiceId, to, channel = "text" } = req.body || {};
    if (!text || !targetLanguage || !to) {
      return res.status(400).json({ error: "text, targetLanguage and to are required." });
    }
    const translation = await translate(text, targetLanguage);

    if (channel === "text") {
      const sid = await sendText(to, translation);
      return res.json({ translation, channel, sid });
    }

    if (channel === "voicemail") {
      if (!voiceId) return res.status(400).json({ error: "voiceId is required for voicemail." });
      if (!PUBLIC_BASE_URL) {
        return res.status(400).json({
          error: "PUBLIC_BASE_URL must be set so Twilio can fetch the generated audio.",
        });
      }
      const audio = await speak(voiceId, translation);
      const id = stashAudio(audio);
      const sid = await placeVoicemailCall(to, `${PUBLIC_BASE_URL}/audio/${id}`);
      return res.json({ translation, channel, sid });
    }

    res.status(400).json({ error: `Unknown channel "${channel}".` });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// Agent 3: two-way — crew/customer replies in their language, contractor gets English.
app.post("/api/transcribe", upload.single("reply"), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: "No reply audio uploaded." });
    const { text, language_code } = await transcribe(req.file.buffer, req.file.mimetype);
    const english = await translate(text, "English");
    res.json({ original: text, languageCode: language_code, english });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

app.get("/api/health", (_req, res) => {
  res.json({
    ok: true,
    anthropic: Boolean(ANTHROPIC_API_KEY),
    elevenlabs: Boolean(ELEVENLABS_API_KEY),
    twilio: Boolean(process.env.TWILIO_ACCOUNT_SID),
  });
});

app.listen(PORT, () => console.log(`CrewVoice running at http://localhost:${PORT}`));
