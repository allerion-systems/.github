# CrewVoice

**Your voice. Every worker's language.**

A contractor records their voice once. Then they type a message in English, pick a
crew member or a customer, and CrewVoice delivers it as a **voicemail or text in the
recipient's language — in the contractor's own cloned voice.**

Built for construction: dispatch a job to a Spanish-speaking crew, or follow up on a
bid with a homeowner who doesn't speak English — all in the voice they already know.
It also ships as an **MCP server**, so it plugs straight into the ChatGPT or Claude
you already use.

> CrewVoice by Allerion · $149/mo · early access.

---

## How it works

| Agent | What it does | Tech |
|-------|-------------|------|
| **Voice Cloner** | 30-second sample → a voice model that speaks any language as that person | ElevenLabs |
| **Translator** | English → the recipient's language, preserving trade terms (TPO, flashing, drip edge) | Claude Opus 4.8 |
| **Dispatcher** | Speaks the translation in the cloned voice; delivers as voicemail or text | ElevenLabs TTS + Twilio |
| **Two-way** | Crew/customer replies in their language → contractor gets English | ElevenLabs STT + Claude |

## Setup

```bash
cd crewvoice
npm install
cp .env.example .env   # fill in ANTHROPIC_API_KEY and ELEVENLABS_API_KEY (Twilio optional)
npm start              # http://localhost:3000
```

- **`ANTHROPIC_API_KEY`** and **`ELEVENLABS_API_KEY`** are required for the core demo
  (clone → translate → speak).
- **Twilio** vars are optional — needed only to deliver texts/voicemails to real phones.
- For the **voicemail** channel, Twilio must be able to reach this server, so set
  `PUBLIC_BASE_URL` (an ngrok URL in dev, or your deployed domain).

## Web demo

Open `http://localhost:3000`:

1. **Clone your voice** — record ~30s.
2. **Send a dispatch** — type in English, pick a language, hear it back in *your* voice.
3. **Two-way** — record a reply in any language, get it back in English.

## HTTP API

| Endpoint | Body | Returns |
|----------|------|---------|
| `POST /api/clone` | multipart `sample` (audio) | `{ voiceId }` |
| `POST /api/dispatch` | `{ text, targetLanguage, voiceId }` | `{ translation, audio (base64 mp3) }` |
| `POST /api/send` | `{ text, targetLanguage, to, channel: "text"\|"voicemail", voiceId? }` | `{ translation, sid }` |
| `POST /api/transcribe` | multipart `reply` (audio) | `{ original, languageCode, english }` |

## Use it inside Claude / ChatGPT (MCP)

CrewVoice ships as an MCP server (`mcp-server.js`) exposing three tools:
`clone_voice`, `translate_dispatch`, and `send_text_dispatch`.

Register it with any MCP client. For **Claude Code**:

```bash
claude mcp add crewvoice -- node /absolute/path/to/crewvoice/mcp-server.js
```

Or add it to a client's MCP config manually:

```json
{
  "mcpServers": {
    "crewvoice": {
      "command": "node",
      "args": ["/absolute/path/to/crewvoice/mcp-server.js"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-...",
        "ELEVENLABS_API_KEY": "...",
        "TWILIO_ACCOUNT_SID": "...",
        "TWILIO_AUTH_TOKEN": "...",
        "TWILIO_FROM_NUMBER": "+1..."
      }
    }
  }
}
```

Then, from chat: *"Send the crew this in Spanish: start the south elevation, underlayment
down before noon"* — and CrewVoice translates and texts it.

## Notes

- This is an early-access MVP. Voice cloning uses ElevenLabs instant cloning; for
  production, get consent from anyone whose voice you clone.
- Numbers and vendor choices are illustrative — validate before committing spend.
