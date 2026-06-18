#!/usr/bin/env python3
"""Allerion Skills Store — sell Claude Skills + the Codex plugin via Stripe.

Zero dependencies (Python standard library only). Serves a storefront, runs
one-time Stripe Checkout, verifies payment server-side, and delivers the product
as a license-gated zip built on the fly.

    python3 server.py                 # http://127.0.0.1:8088
    python3 server.py --port 9001 --host 0.0.0.0

Routes
    GET /                      storefront (product grid)
    GET /api/products          catalog as JSON
    GET /buy/<slug>            create Stripe Checkout + redirect (or dev-grant)
    GET /success              verify the paid session, mint license, show download
    GET /download?token=...    verify license, stream the product zip
    GET /healthz               health check
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

import catalog
import fulfillment
import payments

DB_PATH = os.environ.get("STORE_DB", os.path.join(os.path.dirname(__file__), "store.db"))
# Allow handing over a product without Stripe ONLY when explicitly enabled (local testing).
DEV_FULFILLMENT = os.environ.get("STORE_DEV_FULFILLMENT", "") == "1"


# --------------------------------------------------------------------------- db
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                slug        TEXT NOT NULL,
                email       TEXT,
                amount      INTEGER,
                currency    TEXT,
                session_id  TEXT UNIQUE,
                source      TEXT NOT NULL,          -- 'stripe' | 'dev'
                created_at  TEXT NOT NULL
            )"""
        )


def record_order(slug, email, amount, currency, session_id, source) -> None:
    with db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO orders (slug,email,amount,currency,session_id,source,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (slug, email, amount, currency, session_id, source,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )


def revenue() -> tuple[int, int]:
    with db() as conn:
        r = conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(amount),0) gross FROM orders WHERE source='stripe'"
        ).fetchone()
        return r["n"], r["gross"]


