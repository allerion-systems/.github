#!/usr/bin/env python3
"""Allerion platform — marketing site + embedded CRM in one app.

Zero dependencies (Python standard library only): an HTTP server that serves
the Allerion marketing site, captures access requests as CRM leads in SQLite,
and exposes a lightweight CRM dashboard + JSON API over the same data.

    python3 server.py                 # http://127.0.0.1:8099
    python3 server.py --port 9000

Routes
    GET  /                 marketing landing page (lead-capture form)
    POST /api/leads        create a lead (form post or JSON)
    GET  /crm              CRM dashboard (pipeline + lead list)
    GET  /api/leads        list leads as JSON
    POST /api/leads/<id>/status   advance a lead's pipeline status
    GET  /healthz          health check
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sqlite3
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import billing

DB_PATH = os.environ.get("ALLERION_CRM_DB", os.path.join(os.path.dirname(__file__), "crm.db"))
PIPELINE = ["new", "contacted", "qualified", "won", "lost"]


# --------------------------------------------------------------------------- db
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                email      TEXT NOT NULL,
                company    TEXT,
                interest   TEXT,
                message    TEXT,
                status     TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL
            )
            """
        )


def create_lead(data: dict) -> dict:
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    if not name or not email:
        raise ValueError("name and email are required")
    row = {
        "name": name,
        "email": email,
        "company": (data.get("company") or "").strip(),
        "interest": (data.get("interest") or "").strip(),
        "message": (data.get("message") or "").strip(),
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO leads (name,email,company,interest,message,status,created_at) "
            "VALUES (:name,:email,:company,:interest,:message,:status,:created_at)",
            row,
        )
        row["id"] = cur.lastrowid
    return row


def list_leads() -> list[dict]:
    with db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM leads ORDER BY id DESC")]


def set_status(lead_id: int, status: str) -> bool:
    if status not in PIPELINE:
        raise ValueError(f"status must be one of {PIPELINE}")
    with db() as conn:
        cur = conn.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))
        return cur.rowcount > 0


def pipeline_counts() -> dict:
    counts = {s: 0 for s in PIPELINE}
    with db() as conn:
        for r in conn.execute("SELECT status, COUNT(*) c FROM leads GROUP BY status"):
            counts[r["status"]] = r["c"]
    return counts


