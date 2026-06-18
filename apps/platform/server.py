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
:root{--bg:#0b0d10;--panel:#14181d;--line:#232a31;--ink:#e9edf1;--mut:#8b97a3;--acc:#e07a3f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--acc);text-decoration:none}.wrap{max-width:980px;margin:0 auto;padding:0 24px}
header{border-bottom:1px solid var(--line)}header .wrap{display:flex;align-items:center;
justify-content:space-between;height:64px}.brand{font-weight:700;letter-spacing:.02em}
.brand b{color:var(--acc)}nav a{margin-left:20px;color:var(--mut)}nav a:hover{color:var(--ink)}
.hero{padding:88px 0 64px;text-align:center}.hero h1{font-size:44px;line-height:1.1;margin:0 0 16px}
.hero p{font-size:19px;color:var(--mut);max-width:640px;margin:0 auto 32px}
.btn{display:inline-block;background:var(--acc);color:#fff;padding:12px 22px;border-radius:8px;font-weight:600}
.btn.ghost{background:transparent;border:1px solid var(--line);color:var(--ink);margin-left:10px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin:48px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:22px}
.card h3{margin:0 0 6px;font-size:17px}.card p{margin:0;color:var(--mut);font-size:14px}
.price{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0 56px}
.price .card{text-align:center}.price .amt{font-size:30px;font-weight:700;margin:8px 0}
.price .amt small{font-size:14px;color:var(--mut);font-weight:400}
section h2{font-size:13px;text-transform:uppercase;letter-spacing:.14em;color:var(--mut);margin:48px 0 0}
form{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:24px;margin:20px 0 72px}
label{display:block;font-size:13px;color:var(--mut);margin:12px 0 4px}
input,select,textarea{width:100%;background:#0e1216;border:1px solid var(--line);color:var(--ink);
border-radius:8px;padding:10px 12px;font:inherit}textarea{min-height:84px;resize:vertical}
table{width:100%;border-collapse:collapse;margin:16px 0}th,td{text-align:left;padding:10px 8px;
border-bottom:1px solid var(--line);font-size:14px}th{color:var(--mut);font-weight:600}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;border:1px solid var(--line)}
.s-new{color:#7aa2ff}.s-contacted{color:#e0c23f}.s-qualified{color:var(--acc)}
.s-won{color:#4fbf72}.s-lost{color:#8b97a3}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:20px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;text-align:center}
.kpi b{display:block;font-size:26px}.kpi span{color:var(--mut);font-size:12px;text-transform:uppercase}
footer{border-top:1px solid var(--line);color:var(--mut);font-size:13px;padding:28px 0;text-align:center}
.note{color:var(--mut);font-size:13px}
"""

CAPABILITIES = [
    ("Digital Twin", "3D BIM infrastructure intelligence — real-time spatial data at industrial scale."),
    ("Construction ERP", "Autonomous cost estimation, BOQ generation, CAD/BIM takeoff."),
    ("Agent Orchestration", "Multi-agent swarms — agents hiring agents via the A2A protocol."),
    ("Sovereign AI", "Self-hosted LLM deployment on private infrastructure — your models, your silicon."),
]

PRICING = [
    ("Gateway", "$0", "/mo to start", "Branded OpenAI-compatible API at api.allerion.io. Pay only for usage."),
    ("Team", "$2k", "/mo", "Virtual keys, budgets, metered Stripe billing, priority routing."),
    ("Sovereign", "Custom", "", "Self-hosted GPU deployment + on-prem agent orchestration."),
]


def page(title: str, body: str) -> bytes:
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body>
<header><div class="wrap">
  <div class="brand">▲ ALLERION<b>.io</b></div>
  <nav><a href="/">Platform</a><a href="/#pricing">Pricing</a><a href="/crm">CRM</a></nav>
</div></header>
{body}
<footer><div class="wrap">Allerion Systems — autonomous intelligence for the built world. We don't sell software. We deploy intelligence.</div></footer>
</body></html>"""
    return doc.encode()


def landing() -> bytes:
    caps = "".join(
        f'<div class="card"><h3>{html.escape(t)}</h3><p>{html.escape(d)}</p></div>'
        for t, d in CAPABILITIES
    )
    price = "".join(
        f'<div class="card"><h3>{html.escape(n)}</h3>'
        f'<div class="amt">{html.escape(a)} <small>{html.escape(p)}</small></div>'
        f'<p>{html.escape(d)}</p></div>'
        for n, a, p, d in PRICING
    )
    body = f"""
<div class="hero"><div class="wrap">
  <h1>Autonomous intelligence<br>for the built world.</h1>
  <p>We design, deploy, and operate multi-agent AI systems for infrastructure,
     construction, and industrial operations. Our agents estimate. Our agents build.
     Our agents never sleep.</p>
  <a class="btn" href="#access">Request access</a>
  <a class="btn ghost" href="/crm">Open CRM</a>
</div></div>
<div class="wrap">
  <section><h2>Capabilities</h2></section>
  <div class="grid">{caps}</div>
  <section id="pricing"><h2>Pricing</h2></section>
  <div class="price">{price}</div>
  <section id="access"><h2>Request access</h2></section>
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
    <p style="margin-top:18px"><button class="btn" type="submit">Request access</button></p>
    <p class="note">Submitting creates a lead in the embedded CRM.</p>
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
    body = f"""<div class="wrap">
  <section><h2>CRM — pipeline</h2></section>
  <div class="kpis">{kpis}</div>
  {table}
  <p class="note">Embedded CRM over the same SQLite store. JSON API at <code>/api/leads</code>.</p>
</div>"""
    return page("Allerion CRM", body)


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
        elif path == "/healthz":
            self._json(200, {"ok": True})
        else:
            self._send(404, page("Not found", '<div class="wrap"><div class="hero"><h1>404</h1></div></div>'))

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
