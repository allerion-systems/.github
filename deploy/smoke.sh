#!/bin/sh
# smoke.sh — Allerion post-deploy smoke test.
#
# Run this AFTER `docker compose up` to confirm the live sites are healthy:
#
#     ./smoke.sh
#
# By default it hits the public endpoints:
#     https://allerion.io/healthz        (platform)
#     https://skills.allerion.io/healthz (store)
#
# Optional first arg overrides the base scheme://host to test a single local
# instance instead of the two public sites, e.g.:
#
#     ./smoke.sh http://127.0.0.1:8088   # one local store instance
#     ./smoke.sh http://127.0.0.1:8099   # one local platform instance
#
# Each check curls /healthz and asserts the body contains "ok": true.
# For the store it also surfaces stripe_live and the products count.
#
# Exit codes: 0 = every checked site healthy; 1 = at least one unhealthy.

set -eu

PLATFORM_URL="https://allerion.io"
STORE_URL="https://skills.allerion.io"

FAILED=0

if ! command -v curl >/dev/null 2>&1; then
	echo "FAIL  curl is required but not installed."
	exit 1
fi

# Extract a JSON field value (string/bool/number) without jq.
#   json_field '<body>' '<key>'  ->  prints value, or empty if absent.
json_field() {
	# Tolerates `"key": value` and `"key":value`. Stops at , } or whitespace.
	printf '%s' "$1" \
		| tr -d '\n' \
		| sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^\",}]*\).*/\1/p" \
		| head -n 1
}

# check_site <label> <base-url> <is_store:0|1>
check_site() {
	label="$1"
	base="$2"
	is_store="$3"
	url="${base%/}/healthz"

	echo "-- $label ($url) --"

	# --max-time bounds the wait; -f makes HTTP errors a non-zero exit.
	if body=$(curl -fsS --max-time 15 "$url" 2>/dev/null); then
		ok=$(json_field "$body" ok)
		# Accept "ok": true and "ok":true (json_field already normalises spacing).
		case "$ok" in
			true)
				printf 'PASS  %s is healthy ("ok": true)\n' "$label"
				;;
			*)
				printf 'FAIL  %s responded but "ok" is not true (got: %s)\n' "$label" "${ok:-<missing>}"
				FAILED=$((FAILED + 1))
				;;
		esac

		if [ "$is_store" -eq 1 ]; then
			stripe_live=$(json_field "$body" stripe_live)
			products=$(json_field "$body" products)
			printf '      stripe_live: %s | products: %s\n' "${stripe_live:-unknown}" "${products:-unknown}"
		fi

		printf '      body: %s\n' "$body"
	else
		printf 'FAIL  %s did not return a healthy response (curl failed / timed out)\n' "$label"
		FAILED=$((FAILED + 1))
	fi
	echo
}

echo "== Allerion smoke test =="
echo

if [ "$#" -ge 1 ]; then
	# Override mode: test a single instance at the given base URL.
	# We can't know if it's platform or store, so surface store fields too
	# (they'll just show "unknown" for a platform instance).
	check_site "instance" "$1" 1
else
	check_site "platform (allerion.io)" "$PLATFORM_URL" 0
	check_site "store (skills.allerion.io)" "$STORE_URL" 1
fi

echo "== summary =="
if [ "$FAILED" -gt 0 ]; then
	printf 'RESULT: FAIL (%s site(s) unhealthy). Check `docker compose logs -f` and DNS/TLS.\n' "$FAILED"
	exit 1
fi
echo "RESULT: PASS — all checked sites healthy."
exit 0