# ------------------------------------------------------------------------- views
CSS = """
:root{
  --bg:#07090a;--bg2:#0b0f0c;--panel:#0f1411;--line:#1f2a22;--line2:#2b3a2e;
  --ink:#e9f1ea;--mut:#7e8d82;--nv:#76b900;--nv2:#b6ff3a;--glow:rgba(118,185,0,.30);
  --mono:ui-monospace,"SFMono-Regular","JetBrains Mono",Menlo,Consolas,monospace
}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;z-index:-2;
  background:radial-gradient(900px 520px at 50% -12%,rgba(118,185,0,.12),transparent 70%),
             linear-gradient(var(--bg2),var(--bg))}
body::after{content:"";position:fixed;inset:0;z-index:-1;opacity:.55;
  background-image:linear-gradient(rgba(118,185,0,.05) 1px,transparent 1px),
                   linear-gradient(90deg,rgba(118,185,0,.05) 1px,transparent 1px);
  background-size:46px 46px;-webkit-mask-image:radial-gradient(ellipse at 50% 0,#000,transparent 82%);
  mask-image:radial-gradient(ellipse at 50% 0,#000,transparent 82%)}
a{color:var(--nv);text-decoration:none}
.wrap{max-width:1040px;margin:0 auto;padding:0 24px}
.mono{font-family:var(--mono);text-transform:uppercase;letter-spacing:.18em;font-size:12px;color:var(--mut)}
.nv{color:var(--nv)}
header{position:sticky;top:0;z-index:10;backdrop-filter:blur(10px);
  background:rgba(7,9,10,.72);border-bottom:1px solid var(--line)}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:62px}
.brand{font-family:var(--mono);font-weight:700;letter-spacing:.22em;font-size:14px}
.brand .mk{color:var(--nv)}
nav a{margin-left:22px;font-family:var(--mono);font-size:12px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--mut)}
nav a:hover{color:var(--ink)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--nv);
  box-shadow:0 0 0 0 var(--glow);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 var(--glow)}70%{box-shadow:0 0 0 10px transparent}100%{box-shadow:0 0 0 0 transparent}}
.hero{position:relative;padding:98px 0 56px;text-align:center}
.hero .ey{display:inline-flex;align-items:center;gap:10px;margin-bottom:22px;
  padding:6px 14px;border:1px solid var(--line2);border-radius:999px;background:var(--panel)}
.hero h1{font-size:56px;line-height:1.03;margin:0 0 18px;letter-spacing:-.025em;font-weight:800}
.hero h1 .g{background:linear-gradient(90deg,var(--nv),var(--nv2));-webkit-background-clip:text;
  background-clip:text;color:transparent}
.hero p{font-size:19px;color:var(--mut);max-width:660px;margin:0 auto 30px}
.cta{display:inline-flex;gap:12px;flex-wrap:wrap;justify-content:center}
.btn{display:inline-block;font-family:var(--mono);font-size:13px;letter-spacing:.1em;text-transform:uppercase;
  background:var(--nv);color:#06140a;padding:13px 24px;border-radius:8px;font-weight:700;border:1px solid var(--nv);
  transition:transform .15s,box-shadow .15s,background .15s;box-shadow:0 0 24px var(--glow);cursor:pointer}
.btn:hover{transform:translateY(-2px);box-shadow:0 0 38px var(--glow);background:var(--nv2);border-color:var(--nv2)}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line2);box-shadow:none}
.btn.ghost:hover{border-color:var(--nv);color:var(--nv)}
section .lbl{display:flex;align-items:center;gap:14px;margin:62px 0 22px;
  font-family:var(--mono);text-transform:uppercase;letter-spacing:.18em;font-size:12px;color:var(--mut)}
section .lbl::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--line2),transparent)}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
.card{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:24px;
  transition:border-color .2s,transform .2s,box-shadow .2s;overflow:hidden}
.card::before{content:"";position:absolute;left:0;top:0;width:32px;height:32px;
  border-top:2px solid var(--nv);border-left:2px solid var(--nv);opacity:.45;transition:opacity .2s}
.card::after{content:"";position:absolute;right:0;bottom:0;width:32px;height:32px;
  border-bottom:2px solid var(--nv);border-right:2px solid var(--nv);opacity:.45;transition:opacity .2s}
.card:hover{border-color:var(--line2);transform:translateY(-3px);box-shadow:0 14px 44px rgba(0,0,0,.55)}
.card:hover::before,.card:hover::after{opacity:1}
.card .ix{font-family:var(--mono);font-size:12px;color:var(--nv);letter-spacing:.16em}
.card h3{margin:8px 0 6px;font-size:18px}
.card p{margin:0;color:var(--mut);font-size:14px}
.telem{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px 0}
.telem .t{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
.telem .k{font-family:var(--mono);font-size:11px;color:var(--mut);letter-spacing:.14em;text-transform:uppercase}
.telem .v{font-size:26px;font-weight:800;margin-top:4px}
.telem .v small{color:var(--nv);font-size:13px;font-weight:600}
.bars{display:flex;gap:3px;align-items:flex-end;height:24px;margin-top:12px}
.bars i{flex:1;background:var(--nv);opacity:.7;border-radius:1px;height:30%;animation:eq 1.2s ease-in-out infinite}
.bars i:nth-child(2){animation-delay:.12s}.bars i:nth-child(3){animation-delay:.24s}
.bars i:nth-child(4){animation-delay:.36s}.bars i:nth-child(5){animation-delay:.48s}
.bars i:nth-child(6){animation-delay:.6s}.bars i:nth-child(7){animation-delay:.72s}
@keyframes eq{0%,100%{height:25%}50%{height:100%}}
.price{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.price .card{text-align:center}
.price .card.feat{border-color:var(--nv);box-shadow:0 0 30px var(--glow)}
.price .amt{font-size:32px;font-weight:800;margin:10px 0}
.price .amt small{font-size:13px;color:var(--mut);font-weight:500;font-family:var(--mono)}
form{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:26px;margin:18px 0 80px}
label{display:block;font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--mut);margin:14px 0 6px}
input,select,textarea{width:100%;background:#070a08;border:1px solid var(--line2);color:var(--ink);
  border-radius:8px;padding:11px 13px;font:inherit;transition:border-color .15s,box-shadow .15s}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--nv);box-shadow:0 0 0 3px var(--glow)}
textarea{min-height:88px;resize:vertical}
table{width:100%;border-collapse:collapse;margin:16px 0}
th,td{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);font-size:14px}
th{font-family:var(--mono);font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
td .em{color:var(--mut);font-size:12px;font-family:var(--mono)}
.pill{display:inline-block;padding:3px 11px;border-radius:999px;font-size:11px;font-family:var(--mono);
  text-transform:uppercase;letter-spacing:.08em;border:1px solid var(--line2)}
.s-new{color:#7ab8ff;border-color:#274a6b}.s-contacted{color:var(--nv2);border-color:#3a4a16}
.s-qualified{color:var(--nv);border-color:#2d4a12}.s-won{color:#39e07d;border-color:#1d5a35}.s-lost{color:#8b97a3}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:18px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;text-align:center}
.kpi b{display:block;font-size:30px;font-weight:800;color:var(--nv)}
.kpi span{font-family:var(--mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}
footer{border-top:1px solid var(--line);color:var(--mut);padding:30px 0;text-align:center}
.note{color:var(--mut);font-size:12px;font-family:var(--mono);letter-spacing:.04em}
code{font-family:var(--mono);color:var(--nv);font-size:13px}
"""

