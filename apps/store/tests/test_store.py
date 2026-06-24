"""Tests for the Allerion Skills Store: catalog, license signing, zip delivery."""
import hashlib
import hmac
import io
import json
import os
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import catalog        # noqa: E402
import fulfillment    # noqa: E402


def test_catalog_prices_and_sources_exist():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert catalog.PRODUCTS, "catalog must not be empty"
    for slug, p in catalog.PRODUCTS.items():
        assert p["price"] > 0
        assert p["sources"]
        for src in p["sources"]:
            assert os.path.isdir(os.path.join(here, src)), f"{slug}: missing source {src}"


def test_usd_formatting():
    assert catalog.usd(4900) == "$49"
    assert catalog.usd(2999) == "$29.99"
    assert catalog.usd(14900) == "$149"


def test_license_roundtrip_and_tamper():
    token = fulfillment.mint_license("pr-review-pro", "buyer@acme.co")
    payload = fulfillment.verify_license(token)
    assert payload and payload["slug"] == "pr-review-pro"
    assert payload["email"] == "buyer@acme.co"
    # tampering with the payload invalidates the signature
    body, sig = token.split(".", 1)
    forged = fulfillment._b64(b'{"slug":"devkit-bundle","email":"x","ts":"now"}') + "." + sig
    assert fulfillment.verify_license(forged) is None
    # garbage is rejected
    assert fulfillment.verify_license("not-a-token") is None


def test_license_unknown_slug_rejected():
    # a perfectly-signed token for a product that doesn't exist must be refused
    tok = fulfillment.mint_license("pr-review-pro", "x@y.co")
    raw = fulfillment._unb64(tok.split(".")[0]).replace(b"pr-review-pro", b"ghost-product")
    import hashlib, hmac
    sig = hmac.new(fulfillment.SIGNING_SECRET.encode(), raw, hashlib.sha256).digest()
    forged = fulfillment._b64(raw) + "." + fulfillment._b64(sig)
    assert fulfillment.verify_license(forged) is None


def test_build_zip_contains_skill_and_license():
    token = fulfillment.mint_license("pr-review-pro", "buyer@acme.co")
    blob = fulfillment.build_zip("pr-review-pro", "buyer@acme.co", token)
    zf = zipfile.ZipFile(io.BytesIO(blob))
    names = zf.namelist()
    assert "pr-review-pro/SKILL.md" in names
    assert "pr-review-pro/LICENSE.txt" in names
    assert "README-FIRST.txt" in names
    # license is personalized to the buyer
    lic = zf.read("pr-review-pro/LICENSE.txt").decode()
    assert "buyer@acme.co" in lic
    # no pyc / cache junk leaked in
    assert not any(n.endswith(".pyc") or "__pycache__" in n for n in names)


def test_bundle_zip_contains_all_products():
    token = fulfillment.mint_license("devkit-bundle", "team@acme.co")
    blob = fulfillment.build_zip("devkit-bundle", "team@acme.co", token)
    names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
    assert "pr-review-pro/SKILL.md" in names
    assert "changelog-craft/SKILL.md" in names
    assert "test-forge/SKILL.md" in names
    assert "codex-devkit/server.py" in names


def test_assistant_zip_contains_app_and_requirements():
    token = fulfillment.mint_license("allerion-assistant", "buyer@acme.co")
    blob = fulfillment.build_zip("allerion-assistant", "buyer@acme.co", token)
    names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
    assert "allerion-assistant/assistant.py" in names
    assert "allerion-assistant/requirements.txt" in names
    assert "allerion-assistant/LICENSE.txt" in names


def test_assistant_app_compiles():
    import py_compile
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_compile.compile(
        os.path.join(here, "products", "allerion-assistant", "assistant.py"),
        doraise=True,
    )


def test_every_claude_skill_has_valid_frontmatter():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    skills_dir = os.path.join(here, "products", "claude-skills")
    for name in os.listdir(skills_dir):
        skill_md = os.path.join(skills_dir, name, "SKILL.md")
        assert os.path.isfile(skill_md), f"{name} missing SKILL.md"
        text = open(skill_md, encoding="utf-8").read()
        assert text.startswith("---"), f"{name}: SKILL.md needs YAML frontmatter"
        front = text.split("---", 2)[1]
        assert "name:" in front and "description:" in front, f"{name}: frontmatter incomplete"