# ------------------------------------------------------------------------- views
CSS = """
:root{--bg:#07090a;--bg2:#0b0f0c;--panel:#0f1411;--line:#1f2a22;--line2:#2b3a2e;
--ink:#e9f1ea;--mut:#7e8d82;--nv:#76b900;--nv2:#b6ff3a;--glow:rgba(118,185,0,.30);
--mono:ui-monospace,"JetBrains Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
body::before{content:"";position:fixed;inset:0;z-index:-2;
background:radial-gradient(900px 520px at 50% -12%,rgba(118,185,0,.12),transparent 70%),linear-gradient(var(--bg2),var(--bg))}
a{color:var(--nv);text-decoration:none}
.wrap{max-width:1040px;margin:0 auto;padding:0 24px}
.mono{font-family:var(--mono);text-transform:uppercase;letter-spacing:.18em;font-size:12px;color:var(--mut)}
.nv{color:var(--nv)}
header{position:sticky;top:0;z-index:10;backdrop-filter:blur(10px);
background:rgba(7,9,10,.72);border-bottom:1px solid var(--line)}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:62px}
.brand{font-family:var(--mono);font-weight:700;letter-spacing:.22em;font-size:14px}
.brand .mk{color:var(--nv)}
nav a{margin-left:22px;font-family:var(--mono);font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}
nav a:hover{color:var(--ink)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--nv);
box-shadow:0 0 0 0 var(--glow);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 var(--glow)}70%{box-shadow:0 0 0 10px transparent}100%{box-shadow:0 0 0 0 transparent}}
.hero{padding:84px 0 36px;text-align:center}
.hero .ey{display:inline-flex;align-items:center;gap:10px;margin-bottom:22px;padding:6px 14px;
border:1px solid var(--line2);border-radius:999px;background:var(--panel)}
.hero h1{font-size:50px;line-height:1.04;margin:0 0 16px;letter-spacing:-.025em;font-weight:800}
.hero h1 .g{background:linear-gradient(90deg,var(--nv),var(--nv2));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero p{font-size:18px;color:var(--mut);max-width:640px;margin:0 auto}
section .lbl{display:flex;align-items:center;gap:14px;margin:54px 0 20px;font-family:var(--mono);
text-transform:uppercase;letter-spacing:.18em;font-size:12px;color:var(--mut)}
section .lbl::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--line2),transparent)}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}
.card{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:24px;transition:border-color .2s,transform .2s,box-shadow .2s;overflow:hidden;display:flex;flex-direction:column}
.card::before{content:"";position:absolute;left:0;top:0;width:30px;height:30px;
border-top:2px solid var(--nv);border-left:2px solid var(--nv);opacity:.45;transition:opacity .2s}
.card:hover{border-color:var(--line2);transform:translateY(-3px);box-shadow:0 14px 44px rgba(0,0,0,.55)}
.card:hover::before{opacity:1}
.card.feat{border-color:var(--nv);box-shadow:0 0 28px var(--glow)}
.kind{font-family:var(--mono);font-size:11px;color:var(--nv);letter-spacing:.16em}
.card h3{margin:8px 0 4px;font-size:20px}
.card .tag{color:var(--ink);font-size:14px;margin:0 0 10px}
.card p{margin:0 0 16px;color:var(--mut);font-size:14px;flex:1}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:auto}
.amt{font-size:26px;font-weight:800}
.amt small{font-size:12px;color:var(--mut);font-weight:600;font-family:var(--mono);text-transform:uppercase}
.btn{display:inline-block;font-family:var(--mono);font-size:13px;letter-spacing:.1em;text-transform:uppercase;
background:var(--nv);color:#06140a;padding:11px 20px;border-radius:8px;font-weight:700;border:1px solid var(--nv);
transition:transform .15s,box-shadow .15s,background .15s;box-shadow:0 0 24px var(--glow);cursor:pointer}
.btn:hover{transform:translateY(-2px);box-shadow:0 0 38px var(--glow);background:var(--nv2);border-color:var(--nv2)}
.btn.ghost{background:transparent;color:var(--ink);border-color:var(--line2);box-shadow:none}
.btn.big{font-size:15px;padding:14px 26px}
.telem{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:22px 0}
.telem .t{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px}
.telem .k{font-family:var(--mono);font-size:11px;color:var(--mut);letter-spacing:.14em;text-transform:uppercase}
.telem .v{font-size:24px;font-weight:800;margin-top:4px}
.banner{background:var(--panel);border:1px solid var(--line2);border-radius:12px;padding:16px 18px;margin:18px 0;font-size:14px;color:var(--mut)}
.banner b{color:var(--ink)}
footer{border-top:1px solid var(--line);color:var(--mut);padding:30px 0;text-align:center;margin-top:60px}
.note{color:var(--mut);font-size:12px;font-family:var(--mono);letter-spacing:.04em}
code{font-family:var(--mono);color:var(--nv);font-size:13px}
.center{text-align:center}
"""


def page(title: str, body: str) -> bytes:
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head><body>
<header><div class="wrap">
  <div class="brand"><span class="mk">&#9650;</span> ALLERION<span class="nv"> SKILLS</span></div>
  <nav><a href="/">Store</a><a href="/#catalog">Catalog</a><a href="https://allerion.io">allerion.io</a></nav>
</div></header>
{body}
<footer><div class="wrap"><div class="mono"><span class="nv">&#9650;</span> Allerion Systems — developer skills for Claude &amp; Codex</div>
<div class="note" style="margin-top:8px">Instant download &middot; commercial license &middot; one seat per purchase</div></div></footer>
</body></html>"""
    return doc.encode()


def storefront() -> bytes:
    cards = []
    for slug, p in catalog.PRODUCTS.items():
        feat = " feat" if slug == "devkit-bundle" else ""
        cta = (f'<a class="btn" href="/buy/{slug}">Buy &middot; {catalog.usd(p["price"])} &rarr;</a>')
        cards.append(
            f'<div class="card{feat}">'
            f'<div class="kind">{html.escape(p["kind"])}</div>'
            f'<h3>{html.escape(p["name"])}</h3>'
            f'<div class="tag">{html.escape(p["tagline"])}</div>'
            f'<p>{html.escape(p["blurb"])}</p>'
            f'<div class="row"><div class="amt">{catalog.usd(p["price"])} '
            f'<small>one-time</small></div>{cta}</div></div>'
        )
    grid = "".join(cards)

    n, gross = revenue()
    if payments.live():
        mode = "Stripe live" if "sk_live" in payments.STRIPE_API_KEY else "Stripe test mode"
        banner = (f'<div class="banner"><b>Checkout is online</b> — payments run through '
                  f'Stripe ({mode}). Purchases deliver an instant, license-keyed download.</div>')
    else:
        banner = ('<div class="banner"><b>Storefront preview.</b> Products are built and the '
                  'purchase flow is wired end-to-end; it goes live the moment a Stripe secret key '
                  'is set as <code>STRIPE_API_KEY</code>. Until then, Buy shows the checkout that '
                  'is ready to fire.</div>')

    body = f"""