CAPABILITIES = [
    ("Digital Twin", "3D BIM infrastructure intelligence — real-time spatial data at industrial scale."),
    ("Construction ERP", "Autonomous cost estimation, BOQ generation, CAD/BIM takeoff."),
    ("Agent Orchestration", "Multi-agent swarms — agents hiring agents via the A2A protocol."),
    ("Sovereign AI", "Self-hosted LLM deployment on private infrastructure — your models, your silicon."),
]

#   name, amount, period, description, cta-tier (None → request-access anchor)
PRICING = [
    ("Gateway", "$0", "/mo to start", "Branded OpenAI-compatible API at api.allerion.io. Pay only for usage.", None),
    ("Team", "$2k", "/mo", "Virtual keys, budgets, metered Stripe billing, priority routing.", "team"),
    ("Sovereign", "Custom", "", "Self-hosted GPU deployment + on-prem agent orchestration.", None),
]


def page(title: str, body: str) -> bytes:
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body>
<header><div class="wrap">
  <div class="brand"><span class="mk">&#9650;</span> ALLERION<span class="nv">.IO</span></div>
  <nav><a href="/">System</a><a href="/#pricing">Pricing</a><a href="/crm">Console</a></nav>
</div></header>
{body}
<footer><div class="wrap"><div class="mono"><span class="nv">&#9650;</span> Allerion Systems — autonomous intelligence for the built world</div>
<div class="note" style="margin-top:8px">We don't sell software. We deploy intelligence.</div></div></footer>
</body></html>"""
    return doc.encode()


def landing() -> bytes:
    caps = "".join(
        f'<div class="card"><div class="ix">{i:02d}</div>'
        f'<h3>{html.escape(t)}</h3><p>{html.escape(d)}</p></div>'
        for i, (t, d) in enumerate(CAPABILITIES, 1)
    )
    def price_cta(tier):
        if tier:
            return f'<p style="margin:16px 0 0"><a class="btn" href="/buy/{tier}">Subscribe &rarr;</a></p>'
        return '<p style="margin:16px 0 0"><a class="btn ghost" href="#access">Request access</a></p>'

    price = "".join(
        f'<div class="card{" feat" if i == 1 else ""}"><div class="ix mono">{html.escape(n)}</div>'
        f'<div class="amt">{html.escape(a)} <small>{html.escape(p)}</small></div>'
        f'<p>{html.escape(d)}</p>{price_cta(tier)}</div>'
        for i, (n, a, p, d, tier) in enumerate(PRICING)
    )
    bars = "".join("<i></i>" for _ in range(7))
    body = f"""