# ---------------------------------------------------------------- webhook tests
_WEBHOOK_SECRET = "whsec_test_secret"


def _sign(payload: bytes, secret: str, ts: int) -> str:
    signed = f"{ts}.{payload.decode()}".encode()
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def _fresh_server(tmp_path, monkeypatch):
    """Import server.py with an isolated DB and webhook secret set."""
    monkeypatch.setenv("STORE_DB", str(tmp_path / "store.db"))
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", _WEBHOOK_SECRET)
    for mod in ("server",):
        sys.modules.pop(mod, None)
    import importlib
    server = importlib.import_module("server")
    importlib.reload(server)
    server.init_db()
    return server


def test_verify_stripe_signature_good_and_bad():
    server = _fresh_server_module()
    payload = b'{"hello":"world"}'
    ts = int(time.time())
    header = _sign(payload, _WEBHOOK_SECRET, ts)
    assert server.verify_stripe_signature(payload, header, _WEBHOOK_SECRET)
    # bad signature (wrong secret)
    bad = _sign(payload, "whsec_wrong", ts)
    assert not server.verify_stripe_signature(payload, bad, _WEBHOOK_SECRET)
    # multiple v1 entries — any match accepted
    multi = f"t={ts},v1=deadbeef,{header.split(',', 1)[1]}"
    assert server.verify_stripe_signature(payload, multi, _WEBHOOK_SECRET)


def test_verify_stripe_signature_stale_rejected():
    server = _fresh_server_module()
    payload = b'{"hello":"world"}'
    stale_ts = int(time.time()) - 600  # 10 minutes ago
    header = _sign(payload, _WEBHOOK_SECRET, stale_ts)
    assert not server.verify_stripe_signature(payload, header, _WEBHOOK_SECRET)
    # but valid when within tolerance
    fresh = _sign(payload, _WEBHOOK_SECRET, int(time.time()))
    assert server.verify_stripe_signature(payload, fresh, _WEBHOOK_SECRET)


def _fresh_server_module():
    """server.py imported once with the webhook secret available (shared DB ok)."""
    os.environ["STRIPE_WEBHOOK_SECRET"] = _WEBHOOK_SECRET
    sys.modules.pop("server", None)
    import importlib
    server = importlib.import_module("server")
    importlib.reload(server)
    return server


def test_webhook_records_order_and_token(tmp_path, monkeypatch):
    server = _fresh_server(tmp_path, monkeypatch)
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "cs_test_webhook_1",
            "payment_status": "paid",
            "amount_total": 4900,
            "currency": "usd",
            "metadata": {"slug": "pr-review-pro"},
            "customer_details": {"email": "buyer@webhook.co"},
        }},
    }
    raw = json.dumps(event).encode()
    ts = int(time.time())
    header = _sign(raw, _WEBHOOK_SECRET, ts)
    assert server.verify_stripe_signature(raw, header, _WEBHOOK_SECRET)

    # Drive the handler logic directly (mirror of _webhook body) for an end-to-end check.
    session = event["data"]["object"]
    slug = session["metadata"]["slug"]
    email = session["customer_details"]["email"]
    token = fulfillment.mint_license(slug, email)
    server.record_order(slug, email, session["amount_total"], session["currency"],
                        session["id"], "stripe", license_token=token)
    server.set_license_token(session["id"], token)

    with server.db() as conn:
        row = conn.execute(
            "SELECT slug,email,license_token FROM orders WHERE session_id=?",
            (session["id"],)).fetchone()
    assert row is not None
    assert row["slug"] == "pr-review-pro"
    assert row["email"] == "buyer@webhook.co"
    assert row["license_token"] == token
    assert fulfillment.verify_license(row["license_token"])["slug"] == "pr-review-pro"


def test_webhook_idempotent_record(tmp_path, monkeypatch):
    server = _fresh_server(tmp_path, monkeypatch)
    sid = "cs_test_idem"
    t1 = fulfillment.mint_license("pr-review-pro", "a@b.co")
    server.record_order("pr-review-pro", "a@b.co", 4900, "usd", sid, "stripe", license_token=t1)
    # second insert with same session_id is ignored (UNIQUE constraint)
    server.record_order("pr-review-pro", "a@b.co", 4900, "usd", sid, "stripe", license_token=t1)
    with server.db() as conn:
        n = conn.execute("SELECT COUNT(*) c FROM orders WHERE session_id=?", (sid,)).fetchone()["c"]
    assert n == 1
