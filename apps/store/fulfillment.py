"""Digital fulfillment: signed license tokens + on-the-fly product zips.

A license token is a signed, self-verifying claim that someone bought a product —
so the download endpoint can authorize delivery without trusting the URL. Format:

    base64url(payload_json) . base64url(hmac_sha256(payload_json))

The HMAC key is STORE_SIGNING_SECRET (env). On purchase we mint a token tied to
{slug, email}; the download endpoint verifies the signature, then streams a zip
built from the product's source dirs with a personalized LICENSE.txt injected.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import zipfile
from datetime import datetime, timezone

import catalog

HERE = os.path.dirname(os.path.abspath(__file__))
_DEV_SECRET = "allerion-dev-signing-secret-change-me"
SIGNING_SECRET = os.environ.get("STORE_SIGNING_SECRET", _DEV_SECRET)


def signing_is_production() -> bool:
    return SIGNING_SECRET != _DEV_SECRET


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def mint_license(slug: str, email: str) -> str:
    """Return a signed download token for (slug, email)."""
    payload = {
        "slug": slug,
        "email": email,
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(SIGNING_SECRET.encode(), raw, hashlib.sha256).digest()
    return f"{_b64(raw)}.{_b64(sig)}"


def verify_license(token: str) -> dict | None:
    """Return the payload dict if the token is authentic and known, else None."""
    try:
        body_b64, sig_b64 = token.split(".", 1)
        raw = _unb64(body_b64)
        expected = hmac.new(SIGNING_SECRET.encode(), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig_b64)):
            return None
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("slug") not in catalog.PRODUCTS:
        return None
    return payload


def license_key(token: str) -> str:
    """A short, human-friendly key derived from the token (for the LICENSE file)."""
    digest = hashlib.sha256(token.encode()).hexdigest().upper()
    return "-".join(digest[i:i + 4] for i in range(0, 16, 4))


def build_zip(slug: str, email: str, token: str) -> bytes:
    """Build the deliverable zip for a product in memory."""
    product = catalog.PRODUCTS[slug]
    buf = io.BytesIO()
    issued = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    license_text = catalog.LICENSE_TEMPLATE.format(
        product=product["name"], email=email or "licensed user",
        license_key=license_key(token), issued=issued)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for src in product["sources"]:
            abs_src = os.path.join(HERE, src)
            top = os.path.basename(abs_src.rstrip("/"))
            for root, _dirs, names in os.walk(abs_src):
                # skip caches / vcs cruft (match path components, not substrings —
                # the repo itself lives under a ".github" dir)
                parts = set(root.split(os.sep))
                if "__pycache__" in parts or ".git" in parts:
                    continue
                for name in names:
                    if name.endswith((".pyc", ".pyo")):
                        continue
                    full = os.path.join(root, name)
                    rel = os.path.relpath(full, abs_src)
                    arc = os.path.join(top, rel)
                    zf.write(full, arc)
            # personalized license inside each product folder
            zf.writestr(os.path.join(top, "LICENSE.txt"), license_text)
        zf.writestr("README-FIRST.txt", _readme_first(product, email, issued))
    return buf.getvalue()


def _readme_first(product: dict, email: str, issued: str) -> str:
    return (
        f"Thank you for purchasing {product['name']} from Allerion Systems.\n\n"
        f"Licensed to: {email or 'you'}    Issued: {issued}\n\n"
        "WHAT'S INSIDE\n"
        f"  This bundle contains: {', '.join(os.path.basename(s) for s in product['sources'])}\n\n"
        "CLAUDE SKILLS  (folders containing a SKILL.md)\n"
        "  Copy the skill folder into your Claude skills directory:\n"
        "    Claude Code:   ~/.claude/skills/<skill-name>/\n"
        "    Then it loads automatically when relevant, or invoke it by name.\n\n"
        "CODEX PLUGIN  (codex-devkit/)\n"
        "  See codex-devkit/README.md — add one block to ~/.codex/config.toml.\n"
        "  Verify with:  python3 codex-devkit/server.py --selftest\n\n"
        "Each folder has its own LICENSE.txt tied to your purchase.\n"
        "Support & updates: https://allerion.io\n"
    )