<div class="hero"><div class="wrap">
  <div class="ey"><span class="dot"></span><span class="mono">Developer skills &middot; instant download</span></div>
  <h1>Senior-engineer skills for<br><span class="g">Claude &amp; Codex</span>.</h1>
  <p>Battle-tested Agent Skills and a Codex plugin that review your diffs, write your
     release notes, and forge your tests. Buy once, download instantly, own it.</p>
</div></div>
<div class="wrap">
  {banner}
  <div class="telem">
    <div class="t"><div class="k">Products</div><div class="v">{len(catalog.PRODUCTS)}</div></div>
    <div class="t"><div class="k">Works in</div><div class="v">Claude + Codex</div></div>
    <div class="t"><div class="k">Orders fulfilled</div><div class="v">{n}</div></div>
  </div>
  <section id="catalog"><div class="lbl">// Catalog</div></section>
  <div class="grid">{grid}</div>
  <section><div class="lbl">// How it works</div></section>
  <div class="banner">
    <b>1.</b> Pick a product and check out with Stripe. &nbsp;
    <b>2.</b> We verify the payment and mint a license tied to your email. &nbsp;
    <b>3.</b> Download a zip with the skill/plugin + your license. Drop Claude Skills
    into <code>~/.claude/skills/</code>; add the Codex plugin to <code>~/.codex/config.toml</code>.
  </div>
</div>"""
    return page("Allerion Skills — developer skills for Claude & Codex", body)


def checkout_pending_page(slug: str) -> bytes:
    p = catalog.PRODUCTS[slug]
    dev = ""
    if DEV_FULFILLMENT:
        dev = (f'<p style="margin-top:18px"><a class="btn ghost" href="/success?dev=1&slug={slug}">'
               f'Dev grant (local testing) &rarr;</a></p>'
               f'<p class="note">// STORE_DEV_FULFILLMENT=1 — local testing only, no payment</p>')
    return page("Checkout — configuring", f"""
<div class="wrap"><div class="hero">
  <div class="ey"><span class="dot"></span><span class="mono">Checkout &middot; pending key</span></div>
  <h1>Ready for <span class="g">{html.escape(p['name'])}</span>.</h1>
  <p>Stripe Checkout for this product is wired and ready — it needs the Stripe secret key
     set as <code>STRIPE_API_KEY</code>. Once it's in the environment, this button opens
     Stripe Checkout and delivers the download automatically.</p>
  <a class="btn big" href="/#catalog">Back to catalog</a>{dev}
</div></div>""")


def download_page(slug: str, email: str, token: str) -> bytes:
    p = catalog.PRODUCTS[slug]
    url = "/download?" + urllib.parse.urlencode({"token": token})
    return page("Your download", f"""
<div class="wrap"><div class="hero">
  <div class="ey"><span class="dot"></span><span class="mono">Payment confirmed</span></div>
  <h1>Thank you — here's <span class="g">{html.escape(p['name'])}</span>.</h1>
  <p>Licensed to <b>{html.escape(email or 'you')}</b>. Your download link is below; the
     license key is inside the zip.</p>
  <p style="margin-top:22px"><a class="btn big" href="{html.escape(url)}">Download .zip &rarr;</a></p>
  <p class="note" style="margin-top:14px">// keep this link — it stays valid for re-downloads</p>
  <p style="margin-top:8px"><a class="btn ghost" href="/#catalog">Back to store</a></p>
</div></div>""")


def error_page(title: str, detail: str, code: int) -> bytes:
    return page(title, f"""
