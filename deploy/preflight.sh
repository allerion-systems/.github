#!/bin/sh
# preflight.sh — Allerion deploy pre-flight checks.
#
# Run this from the deploy/ directory BEFORE `docker compose up`:
#
#     cd deploy && ./preflight.sh
#
# It verifies the host is ready to bring the stack up and obtain TLS certs:
#   - docker + the `docker compose` plugin are installed
#   - deploy/.env exists and has a non-empty STORE_SIGNING_SECRET (HARD FAIL)
#   - Stripe key sanity (warn-only: empty = preview, sk_test_ = rehearsal)
#   - DNS A records for allerion.io / www.allerion.io / skills.allerion.io
#     resolve, ideally to this machine's public IP (warn-only)
#   - ports 80/443 are not already taken locally (warn-only)
#
# Hard failures exit non-zero. Warnings never fail the run. Missing optional
# tools (dig, ss, curl, ...) are reported as "skipped", never fatal.
#
# Exit codes: 0 = all hard checks passed; 1 = at least one hard check failed.

set -eu

# --- config: the public hostnames Caddy serves ------------------------------
HOSTS="allerion.io www.allerion.io skills.allerion.io"

# --- state ------------------------------------------------------------------
FAILED=0
WARNED=0

# Resolve the directory this script lives in (so it works from anywhere).
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ENV_FILE="$SCRIPT_DIR/.env"

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; FAILED=$((FAILED + 1)); }
warn() { printf 'WARN  %s\n' "$1"; WARNED=$((WARNED + 1)); }
skip() { printf 'SKIP  %s\n' "$1"; }
info() { printf '      %s\n' "$1"; }

have() { command -v "$1" >/dev/null 2>&1; }

echo "== Allerion deploy preflight =="
echo

# --- 1. docker + compose plugin --------------------------------------------
echo "-- docker --"
if have docker; then
	pass "docker is installed ($(docker --version 2>/dev/null || echo 'version unknown'))"
	if docker compose version >/dev/null 2>&1; then
		pass "docker compose plugin is installed ($(docker compose version --short 2>/dev/null || echo 'version unknown'))"
	else
		fail "the 'docker compose' plugin is not available — install it (see DEPLOY.md §0)"
	fi
else
	fail "docker is not installed — run: curl -fsSL https://get.docker.com | sh (DEPLOY.md §0)"
fi
echo

# --- 2. .env + required secrets --------------------------------------------
echo "-- .env --"
if [ -f "$ENV_FILE" ]; then
	pass ".env exists at $ENV_FILE"

	# Read a KEY=VALUE from .env, stripping surrounding quotes/whitespace.
	# Last assignment wins (matches shell/compose semantics).
	read_env() {
		# $1 = key name
		grep -E "^[[:space:]]*$1=" "$ENV_FILE" 2>/dev/null \
			| tail -n 1 \
			| sed -e "s/^[[:space:]]*$1=//" \
			      -e 's/^"//' -e 's/"$//' \
			      -e "s/^'//" -e "s/'\$//" \
			| tr -d '\r'
	}

	SIGNING_SECRET=$(read_env STORE_SIGNING_SECRET || true)
	if [ -n "${SIGNING_SECRET:-}" ]; then
		pass "STORE_SIGNING_SECRET is set (the store can sign licenses)"
	else
		fail "STORE_SIGNING_SECRET is empty/missing — the store won't sign licenses securely."
		info "Generate a stable one: echo \"STORE_SIGNING_SECRET=\$(openssl rand -hex 32)\" >> .env"
	fi

	STRIPE_KEY=$(read_env STRIPE_API_KEY || true)
	if [ -z "${STRIPE_KEY:-}" ]; then
		warn "STRIPE_API_KEY is empty — store boots in PREVIEW mode (checkout disabled)."
	else
		case "$STRIPE_KEY" in
			sk_test_*)
				warn "STRIPE_API_KEY is a TEST key (sk_test_) — rehearsal mode, not real charges." ;;
			sk_live_*)
				pass "STRIPE_API_KEY is a LIVE key (sk_live_) — real payments enabled." ;;
			*)
				warn "STRIPE_API_KEY is set but doesn't look like sk_test_/sk_live_ — double-check it." ;;
		esac
	fi