<div class="hero"><div class="wrap">
  <div class="ey"><span class="dot"></span><span class="mono">Autonomous systems &middot; online</span></div>
  <h1>Autonomous intelligence<br>for the <span class="g">built world</span>.</h1>
  <p>We design, deploy, and operate multi-agent AI systems for infrastructure,
     construction, and industrial operations. Our agents estimate. Our agents build.
     Our agents never sleep.</p>
  <div class="cta">
    <a class="btn" href="#access">Request access</a>
    <a class="btn ghost" href="/crm">Open console</a>
  </div>
</div></div>
<div class="wrap">
  <div class="telem">
    <div class="t"><div class="k">Agents online</div><div class="v">80 <small>&#9650;</small></div></div>
    <div class="t"><div class="k">Models routed</div><div class="v">80+ <small>NIM</small></div></div>
    <div class="t"><div class="k">Fleet uptime</div><div class="v">99.9<small>%</small></div></div>
    <div class="t"><div class="k">Throughput</div><div class="bars">{bars}</div></div>
  </div>
  <section><div class="lbl">// Capabilities</div></section>
  <div class="grid">{caps}</div>
  <section id="pricing"><div class="lbl">// Pricing</div></section>
  <div class="price">{price}</div>
  <section id="access"><div class="lbl">// Request access</div></section>
  <form method="post" action="/api/leads">
    <label>Name</label><input name="name" required>
    <label>Work email</label><input name="email" type="email" required>
    <label>Company</label><input name="company">
    <label>Interest</label>
    <select name="interest">
      <option>AI Gateway</option><option>Agent Orchestration</option>
      <option>Sovereign AI</option><option>Construction ERP</option><option>Digital Twin</option>
    </select>
    <label>Message</label><textarea name="message" placeholder="What are you building?"></textarea>
    <p style="margin-top:18px"><button class="btn" type="submit">Request access &rarr;</button></p>
    <p class="note">// submitting creates a lead in the embedded CRM</p>
  </form>
</div>"""
    return page("Allerion — Autonomous AI for the built world", body)


def crm_page() -> bytes:
    counts = pipeline_counts()
    kpis = "".join(
        f'<div class="kpi"><b>{counts[s]}</b><span>{s}</span></div>' for s in PIPELINE
    )
    rows = []
    for L in list_leads():
        opts = "".join(
            f'<option value="{s}"{" selected" if s == L["status"] else ""}>{s}</option>'
            for s in PIPELINE
        )
        rows.append(
            f"<tr><td>#{L['id']}</td><td>{html.escape(L['name'])}<br>"
            f"<span class='note'>{html.escape(L['email'])}</span></td>"
            f"<td>{html.escape(L['company'] or '—')}</td>"
            f"<td>{html.escape(L['interest'] or '—')}</td>"
            f"<td><span class='pill s-{L['status']}'>{L['status']}</span></td>"
            f"<td><form method='post' action='/api/leads/{L['id']}/status' "
            f"style='background:none;border:none;padding:0;margin:0;display:flex;gap:6px'>"
            f"<select name='status'>{opts}</select>"
            f"<button class='btn' style='padding:6px 12px'>Save</button></form></td></tr>"
        )
    table = (
        "<table><tr><th>ID</th><th>Lead</th><th>Company</th><th>Interest</th>"
        "<th>Status</th><th>Update</th></tr>" + ("".join(rows) or
        "<tr><td colspan='6' class='note'>No leads yet — submit the form on the landing page.</td></tr>")
        + "</table>"
    )
    body = f"""<div class="wrap" style="padding-top:40px">
  <div class="ey" style="display:inline-flex;align-items:center;gap:10px;padding:6px 14px;
       border:1px solid var(--line2);border-radius:999px;background:var(--panel)">
    <span class="dot"></span><span class="mono">CRM console &middot; live</span></div>
  <section><div class="lbl">// Pipeline telemetry</div></section>
  <div class="kpis">{kpis}</div>
  {table}
  <p class="note">// embedded CRM over the same SQLite store &middot; JSON API at <code>/api/leads</code></p>