<div class="wrap"><div class="hero"><h1>{html.escape(title)}</h1>
  <p class="note">{html.escape(detail)[:400]}</p>
  <p style="margin-top:18px"><a class="btn" href="/#catalog">Back to catalog</a></p>
</div></div>""")


# ----------------------------------------------------------------------- handler
class Handler(BaseHTTPRequestHandler):
    server_version = "AllerionStore/1.0"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, indent=2).encode(), "application/json")

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path
        q = urllib.parse.parse_qs(u.query)
        if path == "/":
            self._send(200, storefront())
        elif path == "/api/products":
            self._json(200, {"products": [
                {"slug": s, "name": p["name"], "kind": p["kind"],
                 "price_cents": p["price"], "price": catalog.usd(p["price"]),
                 "tagline": p["tagline"]}
                for s, p in catalog.PRODUCTS.items()]})
        elif path.startswith("/buy/"):
            self._buy(path.split("/", 2)[2])
        elif path == "/success":
            self._success(q)
        elif path == "/download":
            self._download(q)
        elif path == "/healthz":
            n, gross = revenue()
            self._json(200, {"ok": True, "stripe_live": payments.live(),
                             "signing_production": fulfillment.signing_is_production(),
                             "products": len(catalog.PRODUCTS),
                             "orders": n, "gross_cents": gross})
        else:
            self._send(404, error_page("404", "No such page.", 404))

    def _buy(self, slug):
        if slug not in catalog.PRODUCTS:
            return self._send(404, error_page("Unknown product", "No such item.", 404))
        if not payments.live():
            return self._send(200, checkout_pending_page(slug))
        try:
            session = payments.create_checkout(slug)
        except Exception as e:  # noqa: BLE001
            return self._send(502, error_page("Checkout unavailable", str(e), 502))
        self._redirect(session["url"])

    def _success(self, q):
        # Dev grant path (local testing only).
        if q.get("dev", [""])[0] == "1" and DEV_FULFILLMENT:
            slug = q.get("slug", [""])[0]
            if slug not in catalog.PRODUCTS:
                return self._send(404, error_page("Unknown product", "No such item.", 404))
            email = "dev@localhost"
            record_order(slug, email, 0, "usd", f"dev-{slug}-{datetime.now().timestamp()}", "dev")
            token = fulfillment.mint_license(slug, email)
            return self._send(200, download_page(slug, email, token))

        session_id = q.get("session_id", [""])[0]
        if not session_id:
            return self._send(400, error_page("Missing session", "No checkout session id.", 400))
        try:
            session = payments.retrieve_session(session_id)
        except Exception as e:  # noqa: BLE001
            return self._send(502, error_page("Could not verify payment", str(e), 502))
        if session.get("payment_status") != "paid":
            return self._send(402, error_page("Payment not completed",
                                              "This checkout session isn't paid.", 402))
        slug = (session.get("metadata") or {}).get("slug", "")
        if slug not in catalog.PRODUCTS:
            return self._send(400, error_page("Unknown product", "Session has no product.", 400))
        email = (session.get("customer_details") or {}).get("email") \
            or session.get("customer_email") or ""
        record_order(slug, email, session.get("amount_total"),
                     session.get("currency"), session_id, "stripe")
        token = fulfillment.mint_license(slug, email)
        self._send(200, download_page(slug, email, token))

    def _download(self, q):
        token = q.get("token", [""])[0]
        payload = fulfillment.verify_license(token)
        if not payload:
            return self._send(403, error_page("Invalid or expired link",
                                              "This download link could not be verified.", 403))
        slug, email = payload["slug"], payload.get("email", "")
        try:
            blob = fulfillment.build_zip(slug, email, token)
        except Exception as e:  # noqa: BLE001
            return self._send(500, error_page("Build failed", str(e), 500))
        fname = f"allerion-{slug}.zip"
        self._send(200, blob, "application/zip",
                   {"Content-Disposition": f'attachment; filename="{fname}"'})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    init_db()
    if not fulfillment.signing_is_production():
        print("WARNING: STORE_SIGNING_SECRET not set — using a dev key. "
              "Set it before going live or license links won't be secure.")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Allerion Skills Store on http://{args.host}:{args.port}  "
          f"(Stripe {'LIVE' if payments.live() else 'not configured'})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