else
	fail ".env not found at $ENV_FILE — copy it: cp .env.example .env (DEPLOY.md §3)"
fi
echo

# --- 3. discover this machine's public IP (best effort) --------------------
echo "-- public IP --"
MY_IP=""
if have curl; then
	MY_IP=$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || true)
	if [ -n "$MY_IP" ]; then
		pass "this machine's public IP appears to be $MY_IP"
	else
		warn "couldn't determine public IP (api.ipify.org unreachable) — skipping IP match."
	fi
else
	skip "public IP check skipped: curl not found"
fi
echo

# --- 4. DNS A records -------------------------------------------------------
echo "-- DNS --"
# Pick a resolver tool once.
RESOLVER=""
if have getent; then
	RESOLVER="getent"
elif have dig; then
	RESOLVER="dig"
elif have nslookup; then
	RESOLVER="nslookup"
fi

if [ -z "$RESOLVER" ]; then
	skip "DNS checks skipped: none of getent/dig/nslookup found"
else
	for h in $HOSTS; do
		IPS=""
		case "$RESOLVER" in
			getent)
				# getent hosts may print v4 and v6; keep IPv4-looking lines.
				IPS=$(getent ahostsv4 "$h" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ')
				if [ -z "$IPS" ]; then
					IPS=$(getent hosts "$h" 2>/dev/null | awk '{print $1}' | sort -u | tr '\n' ' ')
				fi
				;;
			dig)
				IPS=$(dig +short A "$h" 2>/dev/null | grep -E '^[0-9]+\.' | tr '\n' ' ')
				;;
			nslookup)
				IPS=$(nslookup "$h" 2>/dev/null | awk '/^Address: /{print $2}' | grep -E '^[0-9]+\.' | tr '\n' ' ')
				;;
		esac
		IPS=$(echo "$IPS" | sed 's/[[:space:]]*$//')

		if [ -z "$IPS" ]; then
			warn "$h does not resolve to an A record — Caddy can't issue TLS until DNS points here."
		elif [ -n "$MY_IP" ]; then
			# Does any resolved IP match this box?
			MATCH=0
			for ip in $IPS; do
				[ "$ip" = "$MY_IP" ] && MATCH=1
			done
			if [ "$MATCH" -eq 1 ]; then
				pass "$h -> $IPS (matches this machine)"
			else
				warn "$h -> $IPS (does NOT match this machine's $MY_IP) — TLS issuance will fail."
			fi
		else
			# We have IPs but no public IP to compare against.
			pass "$h -> $IPS"
			info "(couldn't compare against this machine's IP; verify it points here)"
		fi
	done
fi
echo

# --- 5. ports 80 / 443 ------------------------------------------------------
echo "-- ports 80/443 --"
PORT_TOOL=""
if have ss; then
	PORT_TOOL="ss"
elif have netstat; then
	PORT_TOOL="netstat"
fi

if [ -z "$PORT_TOOL" ]; then
	skip "port checks skipped: neither ss nor netstat found"
else
	if [ "$PORT_TOOL" = "ss" ]; then
		LISTEN=$(ss -ltn 2>/dev/null || true)
	else
		LISTEN=$(netstat -ltn 2>/dev/null || true)
	fi
	for p in 80 443; do
		# Match ":80 " or ":443 " at the local-address column end.
		if printf '%s\n' "$LISTEN" | grep -Eq "[:.]$p[[:space:]]"; then
			warn "port $p is already in use locally — Caddy needs it."
			info "Likely an existing gateway Caddy holding 80/443. See DEPLOY.md §6 to consolidate."
		else
			pass "port $p is free"
		fi
	done
fi
echo

# --- summary ----------------------------------------------------------------
echo "== summary =="
if [ "$FAILED" -gt 0 ]; then
	printf 'RESULT: FAIL (%s hard failure(s), %s warning(s)). Fix the FAIL items above before deploying.\n' "$FAILED" "$WARNED"
	exit 1
fi
if [ "$WARNED" -gt 0 ]; then
	printf 'RESULT: PASS with %s warning(s). Review the WARN items — DNS/ports/Stripe may need attention.\n' "$WARNED"
else
	echo "RESULT: PASS — ready for: docker compose up -d --build"
fi
exit 0