</div>"""
    return page("Allerion Console — CRM", body)


# ----------------------------------------------------------------------- handler
class Handler(BaseHTTPRequestHandler):
    server_version = "AllerionPlatform/0.1"

    def log_message(self, *a):  # quieter logs
        pass

    def _send(self, code: int, body: bytes, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj, indent=2).encode(), "application/json")

    def _body_params(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n).decode() if n else ""
        ctype = self.headers.get("Content-Type", "")
        if "application/json" in ctype:
            try:
                return json.loads(raw or "{}")
            except json.JSONDecodeError:
                return {}
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            self._send(200, landing())
        elif path == "/crm":
            self._send(200, crm_page())
        elif path == "/api/leads":
            self._json(200, {"leads": list_leads()})
        elif path.startswith("/buy/"):
            self._checkout(path.split("/")[2])
        elif path == "/healthz":
            self._json(200, {"ok": True, "billing": billing.live()})
        else:
            self._send(404, page("Not found", '<div class="wrap"><div class="hero"><h1>404</h1></div></div>'))

    def _checkout(self, tier: str):
        """Create a Stripe Checkout Session and redirect the buyer to it."""
        if tier not in billing.TIERS:
            return self._send(404, page("Unknown plan",
                '<div class="wrap"><div class="hero"><h1>Unknown plan</h1>'
                '<p>No such tier.</p><a class="btn" href="/#pricing">Back to pricing</a></div></div>'))
        if not billing.live():
            return self._send(200, page("Checkout — configuring", f"""
<div class="wrap"><div class="hero">
  <div class="ey"><span class="dot"></span><span class="mono">Billing &middot; pending key</span></div>
  <h1>Almost <span class="g">live</span>.</h1>
  <p>Stripe Checkout for the <b>{html.escape(tier.title())}</b> plan is wired and ready —
     it just needs the Stripe secret key set as <code>STRIPE_API_KEY</code>.
     Once that's in the environment, this button opens Stripe Checkout directly.</p>
  <a class="btn" href="/#access">Request access</a>
  <a class="btn ghost" href="/crm">Open console</a>
</div></div>"""))
        try:
            session = billing.create_checkout(tier)
        except Exception as e:  # noqa: BLE001 — surface a friendly page
            return self._send(502, page("Checkout error", f"""
<div class="wrap"><div class="hero"><h1>Checkout unavailable</h1>
  <p class="note">{html.escape(str(e))[:300]}</p>
  <a class="btn" href="/#pricing">Back to pricing</a></div></div>"""))
        self.send_response(303)
        self.send_header("Location", session["url"])
        self.end_headers()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        params = self._body_params()
        wants_json = "application/json" in self.headers.get("Content-Type", "")

        if path == "/api/leads":
            try:
                lead = create_lead(params)
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            if wants_json:
                return self._json(201, lead)
            # browser form post → redirect to CRM
            self.send_response(303)
            self.send_header("Location", "/crm")
            self.end_headers()
            return

        if path.startswith("/api/leads/") and path.endswith("/status"):
            try:
                lead_id = int(path.split("/")[3])
            except (IndexError, ValueError):
                return self._json(404, {"error": "bad lead id"})
            try:
                ok = set_status(lead_id, (params.get("status") or "").strip())
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            if not ok:
                return self._json(404, {"error": "lead not found"})
            if wants_json:
                return self._json(200, {"id": lead_id, "status": params["status"]})
            self.send_response(303)
            self.send_header("Location", "/crm")
            self.end_headers()
            return

        self._json(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    init_db()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Allerion platform on http://{args.host}:{args.port}  (CRM at /crm)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
