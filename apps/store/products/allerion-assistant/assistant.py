#!/usr/bin/env python3
"""Allerion Assistant — your own self-hostable AI chat, powered by Claude.

A complete, brandable AI assistant you run yourself: a streaming chat web UI
plus a backend built on the official Anthropic SDK. Point it at the Anthropic
API directly, or at your own Anthropic-compatible gateway via ANTHROPIC_BASE_URL.

    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 assistant.py                 # http://127.0.0.1:8077

Config (all optional, via environment):
    ANTHROPIC_API_KEY     your key (required)
    ANTHROPIC_BASE_URL    point at your own gateway instead of api.anthropic.com
    ASSISTANT_MODEL       default: claude-opus-4-8
    ASSISTANT_EFFORT      low | medium | high | xhigh | max   (default: high)
    ASSISTANT_SYSTEM      the assistant's persona / system prompt
    ASSISTANT_MAX_TOKENS  default: 8000
    ASSISTANT_NAME        UI title (default: Allerion Assistant)
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import anthropic

MODEL = os.environ.get("ASSISTANT_MODEL", "claude-opus-4-8")
EFFORT = os.environ.get("ASSISTANT_EFFORT", "high")
MAX_TOKENS = int(os.environ.get("ASSISTANT_MAX_TOKENS", "8000"))
NAME = os.environ.get("ASSISTANT_NAME", "Allerion Assistant")
SYSTEM = os.environ.get(
    "ASSISTANT_SYSTEM",
    f"You are {NAME}, a sharp, helpful AI assistant. Be clear and concise; "
    "lead with the answer, then the reasoning. Use code blocks for code.",
)

# Reads ANTHROPIC_API_KEY (and optional ANTHROPIC_BASE_URL) from the environment.
client = anthropic.Anthropic()

# In-memory conversation store, keyed by browser-supplied session id. Swap for a
# database to persist across restarts / scale across processes.
SESSIONS: dict[str, list] = {}


def stream_reply(session_id: str, user_message: str):
    """Yield (kind, text) tuples — kind is 'thinking', 'text', or 'error'."""
    history = SESSIONS.setdefault(session_id, [])
    history.append({"role": "user", "content": user_message})
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": EFFORT},
            messages=history,
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta":
                    if event.delta.type == "thinking_delta":
                        yield "thinking", event.delta.thinking
                    elif event.delta.type == "text_delta":
                        yield "text", event.delta.text
            final = stream.get_final_message()
    except anthropic.APIStatusError as e:  # surface a clean message to the UI
        history.pop()  # don't keep a turn we couldn't answer
        yield "error", f"API error {e.status_code}: {e.message}"
        return
    except anthropic.APIConnectionError:
        history.pop()
        yield "error", "Could not reach the API. Check your network / base URL."
        return

    if final.stop_reason == "refusal":
        history.pop()
        yield "error", "The model declined to answer that request."
        return

    # Persist the full assistant turn (content blocks, incl. thinking) so the
    # next turn replays them unchanged — the correct multi-turn pattern on Opus.
    history.append({"role": "assistant", "content": final.content})


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__</title><style>
:root{--bg:#07090a;--panel:#0f1411;--line:#1f2a22;--line2:#2b3a2e;--ink:#e9f1ea;
--mut:#7e8d82;--nv:#76b900;--nv2:#b6ff3a;--glow:rgba(118,185,0,.25);
--mono:ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--ink);display:flex;flex-direction:column;
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
body::before{content:"";position:fixed;inset:0;z-index:-1;
background:radial-gradient(900px 500px at 50% -15%,rgba(118,185,0,.10),transparent 70%)}
header{border-bottom:1px solid var(--line);padding:14px 20px;display:flex;align-items:center;gap:10px;
background:rgba(7,9,10,.7);backdrop-filter:blur(8px)}
header .mk{color:var(--nv)}
header b{font-family:var(--mono);letter-spacing:.18em;text-transform:uppercase;font-size:14px}
header .m{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--mut);letter-spacing:.08em}
#log{flex:1;overflow-y:auto;padding:24px;max-width:820px;width:100%;margin:0 auto}
.msg{margin:0 0 18px;display:flex;gap:12px}
.msg .who{font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;
color:var(--mut);min-width:54px;padding-top:3px}
.msg.u .who{color:var(--nv2)}.msg.a .who{color:var(--nv)}
.bubble{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 15px;
white-space:pre-wrap;word-wrap:break-word;flex:1}
.msg.u .bubble{background:#0b120c;border-color:var(--line2)}
.think{border:1px dashed var(--line2);border-radius:8px;padding:8px 12px;margin:0 0 8px;
color:var(--mut);font-size:13px;white-space:pre-wrap;display:none}
.think.show{display:block}
.err{color:#ff8a8a;border-color:#5a2b2b}
code,pre{font-family:var(--mono);font-size:13px}
pre{background:#070a08;border:1px solid var(--line2);border-radius:8px;padding:12px;overflow-x:auto}
form{border-top:1px solid var(--line);padding:14px 20px;display:flex;gap:10px;
max-width:820px;width:100%;margin:0 auto}
textarea{flex:1;background:#070a08;border:1px solid var(--line2);color:var(--ink);border-radius:10px;
padding:11px 14px;font:inherit;resize:none;max-height:160px}
textarea:focus{outline:none;border-color:var(--nv);box-shadow:0 0 0 3px var(--glow)}
button{font-family:var(--mono);font-size:13px;letter-spacing:.08em;text-transform:uppercase;
background:var(--nv);color:#06140a;border:1px solid var(--nv);border-radius:10px;padding:0 20px;
font-weight:700;cursor:pointer}
button:disabled{opacity:.5;cursor:default}
.cursor::after{content:"\\2588";color:var(--nv);animation:blink 1s steps(2) infinite}
@keyframes blink{50%{opacity:0}}
</style></head><body>
<header><span class="mk">&#9650;</span><b>__NAME__</b><span class="m">__MODEL__</span></header>
<div id="log"></div>
<form id="f">
  <textarea id="i" rows="1" placeholder="Message your assistant…" autofocus></textarea>
  <button id="b" type="submit">Send</button>
</form>
<script>
const sid = localStorage.sid || (localStorage.sid = Math.random().toString(36).slice(2));
const log = document.getElementById('log'), form = document.getElementById('f');
const input = document.getElementById('i'), btn = document.getElementById('b');
input.addEventListener('input', () => { input.style.height='auto'; input.style.height=input.scrollHeight+'px'; });
input.addEventListener('keydown', e => { if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); form.requestSubmit(); }});
function add(cls, who){ const m=document.createElement('div'); m.className='msg '+cls;
  m.innerHTML='<div class="who">'+who+'</div>'; const t=document.createElement('div'); t.className='think';
  const b=document.createElement('div'); b.className='bubble'; m.append(t,b); log.append(m);
  log.scrollTop=log.scrollHeight; return {think:t, bubble:b, msg:m}; }
form.addEventListener('submit', async e => {
  e.preventDefault(); const text=input.value.trim(); if(!text) return;
  input.value=''; input.style.height='auto'; btn.disabled=true;
  add('u','You').bubble.textContent=text;
  const out=add('a','AI'); out.bubble.classList.add('cursor');
  try {
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session_id:sid,message:text})});
    const reader=r.body.getReader(), dec=new TextDecoder(); let buf='';
    for(;;){ const {value,done}=await reader.read(); if(done) break; buf+=dec.decode(value,{stream:true});
      let i; while((i=buf.indexOf('\\n\\n'))>=0){ const line=buf.slice(0,i); buf=buf.slice(i+2);
        if(!line.startsWith('data: ')) continue; const ev=JSON.parse(line.slice(6));
        if(ev.kind==='thinking'){ out.think.classList.add('show'); out.think.textContent+=ev.text; }
        else if(ev.kind==='text'){ out.bubble.textContent+=ev.text; }
        else if(ev.kind==='error'){ out.bubble.classList.add('err'); out.bubble.textContent=ev.text; }
        log.scrollTop=log.scrollHeight; } }
  } catch(err){ out.bubble.classList.add('err'); out.bubble.textContent='Connection lost.'; }
  out.bubble.classList.remove('cursor'); btn.disabled=false; input.focus();
});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "AllerionAssistant/1.0"

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            body = (PAGE.replace("__NAME__", NAME).replace("__MODEL__", MODEL)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/healthz":
            body = json.dumps({"ok": True, "model": MODEL}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/api/chat":
            return self.send_error(404)
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            data = json.loads(self.rfile.read(n) or "{}")
        except json.JSONDecodeError:
            return self.send_error(400)
        session_id = str(data.get("session_id") or "default")
        message = (data.get("message") or "").strip()
        if not message:
            return self.send_error(400)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for kind, text in stream_reply(session_id, message):
            chunk = f"data: {json.dumps({'kind': kind, 'text': text})}\n\n".encode()
            try:
                self.wfile.write(chunk)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                break  # browser navigated away mid-stream


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8077)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("WARNING: ANTHROPIC_API_KEY is not set — requests will fail until it is.")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"{NAME} on http://{args.host}:{args.port}  (model: {MODEL}, effort: {EFFORT})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
