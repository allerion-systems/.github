"""Tests for the Allerion Skills Store: catalog, license signing, zip delivery."""
import io
import os
import sys
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
