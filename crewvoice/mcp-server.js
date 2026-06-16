// CrewVoice MCP server — exposes CrewVoice as tools inside ChatGPT, Claude, or any MCP client.
//
// Run over stdio:  node mcp-server.js
// Then register it with your MCP client (see README → "Use it inside Claude/ChatGPT").
//
// Tools:
//   clone_voice        — clone a contractor's voice from a local audio file
//   translate_dispatch — construction-aware English -> target-language translation (text only)
//   send_text_dispatch — translate, then deliver as an SMS in the recipient's language

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFile } from "node:fs/promises";
import path from "node:path";
import dotenv from "dotenv";
import { translate, cloneVoice, sendText } from "./lib.js";

dotenv.config();

const server = new McpServer({ name: "crewvoice", version: "0.1.0" });

server.registerTool(
  "clone_voice",
  {
    description:
      "Clone a contractor's voice from a local audio sample (~30s). Returns a voiceId used for later dispatches.",
    inputSchema: {
      audioPath: z.string().describe("Absolute or relative path to an audio file (mp3/wav/webm/m4a)."),
      name: z.string().optional().describe("A label for this voice, e.g. the contractor's name."),
    },
  },
  async ({ audioPath, name }) => {
    const buf = await readFile(audioPath);
    const ext = path.extname(audioPath).slice(1).toLowerCase();
    const mime = { mp3: "audio/mpeg", wav: "audio/wav", webm: "audio/webm", m4a: "audio/mp4" }[ext]
      || "audio/mpeg";
    const voiceId = await cloneVoice(name || "CrewVoice contractor", buf, mime);
    return { content: [{ type: "text", text: `Voice cloned. voiceId: ${voiceId}` }] };
  }
);

server.registerTool(
  "translate_dispatch",
  {
    description:
      "Translate a construction dispatch from English into the crew's or customer's language, preserving trade terminology (TPO, flashing, drip edge, etc.). Returns the translated text only.",
    inputSchema: {
      text: z.string().describe("The message in English."),
      targetLanguage: z.string().describe("Target language, e.g. 'Spanish'."),
    },
  },
  async ({ text, targetLanguage }) => {
    const translation = await translate(text, targetLanguage);
    return { content: [{ type: "text", text: translation }] };
  }
);

server.registerTool(
  "send_text_dispatch",
  {
    description:
      "Translate an English dispatch into the recipient's language and deliver it as an SMS text. Use for crew dispatches or customer/bid follow-ups. Requires Twilio configuration.",
    inputSchema: {
      text: z.string().describe("The message in English."),
      targetLanguage: z.string().describe("Recipient's language, e.g. 'Spanish'."),
      to: z.string().describe("Recipient phone number in E.164 format, e.g. +14155551234."),
    },
  },
  async ({ text, targetLanguage, to }) => {
    const translation = await translate(text, targetLanguage);
    const sid = await sendText(to, translation);
    return {
      content: [
        { type: "text", text: `Sent to ${to} (sid ${sid}).\n\nDelivered text:\n${translation}` },
      ],
    };
  }
);

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("CrewVoice MCP server running on stdio.");
